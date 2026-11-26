import tempfile
from pathlib import Path
from threading import Event as ThreadingEvent, Thread
import unittest
from unittest.mock import Mock

from lj3.client import Event, LJ3Client
from lj3.config import Settings
from lj3.journal import TransactionJournal
from lj3.locking import printer_lock
from lj3.status import read_printer_snapshot
from lj3.transaction import TransactionService
from test_client import FakeSocket


READY = b"^0=RS4\t4\t0\t0\t230\r"
EX_LOW = b"^0=EX10\t0\t120\t1\t0\t0\t0\t0\t0\r"
JOB = b"^0=JLFFSDISK\\JOBS\\CB-LOT-TEST.JOB\r"


class TransactionTests(unittest.TestCase):
    def make_client(self, chunks):
        sock = FakeSocket(chunks)
        client = LJ3Client(Settings("127.0.0.1"), socket_factory=Mock(return_value=sock))
        return client, sock

    def test_snapshot_uses_only_read_only_documented_inquiries_and_preserves_unknowns(self):
        client, sock = self.make_client([READY, EX_LOW, JOB])
        snapshot = read_printer_snapshot(client)
        self.assertEqual(sock.sent, [b"^0?RS\r", b"^0?EX\r", b"^0?JL\r"])
        self.assertFalse(snapshot.printing)
        self.assertFalse(snapshot.printgo_high)
        self.assertIsNone(snapshot.trigger_inhibited)
        self.assertTrue(snapshot.externtext_ready)
        self.assertEqual(snapshot.loaded_job, "FFSDISK\\JOBS\\CB-LOT-TEST.JOB")
        self.assertTrue(snapshot.has_loaded_job("CB-LOT-TEST.job"))

    def test_status_snapshot_journals_raw_inquiry_events_for_status_log(self):
        client, _ = self.make_client([READY, EX_LOW, JOB])
        snapshot = read_printer_snapshot(client)
        event = Event("2026-11-26T00:00:00+00:00", "RX", "Received TCP bytes", READY, 2.5)
        with tempfile.TemporaryDirectory() as directory:
            journal = TransactionJournal(Path(directory) / "journal.jsonl")
            result = TransactionService(journal).record_status_snapshot(client, snapshot, (event,))
            record = result.journal_record()
            self.assertEqual(record["outcome"], "STATUS_ONLY")
            self.assertEqual(record["events"][0]["kind"], "RX")
            self.assertEqual(record["events"][0]["data_hex"], READY.hex())
            self.assertEqual(tuple(journal.pending_records())[0]["events"], record["events"])

    def test_transaction_runs_preflight_baseline_single_write_and_same_session_readback(self):
        client, sock = self.make_client([READY, EX_LOW, JOB, b"^0=ETOLD\r", b"^0=ET4691126P\r"])
        with tempfile.TemporaryDirectory() as directory:
            journal = TransactionJournal(Path(directory) / "journal.jsonl")
            result = TransactionService(journal).execute(
                client, "4691126P", write_safety_confirmed=True,
                command_echo_disabled_confirmed=True,
                expected_job_name="CB-LOT-TEST.job")
            self.assertEqual(result.outcome, "VERIFIED")
            self.assertEqual(result.baseline_text, "OLD")
            self.assertEqual(result.readback_text, "4691126P")
            self.assertTrue(result.journaled)
            self.assertEqual(sock.sent, [b"^0?RS\r", b"^0?EX\r", b"^0?JL\r",
                                         b"^0?ET\r", b"^0=ET4691126P\r", b"^0?ET\r"])
            self.assertFalse(sock.closed)
            records = tuple(journal.pending_records())
            self.assertEqual([item["outcome"] for item in records], ["WRITE_PENDING", "VERIFIED"])
            final = records[-1]
            self.assertIsNone(final["snapshot"]["trigger_inhibited"])
            self.assertIsNone(final["snapshot"]["production_stopped"])
            self.assertIsNone(final["snapshot"]["command_echo_enabled"])

    def test_wrong_expected_job_blocks_before_baseline_or_write(self):
        client, sock = self.make_client([READY, EX_LOW, JOB])
        with tempfile.TemporaryDirectory() as directory:
            result = TransactionService(
                TransactionJournal(Path(directory) / "j.jsonl")).execute(
                    client, "NEW", write_safety_confirmed=True,
                    command_echo_disabled_confirmed=True,
                    expected_job_name="OTHER.JOB")
        self.assertEqual(result.outcome, "BLOCKED")
        self.assertEqual(result.category, "EXPECTED_JOB_MISMATCH")
        self.assertIn("OTHER.JOB", result.message)
        self.assertIn("CB-LOT-TEST.JOB", result.message)
        self.assertEqual(sock.sent, [b"^0?RS\r", b"^0?EX\r", b"^0?JL\r"])

    def test_experimental_iso8859_11_transaction_is_single_write_and_byte_verified(self):
        payload = bytes.fromhex("CA D5 E0 B7 D2 B9 A1")
        returned_frame = b"^0=ET" + payload + b"\r"
        client, sock = self.make_client([READY, EX_LOW, JOB, b"^0=ET4691126P\r", returned_frame])
        confirmations = ("production stopped", "external triggers inhibited",
                         "sole ExternText writer", "!EM echo disabled")
        with tempfile.TemporaryDirectory() as directory:
            journal = TransactionJournal(Path(directory) / "experimental.jsonl")
            result = TransactionService(journal).execute_experimental_iso8859_11(
                client, write_safety_confirmed=True,
                command_echo_disabled_confirmed=True,
                operator_confirmations=confirmations)
            self.assertEqual(result.outcome, "VERIFIED")
            self.assertEqual(result.category, "EXPERIMENTAL_ISO8859_11_MATCH")
            self.assertEqual(result.requested_text, "สีเทานก")
            self.assertEqual(result.readback_text, "สีเทานก")
            expected_write = b"^0=ET" + payload + b"\r"
            self.assertEqual(sock.sent, [b"^0?RS\r", b"^0?EX\r", b"^0?JL\r",
                                         b"^0?ET\r", expected_write, b"^0?ET\r"])
            self.assertEqual(sock.sent.count(expected_write), 1)
            self.assertTrue(result.journaled)
            final = tuple(journal.pending_records())[-1]
            self.assertEqual(final["outcome"], "VERIFIED")
            self.assertTrue(any(event["kind"] == "EXPERIMENT" and
                                event["data_hex"] == payload.hex()
                                for event in final["events"]))
            self.assertTrue(any(event["kind"] == "TX" and
                                event["data_hex"] == expected_write.hex()
                                for event in final["events"]))
            self.assertTrue(any(event["kind"] == "RX" and
                                event["data_hex"] == returned_frame.hex()
                                for event in final["events"]))

    def test_experimental_transaction_blocks_on_high_printgo_without_baseline_or_write(self):
        client, sock = self.make_client([READY, b"^0=EX10\t0\t120\t1\t0\t1\r", JOB])
        with tempfile.TemporaryDirectory() as directory:
            result = TransactionService(TransactionJournal(Path(directory) / "j.jsonl"))\
                .execute_experimental_iso8859_11(
                    client, write_safety_confirmed=True,
                    command_echo_disabled_confirmed=True,
                    operator_confirmations=("production stopped", "triggers inhibited",
                                            "sole writer", "echo disabled"))
        self.assertEqual(result.outcome, "BLOCKED")
        self.assertEqual(result.category, "PRINTER_NOT_READY")
        self.assertEqual(sock.sent, [b"^0?RS\r", b"^0?EX\r", b"^0?JL\r"])

    def test_mailmode_field1_transaction_preserves_field0_and_leaves_fifo_staged(self):
        empty = b"^0=SM256\t0\t0\t0\t0\r"
        one = b"^0=SM256\t1\t0\t0\t0\r"
        field0 = b"^0=ET4691125P\r"
        client, sock = self.make_client([
            READY, EX_LOW, JOB, field0, empty, empty,
            one, one, field0,
        ])
        confirmations = ("production stopped", "external triggers inhibited",
                         "application is the only ExternText writer",
                         "!EM command echo disabled")
        wire = bytes.fromhex("5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D")
        with tempfile.TemporaryDirectory() as directory:
            journal = TransactionJournal(Path(directory) / "mailmode.jsonl")
            result = TransactionService(journal).execute_experimental_thai_mailmode_field1(
                client, "4691125P", production_stopped_confirmed=True,
                triggers_inhibited_confirmed=True, sole_writer_confirmed=True,
                command_echo_disabled_confirmed=True,
                operator_confirmations=confirmations)
            records = tuple(journal.pending_records())
        self.assertEqual(result.outcome, "STAGED_UNVERIFIED")
        self.assertEqual(result.category, "EXPERIMENTAL_MAILMODE_FIELD1_STAGED")
        self.assertEqual(result.baseline_text, "4691125P")
        self.assertEqual(result.readback_text, "4691125P")
        self.assertEqual(sock.sent.count(wire), 1)
        self.assertNotIn(b"^0!FF\r", sock.sent)
        self.assertNotIn(b"^0=ET", [frame for frame in sock.sent if frame.startswith(b"^0=")])
        self.assertNotIn(b"^0!GO\r", sock.sent)
        self.assertEqual(sock.sent.count(b"^0?SM\r"), 4)
        self.assertEqual([record["outcome"] for record in records], ["WRITE_PENDING", "STAGED_UNVERIFIED"])
        self.assertEqual(records[0]["mailmode_field_number"], 1)
        self.assertTrue(any(event["kind"] == "TX" and event["data_hex"] == wire.hex()
                            for event in records[-1]["events"]))

    def test_mailmode_field1_blocks_nonempty_fifo_before_any_write_or_clear(self):
        nonempty = b"^0=SM256\t2\t0\t0\t0\r"
        client, sock = self.make_client([READY, EX_LOW, JOB,
                                         b"^0=ET4691125P\r", nonempty, nonempty])
        with tempfile.TemporaryDirectory() as directory:
            result = TransactionService(TransactionJournal(Path(directory) / "mailmode.jsonl"))\
                .execute_experimental_thai_mailmode_field1(
                    client, "4691125P", production_stopped_confirmed=True,
                    triggers_inhibited_confirmed=True, sole_writer_confirmed=True,
                    command_echo_disabled_confirmed=True,
                    operator_confirmations=("production stopped", "triggers inhibited", "sole writer", "echo off"))
        self.assertEqual(result.category, "MAIL_FIFO_NOT_EMPTY")
        self.assertNotIn(bytes.fromhex("5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D"), sock.sent)
        self.assertNotIn(b"^0!FF\r", sock.sent)

    def test_mailmode_field1_fails_when_postwrite_fifo_count_is_unexpected(self):
        empty = b"^0=SM256\t0\t0\t0\t0\r"
        two = b"^0=SM256\t2\t0\t0\t0\r"
        client, sock = self.make_client([READY, EX_LOW, JOB, b"^0=ET4691125P\r",
                                         empty, empty, two, two])
        with tempfile.TemporaryDirectory() as directory:
            result = TransactionService(TransactionJournal(Path(directory) / "mailmode.jsonl"))\
                .execute_experimental_thai_mailmode_field1(
                    client, "4691125P", production_stopped_confirmed=True,
                    triggers_inhibited_confirmed=True, sole_writer_confirmed=True,
                    command_echo_disabled_confirmed=True,
                    operator_confirmations=("production stopped", "triggers inhibited", "sole writer", "echo off"))
        self.assertEqual(result.category, "MAIL_FIFO_UNEXPECTED")
        self.assertEqual(result.outcome, "FAILED")
        self.assertNotIn(b"^0!FF\r", sock.sent)
        self.assertEqual(sock.sent.count(bytes.fromhex("5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D")), 1)

    def test_high_printgo_blocks_before_baseline_or_write(self):
        client, sock = self.make_client([READY, b"^0=EX10\t0\t120\t1\t0\t1\r", JOB])
        with tempfile.TemporaryDirectory() as directory:
            result = TransactionService(TransactionJournal(Path(directory) / "journal.jsonl")).execute(
                client, "NEW", write_safety_confirmed=True,
                command_echo_disabled_confirmed=True)
        self.assertEqual(result.outcome, "BLOCKED")
        self.assertEqual(result.category, "PRINTER_NOT_READY")
        self.assertEqual(sock.sent, [b"^0?RS\r", b"^0?EX\r", b"^0?JL\r"])
        self.assertNotIn(b"^0=ETNEW\r", sock.sent)

    def test_error_or_unknown_machine_state_never_passes_readiness(self):
        for raw in (b"^0=RS4\t4\t5\t0\t230\r", b"^0=RS4\t9\t0\t0\t230\r"):
            with self.subTest(raw=raw):
                client, sock = self.make_client([raw, EX_LOW, JOB])
                with tempfile.TemporaryDirectory() as directory:
                    result = TransactionService(TransactionJournal(Path(directory) / "j.jsonl")).execute(
                        client, "NEW", write_safety_confirmed=True,
                        command_echo_disabled_confirmed=True)
                self.assertEqual(result.outcome, "BLOCKED")
                self.assertNotIn(b"^0=ETNEW\r", sock.sent)

    def test_missing_operator_confirmations_send_no_printer_commands(self):
        client, sock = self.make_client([])
        with tempfile.TemporaryDirectory() as directory:
            result = TransactionService(TransactionJournal(Path(directory) / "j.jsonl")).execute(
                client, "NEW", write_safety_confirmed=False,
                command_echo_disabled_confirmed=True)
        self.assertEqual(result.category, "SAFETY_ATTESTATION_MISSING")
        self.assertEqual(sock.sent, [])

    def test_active_endpoint_lock_blocks_without_connecting_or_queueing(self):
        client, sock = self.make_client([])
        lock = printer_lock(client.settings.ip, client.settings.port)
        acquired = ThreadingEvent()
        release = ThreadingEvent()

        def hold_endpoint_lock():
            with lock:
                acquired.set()
                release.wait(2)

        holder = Thread(target=hold_endpoint_lock)
        holder.start()
        self.assertTrue(acquired.wait(2))
        try:
            with tempfile.TemporaryDirectory() as directory:
                result = TransactionService(
                    TransactionJournal(Path(directory) / "j.jsonl")).execute(
                        client, "NEW", write_safety_confirmed=True,
                        command_echo_disabled_confirmed=True)
            self.assertEqual(result.category, "APPLICATION_LOCK_BUSY")
            self.assertIsNone(client._socket)
            self.assertEqual(sock.sent, [])
        finally:
            release.set()
            holder.join(2)

    def test_journal_failure_before_write_prevents_the_write(self):
        client, sock = self.make_client([READY, EX_LOW, JOB, b"^0=ETOLD\r"])
        journal = Mock()
        journal.append.side_effect = OSError("disk full")
        result = TransactionService(journal).execute(
            client, "NEW", write_safety_confirmed=True,
            command_echo_disabled_confirmed=True)
        self.assertEqual(result.outcome, "FAILED")
        self.assertNotIn(b"^0=ETNEW\r", sock.sent)

    def test_mismatch_and_transport_failure_are_structured_without_retry(self):
        cases = (([READY, EX_LOW, JOB, b"^0=ETOLD\r", b"^0=ETOTHER\r"], "MISMATCH"),
                 ([READY, EX_LOW, JOB, b"^0=ETOLD\r", TimeoutError()], "FAILED"))
        for chunks, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                client, sock = self.make_client(chunks)
                result = TransactionService(TransactionJournal(Path(directory) / "j.jsonl")).execute(
                    client, "NEW", write_safety_confirmed=True,
                    command_echo_disabled_confirmed=True)
                self.assertEqual(result.outcome, expected)
                self.assertEqual(sock.sent.count(b"^0=ETNEW\r"), 1)
                self.assertEqual(sock.sent.count(b"^0?ET\r"), 2)


if __name__ == "__main__":
    unittest.main()
