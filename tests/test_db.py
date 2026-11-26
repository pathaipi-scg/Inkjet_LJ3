import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from uuid import uuid4

from lj3.db import DatabaseError, DatabaseSettings, SqlRepository, load_database_settings
from lj3.journal import TransactionJournal


class DatabaseUnitTests(unittest.TestCase):
    def test_existing_env_names_are_loaded_without_exposing_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("SQL_DRIVER=AUTO\nSQL_SERVER=127.0.0.1\nSQL_DB=CB\n"
                            "SQL_USER=hidden-user\nSQL_PASS=very-secret\n"
                            "SQL_TRUST_SERVER_CERTIFICATE=true\n", encoding="utf-8")
            settings = load_database_settings(path)
        self.assertEqual((settings.server, settings.database, settings.username),
                         ("127.0.0.1", "CB", "hidden-user"))
        self.assertEqual(settings.password, "very-secret")
        with self.assertRaises(DatabaseError) as caught:
            load_database_settings(Path(directory) / "missing.env")
        self.assertNotIn("very-secret", str(caught.exception))

    def test_missing_database_keys_report_only_key_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("SQL_SERVER=host\nSQL_DB=CB\nSQL_USER=secretuser\nSQL_PASS=secretpass\n",
                            encoding="utf-8")
            (path).write_text("SQL_SERVER=host\nSQL_DB=CB\n", encoding="utf-8")
            with self.assertRaises(DatabaseError) as caught:
                load_database_settings(path)
        self.assertNotIn("secret", str(caught.exception))
        self.assertIn("SQL_USER", str(caught.exception))

    def test_migration_runner_splits_go_batches_and_commits(self):
        cursor = Mock()
        connection = Mock()
        connection.cursor.return_value = cursor
        settings = DatabaseSettings("AUTO", "host", "CB", "user", "secret", True)
        repository = SqlRepository(settings, connect_factory=Mock(return_value=connection))
        with tempfile.TemporaryDirectory() as directory:
            migration = Path(directory) / "001_test.sql"
            migration.write_text("SELECT 1;\nGO\nSELECT 2;\n", encoding="utf-8")
            self.assertEqual(repository.migrate(Path(directory)), ["001_test.sql"])
        self.assertEqual(cursor.execute.call_count, 2)
        connection.commit.assert_called_once_with()

@unittest.skipUnless(os.getenv("INKJET_SQL_TEST_SERVER"),
                     "Set INKJET_SQL_TEST_SERVER to opt into real SQL Server integration tests.")
class SqlServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_database_settings()
        cls.server = os.environ["INKJET_SQL_TEST_SERVER"]
        cls.repository = SqlRepository(cls.settings, server_override=cls.server)
        cls.repository.migrate()

    def test_real_schema_persistence_views_and_idempotent_recovery(self):
        info = self.repository.inspect()
        self.assertTrue(info["sql_server_2019"])
        self.assertEqual(info["missing_tables"], [])
        self.assertEqual(info["missing_views"], [])
        transaction_id = str(uuid4())
        code = f"LJ3-192.0.2.254:{42000 + (int(transaction_id[-4:], 16) % 1000)}"
        port = int(code.rsplit(":", 1)[1])
        record = {
            "transaction_id": transaction_id,
            "outcome": "VERIFIED",
            "category": "SUCCESS",
            "printer_ip": "192.0.2.254",
            "printer_port": port,
            "requested_text": "INTEGRATION-TEST",
            "baseline_text": "BEFORE",
            "readback_text": "INTEGRATION-TEST",
            "message": "Automated SQL integration test.",
            "started_at": "2026-11-26T14:00:00+07:00",
            "completed_at": "2026-11-26T14:00:01+07:00",
            "elapsed_ms": 1000.0,
            "snapshot": {"sampled_at": "2026-11-26T14:00:00+07:00", "machine_state": 4,
                         "nozzle_state": 4, "printer_error": 0, "headcover": 0,
                         "act_speed": "230", "extern_actual_speed": "10", "extern_max_speed": "120",
                         "inputs": 0, "direction": 1, "printgo": 0, "printing": False,
                         "externtext_ready": True, "production_stopped": None,
                         "trigger_inhibited": None, "command_echo_enabled": None,
                         "loaded_job": "INTEGRATION-TEST", "unknown_status_fields": []},
            "events": [{"timestamp": "2026-11-26T14:00:00+07:00", "kind": "STATUS",
                         "message": "Synthetic integration event.", "data_hex": None,
                         "elapsed_ms": None}],
        }
        connection = self.repository._connect()
        try:
            with tempfile.TemporaryDirectory() as directory:
                journal = TransactionJournal(Path(directory) / "integration.jsonl")
                journal.append(record)
                self.assertEqual(self.repository.recover(journal), (1, 0))
                self.assertEqual(self.repository.recover(journal), (1, 0))
            cursor = connection.cursor()
            cursor.execute("SELECT Outcome FROM inkjet.TransactionLog WHERE TransactionId=?", (transaction_id,))
            self.assertEqual(cursor.fetchone()[0], "VERIFIED")
            cursor.execute("SELECT COUNT(*) FROM inkjet.PrinterStatus WHERE TransactionId=?", (transaction_id,))
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute("SELECT COUNT(*) FROM inkjet.StatusLog WHERE TransactionId=?", (transaction_id,))
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute("SELECT COUNT(*) FROM inkjet.vw_TransactionHistory WHERE TransactionId=?", (transaction_id,))
            self.assertEqual(cursor.fetchone()[0], 1)
        finally:
            connection.close()
            cleanup = self.repository._connect()
            try:
                cursor = cleanup.cursor()
                for table in ("StatusLog", "ErrorLog", "PrinterStatus", "TransactionLog"):
                    cursor.execute(f"DELETE FROM inkjet.{table} WHERE TransactionId=?", (transaction_id,))
                cursor.execute("DELETE FROM inkjet.PrinterMaster WHERE PrinterCode=?", (code,))
                cleanup.commit()
            finally:
                cleanup.close()


if __name__ == "__main__":
    unittest.main()
