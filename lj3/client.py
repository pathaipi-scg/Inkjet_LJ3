"""Explicit LJ3 TCP session with serialized commands; no retries or background I/O."""

from dataclasses import dataclass
from datetime import datetime, timezone
import socket
import threading
import time
from typing import Callable

from .config import Settings
from .locking import printer_lock
from .protocol import (Frame, FrameParser, PrinterStatus, ProtocolError, build_command,
                       ExternState, decode_external_text, decode_extern_state,
                       decode_experimental_iso8859_11_response,
                       build_experimental_iso8859_11_frame,
                       decode_loaded_job, decode_printer_status,
                       MailStatus, decode_mail_status,
                       build_experimental_thai_mailmode_field1_frame)


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
                expected_reply = {"?ET": "=ET", "?RS": "=RS", "?EX": "=EX",
                                  "?JL": "=JL", "?SM": "=SM"}[command]
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
                    elif expected == "=EX":
                        decode_extern_state(frame)
                    elif expected == "=JL":
                        decode_loaded_job(frame)
                    elif expected == "=SM":
                        decode_mail_status(frame)
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
        with printer_lock(self.settings.ip, self.settings.port):
            with self._lock:
                self._write_session = None
                self._write_value = None
                if not self.connected:
                    self.connect()
                self.send_command("=ET", text, write_safety_confirmed=True,
                                  command_echo_disabled_confirmed=True)
                self._write_session = self._socket
                self._write_value = text

    def set_external_text_experimental_iso8859_11(
        self, text: str, *, write_safety_confirmed: bool = False,
        command_echo_disabled_confirmed: bool = False,
    ) -> bytes:
        """Submit one raw ISO-8859-11 hypothesis; never used by normal ASCII writes."""
        wire = build_experimental_iso8859_11_frame(text)
        if not write_safety_confirmed or not command_echo_disabled_confirmed:
            raise ValueError("Experimental write requires explicit safety and echo confirmations.")
        with printer_lock(self.settings.ip, self.settings.port):
            with self._lock:
                if self._socket is None:
                    raise CommunicationError("Not connected; experimental send requires the preflight session.")
                started = time.monotonic()
                self._emit("TX", "EXPERIMENTAL ISO-8859-11 hypothesis; one raw =ET submission", wire)
                try:
                    self._socket.settimeout(self.settings.timeout)
                    self._socket.sendall(wire)
                except OSError as exc:
                    elapsed = (time.monotonic() - started) * 1000
                    message = f"Experimental TCP write failed; delivery may be partial or unknown ({type(exc).__name__})."
                    self._emit("TIMING", "Experimental write ended with a transport error.", elapsed_ms=elapsed)
                    self._emit("ERROR", message)
                    self.disconnect()
                    raise CommunicationError(message) from None
                elapsed = (time.monotonic() - started) * 1000
                self._emit("TIMING", "Experimental write frame submitted; printer acceptance is not acknowledged.",
                           elapsed_ms=elapsed)
                return wire

    def send_experimental_thai_mailmode_field1(
        self, text: str, *, production_stopped_confirmed: bool = False,
        triggers_inhibited_confirmed: bool = False,
        sole_writer_confirmed: bool = False,
        command_echo_disabled_confirmed: bool = False,
        empty_fifo_preflight_confirmed: bool = False,
    ) -> bytes:
        """Submit one fixed Field 1 =MR hypothesis on an already-open session."""
        wire = build_experimental_thai_mailmode_field1_frame(text)
        if not all((production_stopped_confirmed, triggers_inhibited_confirmed,
                    sole_writer_confirmed, command_echo_disabled_confirmed,
                    empty_fifo_preflight_confirmed)):
            raise ValueError("Experimental Mailmode write requires all safety and empty-FIFO confirmations.")
        with printer_lock(self.settings.ip, self.settings.port):
            with self._lock:
                if self._socket is None:
                    raise CommunicationError("Not connected; Mailmode send requires the preflight session.")
                started = time.monotonic()
                self._emit("TX", "EXPERIMENTAL Field 1 Mailmode record; one raw =MR submission", wire)
                try:
                    self._socket.settimeout(self.settings.timeout)
                    self._socket.sendall(wire)
                except OSError as exc:
                    elapsed = (time.monotonic() - started) * 1000
                    message = ("Experimental Mailmode transmission failed; delivery may be partial or unknown; "
                               "no retry.")
                    self._emit("TIMING", "Experimental =MR write ended with a transport error.",
                               elapsed_ms=elapsed)
                    self._emit("ERROR", f"{message} ({type(exc).__name__}).")
                    self.disconnect()
                    raise CommunicationError(message) from None
                elapsed = (time.monotonic() - started) * 1000
                self._emit("TIMING", "Experimental =MR frame submitted; FIFO acceptance is unverified.",
                           elapsed_ms=elapsed)
                return wire

    def get_mail_status(self) -> MailStatus:
        with self._lock:
            if not self.connected:
                self.connect()
            frame = self.send_command("?SM")
            assert frame is not None
            return decode_mail_status(frame)

    def get_external_text_experimental_raw(self) -> tuple[bytes, bytes]:
        """Issue one read-only ?ET and return the complete raw frame and payload bytes."""
        wire = build_command("?ET")
        with self._lock:
            if self._socket is None:
                raise CommunicationError("Not connected; experimental read requires the original session.")
            started = time.monotonic()
            deadline = started + self.settings.timeout
            try:
                self._socket.settimeout(self.settings.timeout)
                self._emit("TX", "Read experimental ExternText bytes", wire)
                self._socket.sendall(wire)
                raw = self._receive_raw_cr_frame(deadline)
                payload = decode_experimental_iso8859_11_response(raw)
                elapsed = (time.monotonic() - started) * 1000
                self._emit("TIMING", "Complete raw experimental =ET response received.", elapsed_ms=elapsed)
                return raw, payload
            except ProtocolError as exc:
                self._emit("ERROR", str(exc))
                self.disconnect()
                raise
            except TimeoutError as exc:
                elapsed = (time.monotonic() - started) * 1000
                message = f"No complete experimental =ET response before the {self.settings.timeout:g}-second deadline; no retry."
                self._emit("TIMING", "Experimental readback ended without a complete response.", elapsed_ms=elapsed)
                self._emit("ERROR", message)
                self.disconnect()
                raise ResponseTimeout(message) from exc
            except CommunicationError as exc:
                self._emit("ERROR", str(exc))
                self.disconnect()
                raise
            except OSError as exc:
                message = f"Experimental readback transport failed ({type(exc).__name__}); no retry."
                self._emit("ERROR", message)
                self.disconnect()
                raise CommunicationError(message) from None

    def _receive_raw_cr_frame(self, deadline: float) -> bytes:
        received = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Experimental response deadline expired.")
            assert self._socket is not None
            self._socket.settimeout(remaining)
            chunk = self._socket.recv(4096)
            if not chunk:
                raise CommunicationError("Peer closed before a complete experimental =ET frame.")
            self._emit("RX", "Raw experimental response bytes", chunk)
            received.extend(chunk)
            if len(received) > 65536:
                raise ProtocolError("Experimental response exceeded the receive bound.")
            cr_index = received.find(b"\r")
            if cr_index >= 0:
                raw = bytes(received[:cr_index + 1])
                trailing = bytes(received[cr_index + 1:])
                if trailing not in (b"", b"\n"):
                    raise ProtocolError("Unexpected bytes followed the experimental =ET response frame.")
                return raw + trailing

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

    def get_extern_state(self) -> ExternState:
        with self._lock:
            if not self.connected:
                self.connect()
            frame = self.send_command("?EX")
            assert frame is not None
            return decode_extern_state(frame)

    def get_loaded_job(self) -> str:
        with self._lock:
            if not self.connected:
                self.connect()
            frame = self.send_command("?JL")
            assert frame is not None
            return decode_loaded_job(frame)

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
