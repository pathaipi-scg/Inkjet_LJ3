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

    def test_tcp_connect_test_sends_no_bytes(self):
        sock = FakeSocket()
        client, factory, _ = self.make_client(sock)
        client.connect()
        self.assertTrue(client.connected)
        client.disconnect()
        self.assertEqual(sock.sent, [])
        self.assertEqual(sock.recv_count, 0)
        self.assertTrue(sock.closed)
        self.assertEqual(factory.call_count, 1)

    def test_send_requires_confirmation_before_connect(self):
        client, factory, _ = self.make_client(FakeSocket())
        with self.assertRaises(ValueError):
            client.set_external_text("RED")
        factory.assert_not_called()

    def test_invalid_send_never_connects(self):
        client, factory, _ = self.make_client(FakeSocket())
        with self.assertRaises(ValueError):
            client.set_external_text("BAD\r", stopped_ascii_job_confirmed=True)
        factory.assert_not_called()

    def test_no_ack_expected_on_write_and_connection_closed(self):
        sock = FakeSocket()
        client, _, events = self.make_client(sock)
        client.set_external_text("RED", stopped_ascii_job_confirmed=True)
        self.assertEqual(sock.sent, [b"^0=ETRED\r"])
        self.assertEqual(sock.recv_count, 0)
        self.assertTrue(sock.closed)
        self.assertFalse(client.connected)
        self.assertTrue(any("UNVERIFIED" in event.message for event in events))
        self.assertTrue(all(event.timestamp.endswith("+00:00") for event in events))

    def test_fragmentation_and_unsolicited_frames(self):
        sock = FakeSocket([b"^0=RS2\t5\t0\t0\t0\r\n^0=E", b"TBLUE\r\n"])
        client, _, events = self.make_client(sock)
        self.assertEqual(client.get_external_text(), "BLUE")
        self.assertEqual(sock.sent, [b"^0?ET\r"])
        self.assertTrue(sock.closed)
        self.assertTrue(any(event.kind == "NOTICE" for event in events))
        self.assertEqual(sum(event.kind == "RX" for event in events), 2)

    def test_length_mode_response(self):
        client, _, _ = self.make_client(FakeSocket([b"^000008=ETBLUE\r"]))
        self.assertEqual(client.get_external_text(), "BLUE")

    def test_verification_match_and_mismatch_are_read_only(self):
        for actual, matched in ((b"RED", True), (b"RED ", False), (b"BLUE", False)):
            with self.subTest(actual=actual):
                sock = FakeSocket([b"^0=ET" + actual + b"\r"])
                client, _, events = self.make_client(sock)
                result = client.verify_external_text("RED")
                self.assertEqual(result.matched, matched)
                self.assertEqual(sock.sent, [b"^0?ET\r"])
                verified = [event for event in events if event.kind == "RESULT" and event.message.startswith("VERIFIED")]
                self.assertEqual(len(verified), 1 if matched else 0)

    def test_verification_timeout_never_reports_verified(self):
        client, _, events = self.make_client(FakeSocket([TimeoutError()]))
        with self.assertRaises(ResponseTimeout):
            client.verify_external_text("RED")
        self.assertFalse(any(event.message.startswith("VERIFIED") for event in events))

    def test_timeout_closes_and_never_retries(self):
        sock = FakeSocket([b"^0=ETpartial", TimeoutError()])
        client, factory, _ = self.make_client(sock)
        with self.assertRaises(ResponseTimeout):
            client.get_external_text()
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(sock.sent, [b"^0?ET\r"])
        self.assertTrue(sock.closed)

    def test_absolute_deadline_is_not_reset_by_unsolicited_frames(self):
        sock = FakeSocket([b"^0=VSversion\r"])
        client, _, _ = self.make_client(sock)
        with patch("lj3.client.time.monotonic", side_effect=[10, 11, 14]):
            with self.assertRaises(ResponseTimeout):
                client.get_external_text()
        self.assertEqual(sock.recv_count, 1)

    def test_peer_close_and_reset_fail_without_retry(self):
        for response in (b"", ConnectionResetError("reset")):
            with self.subTest(response=response):
                sock = FakeSocket([response])
                client, factory, _ = self.make_client(sock)
                with self.assertRaises(CommunicationError):
                    client.get_external_text()
                self.assertTrue(sock.closed)
                self.assertEqual(factory.call_count, 1)

    def test_failed_write_reports_unknown_and_is_not_replayed(self):
        sock = FakeSocket(send_error=ConnectionResetError("reset"))
        client, factory, _ = self.make_client(sock)
        with self.assertRaisesRegex(CommunicationError, "unknown"):
            client.set_external_text("RED", stopped_ascii_job_confirmed=True)
        self.assertEqual(sock.sent, [b"^0=ETRED\r"])
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(sock.closed)

    def test_write_echo_cannot_satisfy_subsequent_read(self):
        write_socket = FakeSocket([b"^0=ETRED\r"])
        read_socket = FakeSocket([b"^0=ETBLUE\r"])
        factory = Mock(side_effect=[write_socket, read_socket])
        client = LJ3Client(Settings("127.0.0.1"), socket_factory=factory)
        client.set_external_text("RED", stopped_ascii_job_confirmed=True)
        self.assertFalse(client.verify_external_text("RED").matched)
        self.assertEqual(write_socket.recv_count, 0)
        self.assertEqual(read_socket.sent, [b"^0?ET\r"])

    def test_protocol_error_closes_connection(self):
        sock = FakeSocket([b"^1=ETRED\r"])
        client, _, _ = self.make_client(sock)
        with self.assertRaises(ProtocolError):
            client.get_external_text()
        self.assertTrue(sock.closed)

    def test_device_error_is_not_success_even_if_et_arrives_in_same_chunk(self):
        for error in (b"^0=FC123\r", b"^0=RS2\t5\t123\t0\t0\r"):
            with self.subTest(error=error):
                sock = FakeSocket([b"^0=ETRED\r" + error])
                client, _, _ = self.make_client(sock)
                with self.assertRaises(DeviceError):
                    client.get_external_text()
                self.assertTrue(sock.closed)

    def test_ambiguous_multiple_or_incomplete_trailing_frames_rejected(self):
        for reply in (b"^0=ETRED\r^0=ETBLUE\r", b"^0=ETRED\r^0=FC"):
            with self.subTest(reply=reply):
                client, _, _ = self.make_client(FakeSocket([reply]))
                with self.assertRaises(ProtocolError):
                    client.get_external_text()

    def test_reconnect_only_on_next_explicit_action(self):
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
