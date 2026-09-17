from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

from lj3.__main__ import main
from lj3.client import CommunicationError, LJ3Client, ResponseTimeout, Verification
from lj3.protocol import ProtocolError
from test_client import FakeSocket
from lj3.config import PROJECT_ROOT, Settings, load_settings


class ConfigTests(unittest.TestCase):
    def load_env(self, text):
        # All temporary files stay inside this workspace.
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            (root / ".env").write_text(text, encoding="utf-8")
            with patch("lj3.config.PROJECT_ROOT", root):
                return load_settings()

    def test_missing_file_defaults_without_parent_search(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            with patch("lj3.config.PROJECT_ROOT", Path(directory)):
                self.assertEqual(load_settings(), Settings())

    def test_only_lj3_keys_are_used(self):
        result = self.load_env('# comment\nSQL_PASS=private\nOPC_URL=unused\nLJ3_IP="127.0.0.1"\nLJ3_PORT=3100\nLJ3_TIMEOUT_SECONDS=2.5\n')
        self.assertEqual(result, Settings("127.0.0.1", 3100, 2.5))

    def test_invalid_settings_do_not_echo_secret_values(self):
        for text in ("LJ3_PORT=private", "LJ3_IP=private", "LJ3_TIMEOUT_SECONDS=nan",
                     "LJ3_PORT=0", "LJ3_PORT=65536", "LJ3_TIMEOUT_SECONDS=0", "LJ3_TIMEOUT_SECONDS=inf"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as error:
                    self.load_env(text)
                self.assertNotIn("private", str(error.exception))

    def test_duplicate_and_unclosed_quotes(self):
        for text in ("LJ3_PORT=3000\nLJ3_PORT=3100", 'LJ3_IP="127.0.0.1'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load_env(text)

    def test_ip_required_only_for_network_actions(self):
        Settings().validate(require_ip=False)
        with self.assertRaises(ValueError):
            Settings().validate()


class CLITests(unittest.TestCase):
    def run_menu(self, inputs, verification=None, *, connect_error=None, send_error=None):
        output = io.StringIO()
        with patch("sys.argv", ["lj3"]), patch("lj3.__main__.load_settings", return_value=Settings("127.0.0.1")):
            with patch("builtins.input", side_effect=inputs), patch("lj3.__main__.LJ3Client") as client_class:
                client_class.return_value.connected = False
                client_class.return_value.get_external_text.return_value = "EXISTING"
                client_class.return_value.connect.side_effect = connect_error
                client_class.return_value.set_external_text.side_effect = send_error
                if isinstance(verification, Exception):
                    client_class.return_value.verify_external_text.side_effect = verification
                elif verification is not None:
                    client_class.return_value.verify_external_text.return_value = verification
                with redirect_stdout(output):
                    self.assertEqual(main(), 0)
                return client_class.return_value, output.getvalue()

    def test_startup_and_exit_do_not_connect_or_send(self):
        client, _ = self.run_menu(["0"])
        client.connect.assert_not_called()
        client.set_external_text.assert_not_called()
        client.get_external_text.assert_not_called()

    def test_cancelled_send_does_not_connect(self):
        client, output = self.run_menu(["5", "RED", "no", "0"])
        client.connect.assert_not_called()
        client.set_external_text.assert_not_called()
        self.assertIn("Cancelled", output)

    def test_send_and_verify_are_distinct_actions(self):
        client, _ = self.run_menu(["5", "RED", "SEND", "0"])
        client.set_external_text.assert_called_once_with("RED", stopped_ascii_job_confirmed=True)
        client.get_external_text.assert_not_called()
        client.verify_external_text.assert_not_called()

    def test_invalid_input_never_sends(self):
        client, output = self.run_menu(["5", "RED\r^0!GO", "0"])
        client.set_external_text.assert_not_called()
        self.assertIn("ERROR", output)

    def test_verify_before_send_does_not_query(self):
        client, output = self.run_menu(["4", "0"])
        client.verify_external_text.assert_not_called()
        self.assertIn("No completed send", output)

    def test_verified_requires_separate_readback_and_exact_match(self):
        for actual in ("RED", "RED ", "BLUE"):
            with self.subTest(actual=actual):
                client, output = self.run_menu(["5", "RED", "SEND", "4", "0"], Verification("RED", actual))
                client.verify_external_text.assert_called_once_with("RED")
                self.assertEqual("Result:\nVERIFIED" in output, actual == "RED")
                self.assertEqual("Result:\nMISMATCH" in output, actual != "RED")

    def test_readback_failure_never_displays_verified(self):
        _, output = self.run_menu(["5", "RED", "SEND", "4", "0"], ResponseTimeout("Readback timed out"))
        self.assertIn("ERROR: Readback timed out", output)
        self.assertNotIn("Result:\nVERIFIED", output)

    def test_menu_follows_commissioning_order(self):
        _, output = self.run_menu(["0"])
        self.assertIn("Leibinger Jet3 - Manual Phase 1 Tool", output)
        self.assertIn("Target: 127.0.0.1:3000\nStatus: disconnected", output)
        self.assertIn("1  Test TCP Connection\n2  Read Current ExternText\n"
                      "3  Send Test Text (TEST123)\n4  Verify Last Sent Text\n"
                      "5  Send Free Text\n6  Configure Target\n0  Quit", output)

    def test_tcp_test_only_connects_and_reports_result(self):
        for error in (None, CommunicationError("refused"), ValueError("missing target")):
            with self.subTest(error=error):
                client, output = self.run_menu(["1", "0"], connect_error=error)
                client.connect.assert_called_once_with()
                client.disconnect.assert_called()
                client.set_external_text.assert_not_called()
                client.get_external_text.assert_not_called()
                client.verify_external_text.assert_not_called()
                self.assertIn("TCP CONNECTION FAILED" if error else "TCP CONNECTION OK", output)

    def test_read_displays_value_without_writing(self):
        client, output = self.run_menu(["2", "0"])
        client.get_external_text.assert_called_once_with()
        client.set_external_text.assert_not_called()
        self.assertIn("Current Jet3 ExternText:\nEXISTING", output)

    def test_fixed_test_value_requires_explicit_confirmation(self):
        for confirmation in ("SEND", "send", "", "no"):
            with self.subTest(confirmation=confirmation):
                client, output = self.run_menu(["3", confirmation, "0"])
                self.assertIn("Text to send:\nTEST123", output)
                self.assertNotIn("Result:\nVERIFIED", output)
                client.verify_external_text.assert_not_called()
                client.get_external_text.assert_not_called()
                if confirmation == "SEND":
                    client.set_external_text.assert_called_once_with("TEST123", stopped_ascii_job_confirmed=True)
                    self.assertIn("SENT - UNVERIFIED", output)
                else:
                    client.set_external_text.assert_not_called()
                    client.connect.assert_not_called()

    def test_site_workflow_verifies_most_recent_value(self):
        client, output = self.run_menu(
            ["1", "2", "3", "SEND", "4", "5", "CHARCOAL GREY", "SEND", "4", "0"],
            Verification("TEST123", "TEST123"))
        self.assertEqual(client.set_external_text.call_args_list, [
            call("TEST123", stopped_ascii_job_confirmed=True),
            call("CHARCOAL GREY", stopped_ascii_job_confirmed=True)])
        self.assertEqual(client.verify_external_text.call_args_list,
                         [call("TEST123"), call("CHARCOAL GREY")])
        self.assertIn("Sent:\nTEST123", output)
        self.assertIn("Jet3 Readback:\nTEST123", output)

    def test_free_text_preserves_ascii_spaces(self):
        for value in ("CHARCOAL GREY", "RED", "BLUE", "COLOR A", "LOT260917", " RED "):
            with self.subTest(value=value):
                client, output = self.run_menu(["5", value, "SEND", "0"])
                client.set_external_text.assert_called_once_with(value, stopped_ascii_job_confirmed=True)
                self.assertIn(f"Text to send:\n{value}\n", output)

    def test_unicode_is_blocked_without_confirmation_or_network(self):
        for value in ("สีเทา", "สีแดง", "น้ำตาล", "RED สีแดง", "é", "😀"):
            with self.subTest(value=value):
                client, output = self.run_menu(["5", value, "0"])
                client.connect.assert_not_called()
                client.set_external_text.assert_not_called()
                client.get_external_text.assert_not_called()
                self.assertIn("Unicode / Experimental - SEND BLOCKED", output)
                self.assertIn("hexadecimal", output)
                self.assertNotIn("SENT - UNVERIFIED", output)

    def test_configuration_clears_comparison_without_connecting(self):
        client, output = self.run_menu(["3", "SEND", "6", "127.0.0.2", "3100", "2", "4", "0"])
        self.assertIn("Target: 127.0.0.2:3100", output)
        self.assertIn("No completed send", output)
        client.verify_external_text.assert_not_called()
        client.connect.assert_not_called()

    def test_failed_write_invalidates_previous_value(self):
        client, output = self.run_menu(["3", "SEND", "5", "RED", "SEND", "4", "0"],
                                       send_error=[None, CommunicationError("unknown delivery")])
        client.verify_external_text.assert_not_called()
        self.assertIn("No completed send", output)
        self.assertEqual(output.count("SENT - UNVERIFIED"), 1)

    def test_cancelled_or_blocked_write_preserves_previous_value(self):
        for attempt in (["5", "RED", "no"], ["5", "สีแดง"], ["5", "BAD\r"]):
            with self.subTest(attempt=attempt):
                client, _ = self.run_menu(["3", "SEND", *attempt, "4", "0"],
                                         Verification("TEST123", "TEST123"))
                client.verify_external_text.assert_called_once_with("TEST123")
                self.assertEqual(client.set_external_text.call_count, 1)

    def test_verification_errors_have_explicit_result(self):
        for error in (ResponseTimeout("timeout"), CommunicationError("closed"), ProtocolError("bad frame")):
            with self.subTest(error=error):
                _, output = self.run_menu(["3", "SEND", "4", "0"], error)
                self.assertIn("Result:\nCOMMUNICATION ERROR", output)
                self.assertNotIn("Result:\nVERIFIED", output)

    def test_full_cli_workflow_sends_only_expected_bytes(self):
        sockets = [FakeSocket(), FakeSocket([b"^0=ETOLD\r"]), FakeSocket(),
                   FakeSocket([b"^0=ETTEST123\r"]), FakeSocket(),
                   FakeSocket([b"^0=ETCHARCOAL GREY\r"])]
        from unittest.mock import Mock
        factory = Mock(side_effect=sockets)
        output = io.StringIO()
        with patch("sys.argv", ["lj3"]), patch("lj3.__main__.load_settings", return_value=Settings("127.0.0.1")):
            with patch("lj3.__main__.LJ3Client", side_effect=lambda settings, events: LJ3Client(
                    settings, events, socket_factory=factory)):
                with patch("builtins.input", side_effect=["1", "2", "3", "SEND", "4",
                                                         "5", "CHARCOAL GREY", "SEND", "4", "0"]):
                    with redirect_stdout(output):
                        self.assertEqual(main(), 0)
        self.assertEqual([sock.sent for sock in sockets], [[], [b"^0?ET\r"],
                         [b"^0=ETTEST123\r"], [b"^0?ET\r"],
                         [b"^0=ETCHARCOAL GREY\r"], [b"^0?ET\r"]])
        self.assertTrue(all(sock.closed for sock in sockets))
        self.assertEqual(factory.call_count, 6)
        self.assertEqual(output.getvalue().count("Result:\nVERIFIED"), 2)
