"""One explicit ET operation per TCP connection; no retries or background I/O."""

from dataclasses import dataclass
from datetime import datetime, timezone
import socket
import threading
import time
from typing import Callable

from .config import Settings
from .protocol import Frame, FrameParser, ProtocolError, build_command, decode_external_text


class CommunicationError(RuntimeError):
    pass


class ResponseTimeout(CommunicationError):
    pass


class DeviceError(CommunicationError):
    pass


@dataclass(frozen=True)
class Event:
    timestamp: str
    kind: str
    message: str
    data: bytes | None = None


@dataclass(frozen=True)
class Verification:
    expected: str
    actual: str

    @property
    def matched(self) -> bool:
        return self.expected == self.actual


class LJ3Client:
    def __init__(
        self,
        settings: Settings,
        on_event: Callable[[Event], None] | None = None,
        *,
        socket_factory: Callable = socket.create_connection,
    ):
        settings.validate(require_ip=False)
        self.settings = settings
        self._on_event = on_event
        self._socket_factory = socket_factory
        self._socket: socket.socket | None = None
        self._lock = threading.RLock()

    def _emit(self, kind: str, message: str, data: bytes | None = None) -> None:
        if self._on_event:
            self._on_event(Event(datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                 kind, message, data))

    @property
    def connected(self) -> bool:
        """Local socket state, not a live printer health check."""
        return self._socket is not None

    def connect(self) -> None:
        """Explicit TCP handshake only. Sends no LJ3 command."""
        with self._lock:
            if self.connected:
                return
            self.settings.validate()
            self._emit("STATUS", f"Connecting to {self.settings.ip}:{self.settings.port}")
            try:
                self._socket = self._socket_factory(
                    (self.settings.ip, self.settings.port), timeout=self.settings.timeout
                )
            except OSError as exc:
                self._emit("ERROR", f"TCP connection failed: {exc}")
                raise CommunicationError(f"TCP connection failed: {exc}") from exc
            self._emit("STATUS", "Connected (TCP only; printer identity/readiness unverified)")

    def disconnect(self) -> None:
        with self._lock:
            if self._socket is not None:
                connection, self._socket = self._socket, None
                try:
                    connection.close()
                except OSError as exc:
                    self._emit("ERROR", f"Socket close failed: {exc}")
                self._emit("STATUS", "Disconnected")

    def send_command(
        self, command: str, text: str | None = None, *, stopped_ascii_job_confirmed: bool = False
    ) -> Frame | None:
        """Send only an allowlisted command on an explicitly opened connection.

        Every operation closes the socket. Writes do not wait for an ACK.
        The confirmation enforces our Phase 1 commissioning policy, not a
        documented LJ3 stop-printing requirement or a hardware interlock.
        """
        wire = build_command(command, text)
        if command == "=ET" and not stopped_ascii_job_confirmed:
            raise ValueError("Phase 1 commissioning policy: confirm printing is stopped and a non-Unicode Field 0 test job is loaded.")
        with self._lock:
            if self._socket is None:
                raise CommunicationError("Not connected; call connect explicitly.")
            deadline = time.monotonic() + self.settings.timeout
            try:
                self._socket.settimeout(self.settings.timeout)
                self._emit("TX", "Attempting transmission; delivery not yet known", wire)
                self._socket.sendall(wire)
                if command == "=ET":
                    self._emit("RESULT", "SENT - UNVERIFIED. No ordinary ACK is specified; read back separately.")
                    return None
                return self._read_external_text_frame(deadline)
            except ProtocolError as exc:
                self._emit("ERROR", str(exc))
                raise
            except TimeoutError as exc:
                message = "Operation timed out; printer acceptance is unknown. No automatic retry."
                self._emit("ERROR", message)
                raise ResponseTimeout(message) from exc
            except OSError as exc:
                message = f"TCP failure: {exc}. Delivery may be partial or unknown; no automatic retry."
                self._emit("ERROR", message)
                raise CommunicationError(message) from exc
            finally:
                self.disconnect()

    def _read_external_text_frame(self, deadline: float) -> Frame:
        parser = FrameParser()
        total = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("No matching =ET before deadline")
            assert self._socket is not None
            self._socket.settimeout(remaining)
            chunk = self._socket.recv(4096)
            if not chunk:
                message = "Peer closed before a complete =ET reply; readback unavailable."
                self._emit("ERROR", message)
                raise CommunicationError(message)
            self._emit("RX", "Received TCP bytes", chunk)
            total += len(chunk)
            if total > 65536:
                raise ProtocolError("Too much unsolicited data while awaiting =ET.")
            matches = []
            for frame in parser.feed(chunk):
                if frame.command == "=FC":
                    self._emit("ERROR", "Printer reported CRC failure (=FC).", frame.raw)
                    raise DeviceError("Printer reported CRC failure; CRC was not enabled by this client.")
                if frame.command == "=RS":
                    fields = frame.payload.split(b"\t")
                    if len(fields) < 3:
                        raise ProtocolError("Malformed machine-state frame (=RS).")
                    try:
                        error = int(fields[2])
                    except ValueError as exc:
                        raise ProtocolError("Non-numeric error in machine-state frame.") from exc
                    if error:
                        self._emit("ERROR", f"Printer reported numeric error {error}.", frame.raw)
                        raise DeviceError(f"Printer error {error}; consult printer display.")
                if frame.command == "=ET":
                    decode_external_text(frame)  # Validate before accepting.
                    matches.append(frame)
                else:
                    self._emit("NOTICE", f"Unsolicited/unmatched {frame.command}; not an ET acknowledgement.", frame.raw)
            if len(matches) > 1:
                raise ProtocolError("Multiple =ET frames in one receive batch; ambiguous readback.")
            if matches:
                if parser.incomplete:
                    raise ProtocolError("Additional incomplete frame after =ET; ambiguous receive batch.")
                return matches[0]

    def set_external_text(self, text: str, *, stopped_ascii_job_confirmed: bool = False) -> None:
        build_command("=ET", text)  # Reject invalid input before any network activity.
        if not stopped_ascii_job_confirmed:
            raise ValueError("Phase 1 commissioning policy: confirm printing is stopped and a non-Unicode Field 0 test job is loaded.")
        with self._lock:
            self.disconnect()
            self.connect()
            self.send_command("=ET", text, stopped_ascii_job_confirmed=True)

    def get_external_text(self) -> str:
        with self._lock:
            self.disconnect()
            self.connect()  # Fresh stream avoids treating a previous write echo as readback.
            frame = self.send_command("?ET")
            assert frame is not None
            return decode_external_text(frame)

    def verify_external_text(self, expected: str) -> Verification:
        build_command("=ET", expected)  # Validation only; never sends a write.
        result = Verification(expected, self.get_external_text())
        self._emit("RESULT", f"{'VERIFIED (exact ?ET readback)' if result.matched else 'MISMATCH'}: "
                   f"expected={result.expected!r}, returned={result.actual!r}. Physical printing is unverified.")
        return result
