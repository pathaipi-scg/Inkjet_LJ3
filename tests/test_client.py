import unittest
from unittest.mock import Mock, patch

from lj3.client import CommunicationError, DeviceError, LJ3Client, ResponseTimeout
from lj3.config import Settings
from lj3.protocol import ProtocolError


class FakeSocket:
    def __init__(self, chunks=(), send_error=None):
        self.chunks = list(chunks)
        self.send_error = send_error
        self.sent = []
        self.closed = False
        self.recv_count = 0
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, data):
        self.sent.append(data)
        if self.send_error:
            raise self.send_error

    def recv(self, size):
        self.recv_count += 1
        if not self.chunks:
            raise TimeoutError()
        item = self.chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


class ClientTests(unittest.TestCase):
    def make_client(self, sock):
        factory = Mock(return_value=sock)
        events = []
        client = LJ3Client(Settings("127.0.0.1"), events.append, socket_factory=factory)
        return client, factory, events

    def test_constructor_performs_no_network_io(self):
        client, factory, events = self.make_client(FakeSocket())
        factory.assert_not_called()
        self.assertFalse(client.connected)
        self.assertEqual(events, [])

    def test_connect_is_idempotent_and_tcp_only(self):
        sock = FakeSocket()
        client, factory, _ = self.make_client(sock)
        client.connect()
        client.connect()
        self.assertTrue(client.connected)
        self.assertEqual(sock.sent, [])
        self.assertEqual(sock.recv_count, 0)
        self.assertEqual(factory.call_count, 1)
        client.disconnect()
        self.assertTrue(sock.closed)

    def test_write_requires_both_policy_confirmations_before_network(self):
        client, factory, _ = self.make_client(FakeSocket())
        with self.assertRaises(ValueError):
            client.set_external_text("RED")
        with self.assertRaisesRegex(ValueError, "echo"):
            client.set_external_text("RED", write_safety_confirmed=True)
        factory.assert_not_called()

    def test_invalid_send_never_connects(self):
        client, factory, _ = self.make_client(FakeSocket())
        with self.assertRaises(ValueError):
            client.set_external_text("BAD\r", write_safety_confirmed=True,
                                     command_echo_disabled_confirmed=True)
        factory.assert_not_called()

    def test_write_sends_once_and_keeps_session_open_without_ack(self):
        sock = FakeSocket()
        client, _, events = self.make_client(sock)
        client.set_external_text("RED", write_safety_confirmed=True,
                                 command_echo_disabled_confirmed=True)
        self.assertEqual(sock.sent, [b"^0=ETRED\r"])
        self.assertEqual(sock.recv_count, 0)
        self.assertFalse(sock.closed)
        self.assertTrue(client.connected)
        self.assertTrue(any("UNVERIFIED" in event.message for event in events))
        self.assertTrue(any(event.kind == "TIMING" and event.elapsed_ms is not None for event in events))
        self.assertTrue(all(event.timestamp.endswith("+00:00") for event in events))

    def test_experimental_iso8859_11_transmit_and_raw_readback_same_session(self):
        payload = bytes.fromhex("CA D5 E0 B7 D2 B9 A1")
        raw_response = b"^0=ET" + payload + b"\r"
        sock = FakeSocket([raw_response[:9], raw_response[9:]])
        client, _, events = self.make_client(sock)
        client.connect()
        wire = client.set_external_text_experimental_iso8859_11(
            "สีเทานก", write_safety_confirmed=True,
            command_echo_disabled_confirmed=True)
        raw, returned = client.get_external_text_experimental_raw()
        self.assertEqual(wire, b"^0=ET" + payload + b"\r")
        self.assertEqual(sock.sent, [wire, b"^0?ET\r"])
        self.assertEqual(raw, raw_response)
        self.assertEqual(returned, payload)
        self.assertFalse(sock.closed)
        self.assertEqual(sum(event.kind == "TX" and event.data == wire for event in events), 1)
        self.assertTrue(any(event.kind == "RX" and event.data == raw_response[9:] for event in events))

    def test_experimental_encoding_rejects_missing_safety_and_never_connects(self):
        client, factory, _ = self.make_client(FakeSocket())
        with self.assertRaisesRegex(ValueError, "safety"):
            client.set_external_text_experimental_iso8859_11("สีเทานก")
        factory.assert_not_called()

    def test_experimental_mailmode_field1_sends_once_on_existing_session(self):
        sock = FakeSocket()
        client, factory, events = self.make_client(sock)
        with self.assertRaisesRegex(ValueError, "confirmations"):
            client.send_experimental_thai_mailmode_field1("สีเทานก")
        factory.assert_not_called()
        client.connect()
        wire = client.send_experimental_thai_mailmode_field1(
            "สีเทานก", production_stopped_confirmed=True,
            triggers_inhibited_confirmed=True, sole_writer_confirmed=True,
            command_echo_disabled_confirmed=True,
            empty_fifo_preflight_confirmed=True)
        self.assertEqual(wire, bytes.fromhex("5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D"))
        self.assertEqual(sock.sent, [wire])
        self.assertEqual(factory.call_count, 1)
        self.assertFalse(sock.closed)
        self.assertEqual(sum(event.kind == "TX" and event.data == wire for event in events), 1)

    def test_mail_status_is_read_only_and_fifo_clear_is_not_exposed(self):
        one = b"^0=SM256\t1\t0\t0\t0\r"
        sock = FakeSocket([one])
        client, _, _ = self.make_client(sock)
        client.connect()
        self.assertEqual(client.get_mail_status().fifo_entries, 1)
        self.assertEqual(sock.sent, [b"^0?SM\r"])
        self.assertFalse(hasattr(client, "flush_mail_fifo_for_experiment"))

    def test_fragmentation_and_unsolicited_frames(self):
        sock = FakeSocket([b"^0=RS2\t5\t0\t0\t0\r\n^0=E", b"TBLUE\r\n"])
        client, _, events = self.make_client(sock)
        self.assertEqual(client.get_external_text(), "BLUE")
        self.assertEqual(sock.sent, [b"^0?ET\r"])
        self.assertFalse(sock.closed)
        self.assertTrue(any(event.kind == "NOTICE" for event in events))
        self.assertEqual(sum(event.kind == "RX" for event in events), 2)

    def test_length_mode_response(self):
        client, _, _ = self.make_client(FakeSocket([b"^000008=ETBLUE\r"]))
        self.assertEqual(client.get_external_text(), "BLUE")

    def test_status_query_decodes_fields_and_opaque_extra_parameters(self):
        sock = FakeSocket([b"^0=RS4\t4\t0\t0\t230\t0\r"])
        client, _, events = self.make_client(sock)
        status = client.get_printer_status()
        self.assertEqual(sock.sent, [b"^0?RS\r"])
        self.assertEqual((status.nozzle_state, status.machine_state, status.error,
                          status.headcover, status.act_speed), (4, 4, 0, 0, 230))
        self.assertEqual(status.additional_parameters, (b"0",))
        self.assertFalse(sock.closed)
        self.assertTrue(any(event.elapsed_ms is not None for event in events if event.kind == "TIMING"))

    def test_extern_state_and_loaded_job_are_documented_read_only_queries(self):
        sock = FakeSocket([b"^0=EX10\t0\t120\t1\t0\t0\t0\r",
                           b"^0=JLFFSDISK\\JOBS\\TEST.JOB\r"])
        client, _, _ = self.make_client(sock)
        state = client.get_extern_state()
        job = client.get_loaded_job()
        self.assertEqual(state.printgo, 0)
        self.assertEqual(job, "FFSDISK\\JOBS\\TEST.JOB")
        self.assertEqual(sock.sent, [b"^0?EX\r", b"^0?JL\r"])
        self.assertFalse(sock.closed)

    def test_status_error_is_returned_for_display(self):
        client, _, _ = self.make_client(FakeSocket([b"^0=RS4\t4\t123\t0\t230\r"]))
        self.assertEqual(client.get_printer_status().error, 123)

    def test_verification_match_and_mismatch_are_exact_and_read_only(self):
        for actual, matched in ((b"RED", True), (b"RED ", False), (b"BLUE", False)):
            with self.subTest(actual=actual):
                sock = FakeSocket([b"^0=ET" + actual + b"\r"])
                client, _, events = self.make_client(sock)
                client.set_external_text("RED", write_safety_confirmed=True,
                                         command_echo_disabled_confirmed=True)
                result = client.verify_external_text("RED")
                self.assertEqual(result.matched, matched)
                self.assertEqual(sock.sent, [b"^0=ETRED\r", b"^0?ET\r"])
                verified = [event for event in events if event.kind == "RESULT" and event.message.startswith("VERIFIED")]
                self.assertEqual(len(verified), 1 if matched else 0)

    def test_write_and_readback_share_one_session(self):
        sock = FakeSocket([b"^0=ETRED\r"])
        factory = Mock(return_value=sock)
        client = LJ3Client(Settings("127.0.0.1"), socket_factory=factory)
        client.set_external_text("RED", write_safety_confirmed=True,
                                 command_echo_disabled_confirmed=True)
        self.assertTrue(client.verify_external_text("RED").matched)
        self.assertEqual(sock.sent, [b"^0=ETRED\r", b"^0?ET\r"])
        self.assertEqual(factory.call_count, 1)
        self.assertFalse(sock.closed)

    def test_verification_cannot_reconnect_after_write_session_is_lost(self):
        write_sock, later_sock = FakeSocket(), FakeSocket([b"^0=ETRED\r"])
        factory = Mock(side_effect=[write_sock, later_sock])
        client = LJ3Client(Settings("127.0.0.1"), socket_factory=factory)
        client.set_external_text("RED", write_safety_confirmed=True,
                                 command_echo_disabled_confirmed=True)
        client.disconnect()
        with self.assertRaisesRegex(CommunicationError, "Same TCP session"):
            client.verify_external_text("RED")
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(later_sock.sent, [])

    def test_write_echo_must_be_confirmed_disabled(self):
        sock = FakeSocket()
        client, factory, _ = self.make_client(sock)
        with self.assertRaisesRegex(ValueError, "echo"):
            client.send_command("=ET", "RED", write_safety_confirmed=True)
        factory.assert_not_called()
        self.assertEqual(sock.sent, [])

    def test_verification_timeout_never_reports_verified_and_does_not_retry(self):
        sock = FakeSocket([TimeoutError()])
        client, factory, events = self.make_client(sock)
        client.set_external_text("RED", write_safety_confirmed=True,
                                 command_echo_disabled_confirmed=True)
        with self.assertRaises(ResponseTimeout):
            client.verify_external_text("RED")
        self.assertFalse(any(event.message.startswith("VERIFIED") for event in events))
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(sock.sent, [b"^0=ETRED\r", b"^0?ET\r"])
        self.assertTrue(sock.closed)
        self.assertFalse(client.connected)

    def test_timeout_closes_session_and_never_retries(self):
        sock = FakeSocket([b"^0=ETpartial", TimeoutError()])
        client, factory, _ = self.make_client(sock)
        with self.assertRaises(ResponseTimeout):
            client.get_external_text()
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(sock.sent, [b"^0?ET\r"])
        self.assertTrue(sock.closed)

    def test_absolute_response_deadline_is_not_reset_by_unsolicited_frames(self):
        sock = FakeSocket([b"^0=VSversion\r"])
        client, _, _ = self.make_client(sock)
        client.settings = Settings("127.0.0.1", timeout=3)
        with patch("lj3.client.time.monotonic", side_effect=[10, 11, 14, 15]):
            with self.assertRaises(ResponseTimeout):
                client.get_external_text()
        self.assertEqual(sock.recv_count, 1)
        self.assertEqual(sock.sent, [b"^0?ET\r"])
        self.assertTrue(sock.closed)

    def test_peer_close_and_reset_fail_without_retry(self):
        for response in (b"", ConnectionResetError("reset")):
            with self.subTest(response=response):
                sock = FakeSocket([response])
                client, factory, _ = self.make_client(sock)
                with self.assertRaises(CommunicationError):
                    client.get_external_text()
                self.assertTrue(sock.closed)
                self.assertEqual(factory.call_count, 1)

    def test_failed_write_is_not_replayed(self):
        sock = FakeSocket(send_error=ConnectionResetError("reset"))
        client, factory, _ = self.make_client(sock)
        with self.assertRaisesRegex(CommunicationError, "unknown"):
            client.set_external_text("RED", write_safety_confirmed=True,
                                     command_echo_disabled_confirmed=True)
        self.assertEqual(sock.sent, [b"^0=ETRED\r"])
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(sock.closed)

    def test_protocol_error_closes_connection(self):
        sock = FakeSocket([b"^1=ETRED\r"])
        client, _, _ = self.make_client(sock)
        with self.assertRaises(ProtocolError):
            client.get_external_text()
        self.assertTrue(sock.closed)

    def test_unsolicited_device_error_fails_external_text_read(self):
        sock = FakeSocket([b"^0=RS4\t4\t123\t0\t230\r"])
        client, _, _ = self.make_client(sock)
        with self.assertRaises(DeviceError):
            client.get_external_text()
        self.assertTrue(sock.closed)

    def test_ambiguous_multiple_frames_are_rejected(self):
        sock = FakeSocket([b"^0=ETRED\r^0=ETBLUE\r"])
        client, _, _ = self.make_client(sock)
        with self.assertRaises(ProtocolError):
            client.get_external_text()
        self.assertTrue(sock.closed)

    def test_next_explicit_action_may_reconnect_after_failure(self):
        first, second = FakeSocket([TimeoutError()]), FakeSocket([b"^0=ETRED\r"])
        factory = Mock(side_effect=[first, second])
        client = LJ3Client(Settings("127.0.0.1"), socket_factory=factory)
        with self.assertRaises(ResponseTimeout):
            client.get_external_text()
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(client.get_external_text(), "RED")
        self.assertEqual(factory.call_count, 2)

    def test_connection_failure_is_reported_without_retry(self):
        factory = Mock(side_effect=ConnectionRefusedError("refused"))
        client = LJ3Client(Settings("127.0.0.1"), socket_factory=factory)
        with self.assertRaises(CommunicationError):
            client.connect()
        self.assertFalse(client.connected)
        self.assertEqual(factory.call_count, 1)

    def test_generic_send_requires_explicit_connection_and_allowlisted_command(self):
        client, factory, _ = self.make_client(FakeSocket())
        with self.assertRaises(CommunicationError):
            client.send_command("?ET")
        with self.assertRaises(ValueError):
            client.send_command("!GO")
        factory.assert_not_called()
