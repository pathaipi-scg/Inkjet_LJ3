from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lj3.__main__ import main
from lj3.client import ResponseTimeout, Verification
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
    def run_menu(self, inputs, verification=None):
        output = io.StringIO()
        with patch("sys.argv", ["lj3"]), patch("lj3.__main__.load_settings", return_value=Settings("127.0.0.1")):
            with patch("builtins.input", side_effect=inputs), patch("lj3.__main__.LJ3Client") as client_class:
                client_class.return_value.connected = False
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
        client, output = self.run_menu(["3", "RED", "no", "0"])
        client.connect.assert_not_called()
        client.set_external_text.assert_not_called()
        self.assertIn("Cancelled", output)

    def test_send_and_verify_are_distinct_actions(self):
        client, _ = self.run_menu(["3", "RED", "SEND", "0"])
        client.set_external_text.assert_called_once_with("RED", stopped_ascii_job_confirmed=True)
        client.get_external_text.assert_not_called()
        client.verify_external_text.assert_not_called()

    def test_invalid_input_never_sends(self):
        client, output = self.run_menu(["3", "RED\r^0!GO", "0"])
        client.set_external_text.assert_not_called()
        self.assertIn("ERROR", output)

    def test_verify_before_send_does_not_query(self):
        client, output = self.run_menu(["5", "0"])
        client.verify_external_text.assert_not_called()
        self.assertIn("No completed send", output)

    def test_verified_requires_separate_readback_and_exact_match(self):
        for actual in ("RED", "RED ", "BLUE"):
            with self.subTest(actual=actual):
                client, output = self.run_menu(["3", "RED", "SEND", "5", "0"], Verification("RED", actual))
                client.verify_external_text.assert_called_once_with("RED")
                self.assertEqual("VERIFIED (exact readback):" in output, actual == "RED")
                self.assertEqual("MISMATCH:" in output, actual != "RED")

    def test_readback_failure_never_displays_verified(self):
        _, output = self.run_menu(["3", "RED", "SEND", "5", "0"], ResponseTimeout("Readback timed out"))
        self.assertIn("ERROR: Readback timed out", output)
        self.assertNotIn("VERIFIED (exact readback):", output)
