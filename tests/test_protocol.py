import unittest

from lj3.protocol import (FrameParser, ProtocolError, build_command,
                          decode_external_text, parse_frame)


class ProtocolTests(unittest.TestCase):
    def test_documented_framing_and_ascii_address(self):
        self.assertEqual(build_command("=ET", "BLUE"), bytes.fromhex("5E 30 3D 45 54 42 4C 55 45 0D"))
        self.assertEqual(build_command("?ET"), b"^0?ET\r")

    def test_no_implicit_whitespace_or_lf(self):
        self.assertEqual(build_command("=ET", " BLUE "), b"^0=ET BLUE \r")

    def test_caret_escape_roundtrip(self):
        wire = build_command("=ET", "A^B")
        self.assertEqual(wire, b"^0=ETA\\^B\r")
        self.assertEqual(decode_external_text(parse_frame(wire)), "A^B")

    def test_exact_length_limits(self):
        self.assertEqual(len(build_command("=ET", "A" * 256)), 262)
        for text in ("A" * 257, "^" * 129, ""):
            with self.subTest(text_length=len(text)), self.assertRaises(ValueError):
                build_command("=ET", text)

    def test_injection_controls_unicode_and_backslash_rejected(self):
        for text in ("RED\r^0!GO", "BLUE\n", "A\tB", "\0", "\x1b", "\x7f", "สีแดง", "é", "😀", "A\\B"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                build_command("=ET", text)

    def test_command_allowlist(self):
        for command, payload in (("!GO", None), ("=JL", "job"), ("?RS", None),
                                 ("?ET", "unexpected"), ("=ET", None), ("?ET\r^0!GO", None)):
            with self.subTest(command=command), self.assertRaises(ValueError):
                build_command(command, payload)

    def test_every_tcp_split_point_including_optional_lf(self):
        wire = b"^0=ETBLUE\r\n^0=ETRED\r\n"
        for split in range(len(wire) + 1):
            with self.subTest(split=split):
                parser = FrameParser()
                frames = parser.feed(wire[:split]) + parser.feed(wire[split:])
                self.assertEqual([decode_external_text(frame) for frame in frames], ["BLUE", "RED"])
                self.assertFalse(parser.incomplete)

    def test_single_byte_fragments_and_spaces(self):
        parser = FrameParser()
        frames = []
        for value in b"^0=ET RED \r":
            frames.extend(parser.feed(bytes([value])))
        self.assertEqual(decode_external_text(frames[0]), " RED ")

    def test_length_header_includes_cr(self):
        self.assertEqual(decode_external_text(parse_frame(b"^000008=ETBLUE\r")), "BLUE")
        # Published length-mode example, protocol p.7 (four TABs).
        self.assertEqual(parse_frame(b"^000013=RS2\t6\t0\t0\t0\r").command, "=RS")
        with self.assertRaises(ProtocolError):
            parse_frame(b"^000007=ETBLUE\r")

    def test_invalid_frames(self):
        cases = (b"^1=ETBLUE\r", b"^\x00=ETBLUE\r", b"^0=ETBLUE\n",
                 b"^0=ETB^LUE\r", b"^0008=ETBLUE\r", b"^0XETBLUE\r",
                 b"^0=ET\xff\r", b"^0=ET\nRED\r", b"^0=\r")
        for wire in cases:
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                parse_frame(wire)

    def test_noise_padding_and_lf_without_cr_rejected(self):
        for wire in (b"garbage", b"\n", b"^0=ETRED\r  ", b"^0=ETRED\r\n\n"):
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                FrameParser().feed(wire)

    def test_oversize_unterminated_frame_rejected(self):
        with self.assertRaises(ProtocolError):
            FrameParser(max_frame_bytes=12).feed(b"^0=ET" + b"A" * 8)

    def test_incomplete_frame_remains_pending(self):
        parser = FrameParser()
        self.assertEqual(parser.feed(b"^0=ETBLUE"), [])
        self.assertTrue(parser.incomplete)

    def test_empty_readback_is_observable_but_not_writable(self):
        self.assertEqual(decode_external_text(parse_frame(b"^0=ET\r")), "")

    def test_unsupported_readback_rejected(self):
        for wire in (b"^0=ETRED\t\r", b"^0=ETA\\B\r", b"^0=ET" + b"A" * 257 + b"\r"):
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                decode_external_text(parse_frame(wire))
