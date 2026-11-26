import unittest

from lj3.protocol import (FrameParser, ProtocolError, build_command,
                          build_experimental_iso8859_11_frame,
                          build_experimental_thai_mailmode_field1_frame,
                          decode_experimental_iso8859_11_response,
                          decode_mail_status,
                          decode_external_text, decode_extern_state,
                          decode_loaded_job, decode_printer_status,
                          encode_experimental_iso8859_11,
                          encode_experimental_thai_field1_iso8859_11_hypothesis,
                          parse_frame)


class ProtocolTests(unittest.TestCase):
    def test_documented_framing_and_ascii_address(self):
        self.assertEqual(build_command("=ET", "BLUE"), bytes.fromhex("5E 30 3D 45 54 42 4C 55 45 0D"))
        self.assertEqual(build_command("?ET"), b"^0?ET\r")
        self.assertEqual(build_command("?RS"), b"^0?RS\r")
        self.assertEqual(build_command("?EX"), b"^0?EX\r")
        self.assertEqual(build_command("?JL"), b"^0?JL\r")
        self.assertEqual(build_command("?SM"), b"^0?SM\r")

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

    def test_isolated_iso8859_11_experimental_encoding_and_frame(self):
        text = "สีเทานก"
        payload = bytes.fromhex("CA D5 E0 B7 D2 B9 A1")
        self.assertEqual(encode_experimental_iso8859_11(text), payload)
        self.assertEqual(build_experimental_iso8859_11_frame(text), b"^0=ET" + payload + b"\r")
        # The normal command builder remains ASCII-only and rejects the same text.
        with self.assertRaises(ValueError):
            build_command("=ET", text)

    def test_experimental_response_decoder_preserves_raw_payload_bytes(self):
        payload = bytes.fromhex("CA D5 E0 B7 D2 B9 A1")
        raw = b"^0=ET" + payload + b"\r"
        self.assertEqual(decode_experimental_iso8859_11_response(raw), payload)
        self.assertEqual(decode_experimental_iso8859_11_response(raw + b"\n"), payload)
        with self.assertRaises(ProtocolError):
            decode_experimental_iso8859_11_response(b"^0=ET" + payload)
        with self.assertRaises(ProtocolError):
            decode_experimental_iso8859_11_response(b"^0=RS" + payload + b"\r")

    def test_experimental_mailmode_field1_preview_isolated_from_et(self):
        text = "สีเทานก"
        payload = bytes.fromhex("CA D5 E0 B7 D2 B9 A1")
        frame = bytes.fromhex("5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D")
        self.assertEqual(encode_experimental_thai_field1_iso8859_11_hypothesis(text), payload)
        self.assertEqual(build_experimental_thai_mailmode_field1_frame(text), frame)
        for codec in ("iso8859_11", "tis-620", "cp874"):
            self.assertEqual(text.encode(codec), payload)
        with self.assertRaises(ValueError):
            encode_experimental_thai_field1_iso8859_11_hypothesis("สีแดง")
        # The existing global ExternText command remains ASCII-only and unchanged.
        with self.assertRaises(ValueError):
            build_command("=ET", text)

    def test_mail_status_decodes_five_manual_parameters_and_preserves_extras(self):
        status = decode_mail_status(parse_frame(b"^0=SM256\t1\t0\t0\t0\tX\r"))
        self.assertEqual((status.fifo_depth, status.fifo_entries,
                          status.last_started_print_no, status.stop_at_no,
                          status.last_started_print_no_was_finished), (256, 1, 0, 0, 0))
        self.assertEqual(status.additional_parameters, (b"X",))

    def test_mail_status_rejects_malformed_or_out_of_range_fields(self):
        for wire in (b"^0=SM256\t0\t0\t0\r", b"^0=SMx\t0\t0\t0\t0\r",
                     b"^0=SM10\t11\t0\t0\t0\r", b"^0=SM0\t0\t0\t0\t0\r"):
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                decode_mail_status(parse_frame(wire))

    def test_command_allowlist(self):
        for command, payload in (("!GO", None), ("=JL", "job"),
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

    def test_documented_status_fields_and_opaque_extra_parameters(self):
        status = decode_printer_status(parse_frame(b"^0=RS4\t4\t0\t0\t230\t0\r"))
        self.assertEqual((status.nozzle_state, status.machine_state, status.error,
                          status.headcover, status.act_speed), (4, 4, 0, 0, 230))
        self.assertEqual(status.additional_parameters, (b"0",))
        self.assertEqual(status.additional_parameters_raw, b"\t0")

    def test_status_accepts_space_separated_manual_example(self):
        status = decode_printer_status(parse_frame(b"^0=RS2 6 0 0 0\r"))
        self.assertEqual((status.nozzle_state, status.machine_state, status.error,
                          status.headcover, status.act_speed), (2, 6, 0, 0, 0))
        self.assertEqual(status.additional_parameters, ())

    def test_status_requires_five_valid_documented_fields(self):
        for wire in (b"^0=RS4\t4\t0\t0\r", b"^0=RSx\t4\t0\t0\t230\r",
                     b"^0=RS4\t4\tbad\t0\t230\r", b"^0=RS4\t4\t0\t0\tfast\r"):
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                decode_printer_status(parse_frame(wire))

    def test_extern_state_parses_documented_printgo_field_and_opaque_reserved_values(self):
        state = decode_extern_state(parse_frame(b"^0=EX10\t0\t120\t1\t0\t0\t0\t0\t0\r"))
        self.assertEqual((state.actual_speed, state.inputs, state.max_speed,
                          state.direction, state.printgo), (10, 0, 120, 1, 0))
        self.assertEqual(state.additional_parameters, (b"0", b"0", b"0"))

    def test_extern_state_rejects_missing_or_invalid_documented_values(self):
        for wire in (b"^0=EX1\t0\t2\t1\t0\r", b"^0=EX1\t0\t2\t2\t0\t0\r",
                     b"^0=EX1\t0\t2\t1\t0\t2\r"):
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                decode_extern_state(parse_frame(wire))

    def test_loaded_job_decoder_is_read_only_response_only(self):
        self.assertEqual(decode_loaded_job(parse_frame(b"^0=JLFFSDISK\\JOBS\\TEST.JOB\r")),
                         "FFSDISK\\JOBS\\TEST.JOB")

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
