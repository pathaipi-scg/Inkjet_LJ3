"""Real TCP tests bind loopback only. They never load .env or contact a printer."""

import socket
import threading
import unittest

from lj3.client import LJ3Client, ResponseTimeout
from lj3.config import Settings


class LoopbackTests(unittest.TestCase):
    def test_status_write_and_readback_share_one_real_tcp_session(self):
        received = []
        failures = []
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            server.settimeout(3)
            port = server.getsockname()[1]

            def run_server():
                try:
                    conn, _ = server.accept()
                    with conn:
                        conn.settimeout(3)
                        for expected, response in (
                            (b"^0?RS\r", b"^0=RS4\t4\t0\t0\t230\t0\r"),
                            (b"^0=ETBLUE\r", None),
                            (b"^0?ET\r", b"^0=ETBLUE\r"),
                        ):
                            data = bytearray()
                            while not data.endswith(b"\r"):
                                chunk = conn.recv(1)
                                if not chunk:
                                    break
                                data.extend(chunk)
                            received.append(bytes(data))
                            if bytes(data) != expected:
                                raise AssertionError(f"expected {expected!r}, received {bytes(data)!r}")
                            if response is not None:
                                conn.sendall(response)
                except Exception as exc:
                    failures.append(exc)

            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            client = LJ3Client(Settings("127.0.0.1", port, 2))
            try:
                status = client.get_printer_status()
                self.assertEqual(status.machine_state, 4)
                client.set_external_text("BLUE", write_safety_confirmed=True,
                                         command_echo_disabled_confirmed=True)
                self.assertTrue(client.verify_external_text("BLUE").matched)
                self.assertTrue(client.connected)
            finally:
                client.disconnect()
                thread.join(4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(received, [b"^0?RS\r", b"^0=ETBLUE\r", b"^0?ET\r"])

    def test_silent_peer_times_out_without_reconnect_or_retry(self):
        finished = threading.Event()
        received = []
        failures = []
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            server.settimeout(2)

            def run_server():
                try:
                    conn, _ = server.accept()
                    with conn:
                        conn.settimeout(2)
                        data = bytearray()
                        while not data.endswith(b"\r"):
                            chunk = conn.recv(1)
                            if not chunk:
                                break
                            data.extend(chunk)
                        received.append(bytes(data))
                        finished.wait(2)
                except Exception as exc:
                    failures.append(exc)

            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            client = LJ3Client(Settings("127.0.0.1", server.getsockname()[1], 0.1))
            try:
                with self.assertRaises(ResponseTimeout):
                    client.get_external_text()
                self.assertFalse(client.connected)
            finally:
                finished.set()
                client.disconnect()
                thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(received, [b"^0?ET\r"])
