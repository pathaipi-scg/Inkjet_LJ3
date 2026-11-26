"""Explicit LJ3 TCP session with serialized commands; no retries or background I/O."""

from dataclasses import dataclass
from datetime import datetime, timezone
import socket
import threading
import time
from typing import Callable

from .config import Settings
from .protocol import (Frame, FrameParser, PrinterStatus, ProtocolError, build_command,
                       decode_external_text, decode_printer_status)


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
    elapsed_ms: float | None = None


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
        self._parser = FrameParser()
        self._write_session: socket.socket | None = None
        self._write_value: str | None = None
        self._lock = threading.RLock()

    def _emit(self, kind: str, message: str, data: bytes | None = None,
              elapsed_ms: float | None = None) -> None:
        if self._on_event:
            self._on_event(Event(datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                 kind, message, data, elapsed_ms))

    @property
    def connected(self) -> bool:
        """Local socket state, not a live printer health check."""
        return self._socket is not None

    def connect(self) -> None:
        """Open a TCP session only when needed; this sends no LJ3 command."""
        with self._lock:
            if self.connected:
                return
            self.settings.validate()
            self._emit("STATUS", f"Connecting to {self.settings.ip}:{self.settings.port}")
            try:
                self._socket = self._socket_factory(
                    (self.settings.ip, self.settings.port), timeout=self.settings.timeout
                )
                self._parser = FrameParser()
            except OSError as exc:
                self._emit("ERROR", f"TCP connection failed: {exc}")
                raise CommunicationError(f"TCP connection failed: {exc}") from exc
            self._emit("STATUS", "Connected (TCP only; printer identity/readiness unverified)")

    def disconnect(self) -> None:
        with self._lock:
            if self._socket is not None:
                connection, self._socket = self._socket, None
                self._parser = FrameParser()
                try:
                    connection.close()
                except OSError as exc:
                    self._emit("ERROR", f"Socket close failed: {exc}")
                self._emit("STATUS", "Disconnected")

    def send_command(
        self, command: str, text: str | None = None, *, write_safety_confirmed: bool = False,
        command_echo_disabled_confirmed: bool = False,
    ) -> Frame | None:
        """Send one allowlisted command on the current session; never reconnect/retry here."""
        wire = build_command(command, text)
        if command == "=ET" and not write_safety_confirmed:
            raise ValueError("Confirm printing is stopped, print triggers are inhibited, and no other ExternText writer is active.")
        if command == "=ET" and not command_echo_disabled_confirmed:
            raise ValueError("Confirm printer command echo (!EM) is disabled before same-session write/readback verification.")
        with self._lock:
            if self._socket is None:
                raise CommunicationError("Not connected; call connect explicitly.")
            started = time.monotonic()
            deadline = started + self.settings.timeout
            try:
                self._socket.settimeout(self.settings.timeout)
                self._emit("TX", "Attempting transmission; delivery not yet known", wire)
                self._socket.sendall(wire)
                if command == "=ET":
                    elapsed = (time.monotonic() - started) * 1000
                    self._emit("TIMING", "Write frame submitted; printer acceptance is not acknowledged.",
                               elapsed_ms=elapsed)
                    self._emit("RESULT", "SENT - UNVERIFIED. No ordinary ACK is specified; read back separately.")
                    return None
                expected_reply = {"?ET": "=ET", "?RS": "=RS"}[command]
                return self._read_response_frame(expected_reply, deadline, started)
            except ProtocolError as exc:
                elapsed = (time.monotonic() - started) * 1000
                self._emit("TIMING", f"{command} ended with a protocol error.", elapsed_ms=elapsed)
                self._emit("ERROR", str(exc))
                self.disconnect()
                raise
            except TimeoutError as exc:
                elapsed = (time.monotonic() - started) * 1000
                message = f"No complete response to {command} before the {self.settings.timeout:g}-second deadline. No automatic retry."
                self._emit("TIMING", f"{command} ended without a complete response.", elapsed_ms=elapsed)
                self._emit("ERROR", message, elapsed_ms=elapsed)
                self.disconnect()
                raise ResponseTimeout(message) from exc
            except CommunicationError as exc:
                elapsed = (time.monotonic() - started) * 1000
                self._emit("TIMING", f"{command} ended with a communication/device error.", elapsed_ms=elapsed)
                self._emit("ERROR", str(exc), elapsed_ms=elapsed)
                self.disconnect()
                raise
            except OSError as exc:
                elapsed = (time.monotonic() - started) * 1000
                message = f"TCP failure: {exc}. Delivery may be partial or unknown; no automatic retry."
                self._emit("TIMING", f"{command} ended with a transport error.", elapsed_ms=elapsed)
                self._emit("ERROR", message, elapsed_ms=elapsed)
                self.disconnect()
                raise CommunicationError(message) from exc

    def _read_response_frame(self, expected: str, deadline: float, started: float) -> Frame:
        total = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"No matching {expected} before deadline")
            assert self._socket is not None
            self._socket.settimeout(remaining)
            chunk = self._socket.recv(4096)
            if not chunk:
                message = f"Peer closed before a complete {expected} reply."
                raise CommunicationError(message)
            self._emit("RX", "Received TCP bytes", chunk)
            total += len(chunk)
            if total > 65536:
                raise ProtocolError(f"Too much data while awaiting {expected}.")
            matches: list[Frame] = []
            for frame in self._parser.feed(chunk):
                if frame.command == "=FC":
                    raise DeviceError("Printer reported CRC failure; CRC was not enabled by this client.")
                if frame.command == "=RS":
                    status = decode_printer_status(frame)
                    if frame.command != expected and status.error:
                        raise DeviceError(f"Printer error {status.error}; consult printer display.")
                if frame.command == expected:
                    if expected == "=ET":
                        decode_external_text(frame)
                    else:
                        decode_printer_status(frame)
                    matches.append(frame)
                else:
                    self._emit("NOTICE", f"Unsolicited/unmatched {frame.command}; not accepted as {expected}.", frame.raw)
            if len(matches) > 1:
                raise ProtocolError(f"Multiple {expected} frames in one receive batch; ambiguous response.")
            if matches:
                if self._parser.incomplete:
                    raise ProtocolError(f"Incomplete frame followed {expected}; response is ambiguous.")
                elapsed = (time.monotonic() - started) * 1000
                self._emit("TIMING", f"Complete {expected} response received.", elapsed_ms=elapsed)
                return matches[0]

    def set_external_text(
        self, text: str, *, write_safety_confirmed: bool = False,
        command_echo_disabled_confirmed: bool = False,
    ) -> None:
        """Submit one ET write and keep the session for an explicit later readback."""
        build_command("=ET", text)
        if not write_safety_confirmed:
            raise ValueError("Confirm printing is stopped, print triggers are inhibited, and no other ExternText writer is active.")
        if not command_echo_disabled_confirmed:
            raise ValueError("Confirm printer command echo (!EM) is disabled before same-session write/readback verification.")
        with self._lock:
            self._write_session = None
            self._write_value = None
            if not self.connected:
                self.connect()
            self.send_command("=ET", text, write_safety_confirmed=True,
                              command_echo_disabled_confirmed=True)
            self._write_session = self._socket
            self._write_value = text

    def get_external_text(self) -> str:
        with self._lock:
            if not self.connected:
                self.connect()
            frame = self.send_command("?ET")
            assert frame is not None
            return decode_external_text(frame)

    def get_printer_status(self) -> PrinterStatus:
        with self._lock:
            if not self.connected:
                self.connect()
            frame = self.send_command("?RS")
            assert frame is not None
            return decode_printer_status(frame)

    def verify_external_text(self, expected: str) -> Verification:
        build_command("=ET", expected)  # Validation only; never sends another write.
        with self._lock:
            if self._write_value != expected:
                raise ValueError("Verification must match the most recent ET write in this client session.")
            if self._socket is None or self._write_session is not self._socket:
                raise CommunicationError("Same TCP session as the write is no longer available; no readback command sent.")
            result = Verification(expected, self.get_external_text())
        self._emit("RESULT", f"{'VERIFIED (exact ?ET readback)' if result.matched else 'MISMATCH'}: "
                   f"expected={result.expected!r}, returned={result.actual!r}. Physical printing is unverified.")
        return result
