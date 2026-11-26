"""Pure protocol functions derived from the supplied JET3 manuals.

Normal ExternText remains printable ASCII; experimental Mailmode functions are
separate, fixed to one Thai Field 1 hypothesis, and never enter the ASCII path.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


class ProtocolError(ValueError):
    """Received bytes do not meet the supported LJ3 protocol contract."""


def encode_external_text(text: str) -> bytes:
    if not isinstance(text, str) or not 1 <= len(text) <= 256:
        raise ValueError("ExternText must contain 1-256 characters; empty writes are disabled.")
    if any(not 0x20 <= ord(char) <= 0x7E for char in text):
        raise ValueError("Only printable ASCII is supported; no controls or Unicode.")
    if "\\" in text:
        raise ValueError("Literal backslashes are disabled: ET escaping is not documented.")
    payload = text.replace("^", "\\^").encode("ascii")
    if len(payload) > 256:
        raise ValueError("Escaped payload exceeds the conservative 256-byte limit.")
    return payload


def encode_experimental_iso8859_11(text: str) -> bytes:
    """Encode a one-off experimental hypothesis; this is not a supported printer mode."""
    if not isinstance(text, str) or not 1 <= len(text) <= 256:
        raise ValueError("Experimental ExternText must contain 1-256 characters.")
    try:
        payload = text.encode("iso8859_11", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("Text is not representable in experimental ISO-8859-11.") from exc
    if len(payload) > 256 or any(value < 0x20 or value == 0x7F for value in payload):
        raise ValueError("Experimental ISO-8859-11 payload contains a protocol control or exceeds 256 bytes.")
    return payload


def build_experimental_iso8859_11_frame(text: str) -> bytes:
    """Build a raw ISO-8859-11 frame without enabling it in the normal ASCII allowlist."""
    return b"^0=ET" + encode_experimental_iso8859_11(text) + b"\r"


EXPERIMENTAL_THAI_FIELD1_TEXT = "สีเทานก"


def encode_experimental_thai_field1_iso8859_11_hypothesis(text: str) -> bytes:
    """Return the one-byte hypothesis for ISOB_Thai; font mapping is unverified."""
    if text != EXPERIMENTAL_THAI_FIELD1_TEXT:
        raise ValueError("The experimental Mailmode path is limited to the fixed Thai test text.")
    return encode_experimental_iso8859_11(text)


def build_experimental_thai_mailmode_field1_frame(text: str) -> bytes:
    """Build one record-0, one-field =MR frame; it does not touch =ET/Field 0."""
    payload = encode_experimental_thai_field1_iso8859_11_hypothesis(text)
    if any(value in payload for value in (0x09, 0x0A, 0x0D, 0x5E)):
        raise ValueError("Experimental Mailmode field contains a delimiter, terminator, or caret.")
    return b"^0=MR0\t" + payload + b"\r"


def decode_experimental_iso8859_11_response(raw: bytes) -> bytes:
    """Validate an =ET response envelope and return its uninterpreted payload bytes."""
    if raw.endswith(b"\r\n"):
        raw = raw[:-1]
    if not raw.startswith(b"^") or not raw.endswith(b"\r"):
        raise ProtocolError("Expected a complete experimental ExternText frame ending in CR.")
    body = raw[1:-1]
    if len(body) >= 8 and body[:5].isdigit():
        size = int(body[:5])
        body = body[5:]
        if size != len(body) + 1:
            raise ProtocolError("Experimental response length header does not match bytes through CR.")
    if not body.startswith(b"0=ET"):
        raise ProtocolError("Expected response address 0 and command =ET.")
    payload = body[4:]
    if len(payload) > 512:
        raise ProtocolError("Experimental ExternText readback exceeds the supported response size.")
    return payload


def build_command(command: str, text: str | None = None) -> bytes:
    """Allowlist prevents the manual tool becoming an arbitrary printer console."""
    if command in {"?ET", "?RS", "?EX", "?JL", "?SM"} and text is None:
        return b"^0" + command.encode("ascii") + b"\r"
    if command == "=ET" and text is not None:
        return b"^0=ET" + encode_external_text(text) + b"\r"
    raise ValueError("Supported commands are =ET with text, or ?ET/?RS/?EX/?JL without parameters.")


@dataclass(frozen=True)
class Frame:
    command: str
    payload: bytes
    raw: bytes


def parse_frame(raw: bytes) -> Frame:
    if not raw.startswith(b"^0") or not raw.endswith(b"\r"):
        raise ProtocolError("Expected ^, ASCII address 0, and final CR.")
    body = raw[2:-1]
    if body[:1].isdigit():
        if len(body) < 8 or not body[:5].isdigit():
            raise ProtocolError("Invalid five-digit LJ3 length header.")
        size = int(body[:5])
        body = body[5:]
        if size != len(body) + 1:
            raise ProtocolError("LJ3 length header does not match bytes through CR.")
    if not re.fullmatch(rb"[!?=*$][A-Z0-9]{2}", body[:3]):
        raise ProtocolError("Invalid command group or two-character command.")
    payload = body[3:]
    for index, value in enumerate(payload):
        if value != 9 and not 0x20 <= value <= 0x7E:
            raise ProtocolError("Non-ASCII or control byte in frame payload.")
        if value == 0x5E and (index == 0 or payload[index - 1] != 0x5C):
            raise ProtocolError("Unescaped caret in frame payload.")
    return Frame(body[:3].decode("ascii"), payload, raw)


def decode_external_text(frame: Frame) -> str:
    if frame.command != "=ET":
        raise ProtocolError("Expected =ET readback.")
    payload = frame.payload
    if len(payload) > 512:
        raise ProtocolError("ExternText readback exceeds supported ASCII size.")
    chars: list[str] = []
    index = 0
    while index < len(payload):
        value = payload[index]
        if value == 0x5C:
            if payload[index:index + 2] != b"\\^":
                raise ProtocolError("Unsupported backslash escape in ExternText readback.")
            chars.append("^")
            index += 2
            continue
        if not 0x20 <= value <= 0x7E:
            raise ProtocolError("Readback is not printable ASCII ExternText.")
        chars.append(chr(value))
        index += 1
    if len(chars) > 256:
        raise ProtocolError("ExternText readback exceeds 256 characters.")
    return "".join(chars)  # Preserve spaces; never silently strip or normalize.


@dataclass(frozen=True)
class PrinterStatus:
    """The five documented =RS parameters plus opaque extra wire fields."""

    nozzle_state: int
    machine_state: int
    error: int
    headcover: int
    act_speed: Decimal
    additional_parameters: tuple[bytes, ...] = ()
    additional_parameters_raw: bytes = b""


@dataclass(frozen=True)
class ExternState:
    """Only documented =EX fields are decoded; reserved fields stay opaque."""

    actual_speed: Decimal
    inputs: int
    max_speed: Decimal
    direction: int
    printgo: int
    additional_parameters: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class MailStatus:
    """The five documented =SM fields and any unrecognized trailing values."""

    fifo_depth: int
    fifo_entries: int
    last_started_print_no: int
    stop_at_no: int
    last_started_print_no_was_finished: int
    additional_parameters: tuple[bytes, ...] = ()


def decode_mail_status(frame: Frame) -> MailStatus:
    """Decode the manual's five integer =SM parameters without guessing extras."""
    if frame.command != "=SM":
        raise ProtocolError("Expected =SM Mail Status.")
    fields = re.split(rb"[\t ]+", frame.payload.strip())
    if len(fields) < 5 or any(re.fullmatch(rb"[0-9]+", item) is None for item in fields[:5]):
        raise ProtocolError("Malformed =SM status: expected five nonnegative decimal parameters.")
    values = tuple(int(item) for item in fields[:5])
    fifo_depth, fifo_entries, last_started, stop_at, finished = values
    if fifo_depth <= 0 or fifo_entries > fifo_depth:
        raise ProtocolError("Malformed =SM status: FIFO entry count is outside its reported depth.")
    return MailStatus(fifo_depth, fifo_entries, last_started, stop_at, finished,
                      tuple(fields[5:]))


def decode_printer_status(frame: Frame) -> PrinterStatus:
    """Decode the five manual-defined fields; retain extras without interpretation."""
    if frame.command != "=RS":
        raise ProtocolError("Expected =RS printer status.")
    fields = list(re.finditer(rb"[^\t ]+", frame.payload))
    if len(fields) < 5:
        raise ProtocolError("Malformed =RS status: expected at least five parameters.")
    documented = [match.group() for match in fields[:5]]
    if any(re.fullmatch(rb"[0-9]+", field) is None for field in documented[:4]):
        raise ProtocolError("Malformed =RS status: first four parameters must be decimal integers.")
    try:
        nozzle_state, machine_state, error, headcover = (int(field) for field in documented[:4])
        speed_text = documented[4].decode("ascii")
        if re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", speed_text) is None:
            raise InvalidOperation
        act_speed = Decimal(speed_text)
    except (UnicodeDecodeError, InvalidOperation, ValueError) as exc:
        raise ProtocolError("Malformed =RS status: invalid documented numeric parameter.") from exc
    additional = tuple(match.group() for match in fields[5:])
    raw_tail = frame.payload[fields[4].end():] if len(fields) > 5 else b""
    return PrinterStatus(nozzle_state, machine_state, error, headcover, act_speed,
                         additional, raw_tail)


def decode_extern_state(frame: Frame) -> ExternState:
    """Decode the documented =EX fields, including the manual's Par6 PrintGo."""
    if frame.command != "=EX":
        raise ProtocolError("Expected =EX extern-state response.")
    fields = re.split(rb"[\t ]+", frame.payload.strip())
    if len(fields) < 6:
        raise ProtocolError("Malformed =EX status: expected documented Par1-Par4 and Par6 fields.")
    try:
        speed = Decimal(fields[0].decode("ascii"))
        inputs = int(fields[1])
        max_speed = Decimal(fields[2].decode("ascii"))
        direction = int(fields[3])
        printgo = int(fields[5])
    except (UnicodeDecodeError, InvalidOperation, ValueError) as exc:
        raise ProtocolError("Malformed =EX status: invalid documented numeric parameter.") from exc
    if not speed.is_finite() or not max_speed.is_finite():
        raise ProtocolError("Malformed =EX status: speed must be finite.")
    if inputs < 0 or inputs > 2**17 or direction not in (0, 1) or printgo not in (0, 1):
        raise ProtocolError("Malformed =EX status: documented field is outside its valid range.")
    return ExternState(speed, inputs, max_speed, direction, printgo,
                       tuple(fields[6:]))


def decode_loaded_job(frame: Frame) -> str:
    """Decode the read-only response to ?JL; never builds the =JL load command."""
    if frame.command != "=JL":
        raise ProtocolError("Expected =JL loaded-job response.")
    try:
        return frame.payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("Loaded-job response is not ASCII.") from exc


class FrameParser:
    """Bounded incremental CR parser; tolerates a single optional LF after each CR."""

    def __init__(self, max_frame_bytes: int = 4096):
        self.max_frame_bytes = max_frame_bytes
        self._buffer = bytearray()
        self._after_cr = False

    def feed(self, data: bytes) -> list[Frame]:
        frames: list[Frame] = []
        for value in data:
            if self._after_cr:
                self._after_cr = False
                if value == 0x0A:
                    continue
            if not self._buffer and value != 0x5E:
                raise ProtocolError("Unexpected bytes outside a frame (padding is unsupported).")
            self._buffer.append(value)
            if len(self._buffer) > self.max_frame_bytes:
                raise ProtocolError("Receive frame exceeds the configured bound.")
            if value == 0x0D:
                frames.append(parse_frame(bytes(self._buffer)))
                self._buffer.clear()
                self._after_cr = True
        return frames

    @property
    def incomplete(self) -> bool:
        return bool(self._buffer)
