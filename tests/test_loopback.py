"""Real TCP tests bind loopback only. They never load .env or contact a printer."""

import socket
import threading
import unittest

from lj3.client import LJ3Client, ResponseTimeout
from lj3.config import Settings


class LoopbackTests(unittest.TestCase):
    def test_connection_send_and_readback_over_real_tcp(self):
        received = []
        failures = []
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            server.settimeout(3)
            port = server.getsockname()[1]

            def run_server():
                try:
                    for index in range(3):
                        conn, _ = server.accept()
                        with conn:
                            conn.settimeout(3)
                            data = b""
                            while not data.endswith(b"\r"):
                                chunk = conn.recv(1024)
                                if not chunk:
                                    break
                                data += chunk
                            received.append(data)
                            if index == 2:
                                conn.sendall(b"^0=ETBL")
                                conn.sendall(b"UE\r\n")
                except Exception as exc:
                    failures.append(exc)

            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            client = LJ3Client(Settings("127.0.0.1", port, 2))
            try:
                client.connect()
                client.disconnect()
                client.set_external_text("BLUE", stopped_ascii_job_confirmed=True)
                self.assertTrue(client.verify_external_text("BLUE").matched)
            finally:
                client.disconnect()
                thread.join(4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(received, [b"", b"^0=ETBLUE\r", b"^0?ET\r"])

    def test_silent_peer_times_out_without_a_second_connection(self):
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
                        data = b""
                        while not data.endswith(b"\r"):
                            chunk = conn.recv(1024)
                            if not chunk:
                                break
                            data += chunk
                        received.append(data)
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
