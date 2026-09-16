"""Pure protocol functions derived from the supplied interface manual, pp.4,7,8,11.

Phase 1 deliberately supports only printable ASCII ExternText and address '0'.
"""

from dataclasses import dataclass
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


def build_command(command: str, text: str | None = None) -> bytes:
    """Allowlist prevents the manual tool becoming an arbitrary printer console."""
    if command == "?ET" and text is None:
        return b"^0?ET\r"
    if command == "=ET" and text is not None:
        return b"^0=ET" + encode_external_text(text) + b"\r"
    raise ValueError("Phase 1 permits only =ET with text or ?ET without parameters.")


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
