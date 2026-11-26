"""One-shot, serialized ExternText update with status gates and exact readback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .client import CommunicationError, Event, LJ3Client, ResponseTimeout
from .journal import TransactionJournal, as_iso
from .locking import printer_lock
from .protocol import (ProtocolError, build_command,
                       encode_experimental_iso8859_11,
                       EXPERIMENTAL_THAI_FIELD1_TEXT,
                       encode_experimental_thai_field1_iso8859_11_hypothesis,
                       build_experimental_thai_mailmode_field1_frame)
from .status import PrinterSnapshot, read_printer_snapshot


APP_TIMEZONE = timezone(timedelta(hours=7), "Asia/Bangkok")
@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    outcome: str
    category: str
    requested_text: str
    baseline_text: str | None
    readback_text: str | None
    message: str
    started_at: str
    completed_at: str
    elapsed_ms: float
    snapshot: PrinterSnapshot | None = None
    events: tuple[Event, ...] = ()
    journaled: bool = True
    printer_ip: str = ""
    printer_port: int = 0

    @property
    def verified(self) -> bool:
        return self.outcome == "VERIFIED" and self.readback_text == self.requested_text

    def journal_record(self) -> dict[str, Any]:
        snapshot = None
        if self.snapshot:
            status = self.snapshot.status
            extern = self.snapshot.extern_state
            snapshot = {
                "sampled_at": as_iso(self.snapshot.sampled_at),
                "machine_state": status.machine_state,
                "nozzle_state": status.nozzle_state,
                "printer_error": status.error,
                "headcover": status.headcover,
                "act_speed": str(status.act_speed),
                "extern_actual_speed": str(extern.actual_speed),
                "extern_max_speed": str(extern.max_speed),
                "inputs": extern.inputs,
                "direction": extern.direction,
                "printgo": extern.printgo,
                "loaded_job": self.snapshot.loaded_job,
                "printing": self.snapshot.printing,
                "externtext_ready": self.snapshot.externtext_ready,
                "production_stopped": None,
                "trigger_inhibited": None,
                "command_echo_enabled": None,
                "unknown_status_fields": [item.decode("ascii", errors="replace")
                                           for item in status.additional_parameters],
            }
        return {
            "transaction_id": self.transaction_id,
            "outcome": self.outcome,
            "category": self.category,
            "printer_ip": self.printer_ip,
            "printer_port": self.printer_port,
            "requested_text": self.requested_text,
            "baseline_text": self.baseline_text,
            "readback_text": self.readback_text,
            "message": self.message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_ms": self.elapsed_ms,
            "snapshot": snapshot,
            "events": [
                {"timestamp": item.timestamp, "kind": item.kind, "message": item.message,
                 "data_hex": item.data.hex() if item.data is not None else None,
                 "elapsed_ms": item.elapsed_ms}
                for item in self.events
            ],
        }


class TransactionService:
    def __init__(self, journal: TransactionJournal | None = None):
        self.journal = journal or TransactionJournal()

    def execute(self, client: LJ3Client, text: str, *,
                write_safety_confirmed: bool,
                command_echo_disabled_confirmed: bool,
                expected_job_name: str | None = None,
                operator_confirmations: tuple[str, ...] = ()) -> TransactionResult:
        # Validate before locks, sockets, or local file creation.
        try:
            build_command("=ET", text)
        except (ValueError, TypeError) as exc:
            return self._result(client, str(uuid4()), "BLOCKED", "INVALID_TEXT", text,
                                None, None, str(exc), datetime.now(APP_TIMEZONE), None)
        if not write_safety_confirmed:
            return self._result(client, str(uuid4()), "BLOCKED", "SAFETY_ATTESTATION_MISSING", text,
                                None, None, "Stopped production, inhibited triggers, and no competing writer must be confirmed.",
                                datetime.now(APP_TIMEZONE), None)
        if not command_echo_disabled_confirmed:
            return self._result(client, str(uuid4()), "BLOCKED", "ECHO_STATE_UNKNOWN", text,
                                None, None, "The manual documents enabling !EM only; echo state cannot be queried and must be confirmed disabled.",
                                datetime.now(APP_TIMEZONE), None)

        lock = printer_lock(client.settings.ip, client.settings.port)
        # Block rather than queue a potentially stale requested value behind another update.
        if not lock.acquire(blocking=False):
            return self._result(client, str(uuid4()), "BLOCKED", "APPLICATION_LOCK_BUSY", text,
                                None, None, "Another in-process transaction for this printer is active.",
                                datetime.now(APP_TIMEZONE), None)
        try:
            return self._execute_locked(client, text, expected_job_name, operator_confirmations)
        finally:
            lock.release()

    def execute_experimental_iso8859_11(self, client: LJ3Client, *,
                                        write_safety_confirmed: bool,
                                        command_echo_disabled_confirmed: bool,
                                        operator_confirmations: tuple[str, ...]) -> TransactionResult:
        """One isolated, explicitly experimental Thai transaction; no fallback encoding."""
        text = "สีเทานก"
        if not write_safety_confirmed:
            return self._result(client, str(uuid4()), "BLOCKED", "SAFETY_ATTESTATION_MISSING",
                                text, None, None,
                                "Stopped production, inhibited triggers, and sole-writer status must be confirmed.",
                                datetime.now(APP_TIMEZONE), None)
        if not command_echo_disabled_confirmed:
            return self._result(client, str(uuid4()), "BLOCKED", "ECHO_STATE_UNKNOWN", text,
                                None, None, "Command echo must be confirmed disabled.",
                                datetime.now(APP_TIMEZONE), None)
        try:
            payload = encode_experimental_iso8859_11(text)
        except ValueError as exc:
            return self._result(client, str(uuid4()), "BLOCKED", "EXPERIMENTAL_ENCODING_UNAVAILABLE",
                                text, None, None, str(exc), datetime.now(APP_TIMEZONE), None)
        lock = printer_lock(client.settings.ip, client.settings.port)
        if not lock.acquire(blocking=False):
            return self._result(client, str(uuid4()), "BLOCKED", "APPLICATION_LOCK_BUSY", text,
                                None, None, "Another in-process transaction for this printer is active.",
                                datetime.now(APP_TIMEZONE), None)
        try:
            return self._execute_locked(client, text, "CB-LOT-TEST.job", operator_confirmations,
                                        experimental_payload=payload)
        finally:
            lock.release()

    def execute_experimental_thai_mailmode_field1(
        self, client: LJ3Client, expected_field0_text: str, *,
        production_stopped_confirmed: bool,
        triggers_inhibited_confirmed: bool,
        sole_writer_confirmed: bool,
        command_echo_disabled_confirmed: bool,
        operator_confirmations: tuple[str, ...],
    ) -> TransactionResult:
        """Stage one fixed Field 1 hypothesis; never writes or reads Field 0 as data."""
        text = EXPERIMENTAL_THAI_FIELD1_TEXT
        try:
            build_command("=ET", expected_field0_text)  # Validate the protected baseline as printable ASCII.
            payload = encode_experimental_thai_field1_iso8859_11_hypothesis(text)
            build_experimental_thai_mailmode_field1_frame(text)
        except (ValueError, TypeError) as exc:
            return self._result(client, str(uuid4()), "BLOCKED", "INVALID_EXPERIMENT_INPUT",
                                text, None, None, str(exc), datetime.now(APP_TIMEZONE), None)
        if not all((production_stopped_confirmed, triggers_inhibited_confirmed,
                    sole_writer_confirmed, command_echo_disabled_confirmed)):
            return self._result(client, str(uuid4()), "BLOCKED", "SAFETY_ATTESTATION_MISSING",
                                text, None, None,
                                "Stopped production, inhibited triggers, sole-writer, and disabled echo must be confirmed.",
                                datetime.now(APP_TIMEZONE), None)
        lock = printer_lock(client.settings.ip, client.settings.port)
        if not lock.acquire(blocking=False):
            return self._result(client, str(uuid4()), "BLOCKED", "APPLICATION_LOCK_BUSY",
                                text, None, None,
                                "Another in-process operation for this printer is active.",
                                datetime.now(APP_TIMEZONE), None)
        try:
            return self._execute_experimental_mailmode_locked(
                client, expected_field0_text, payload, operator_confirmations)
        finally:
            lock.release()

    def _execute_experimental_mailmode_locked(
        self, client: LJ3Client, expected_field0_text: str,
        payload: bytes, operator_confirmations: tuple[str, ...],
    ) -> TransactionResult:
        transaction_id = str(uuid4())
        started = datetime.now(APP_TIMEZONE)
        baseline: str | None = None
        snapshot: PrinterSnapshot | None = None
        events: list[Event] = []
        previous_sink = client._on_event

        def capture(event: Event) -> None:
            events.append(event)
            if previous_sink is not None:
                previous_sink(event)

        client._on_event = capture
        try:
            client._emit("SAFETY", "Mailmode operator confirmations: " + "; ".join(operator_confirmations))
            snapshot = read_printer_snapshot(client)
            blockers = snapshot.blockers()
            if blockers:
                return self._result(client, transaction_id, "BLOCKED", "PRINTER_NOT_READY",
                                    EXPERIMENTAL_THAI_FIELD1_TEXT, None, None,
                                    "; ".join(blockers), started, snapshot, events)
            if not snapshot.has_loaded_job("CB-LOT-TEST.job"):
                return self._result(client, transaction_id, "BLOCKED", "EXPECTED_JOB_MISMATCH",
                                    EXPERIMENTAL_THAI_FIELD1_TEXT, None, None,
                                    f"Expected loaded job 'CB-LOT-TEST.job'; printer reports {snapshot.loaded_job_name!r}.",
                                    started, snapshot, events)

            baseline = client.get_external_text()
            if baseline != expected_field0_text:
                return self._result(client, transaction_id, "BLOCKED", "FIELD0_BASELINE_MISMATCH",
                                    EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, None,
                                    "Current ?ET does not match the operator-supplied Lot Number; no Mailmode record sent.",
                                    started, snapshot, events)

            fifo_before_1 = client.get_mail_status()
            fifo_before_2 = client.get_mail_status()
            if fifo_before_1.fifo_entries != 0 or fifo_before_2.fifo_entries != 0 or fifo_before_1 != fifo_before_2:
                return self._result(client, transaction_id, "BLOCKED", "MAIL_FIFO_NOT_EMPTY",
                                    EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, None,
                                    "Both fresh ?SM samples must show an empty FIFO; no records were cleared or sent.",
                                    started, snapshot, events)

            frame = build_experimental_thai_mailmode_field1_frame(EXPERIMENTAL_THAI_FIELD1_TEXT)
            client._emit("EXPERIMENT",
                         "Fixed Field 1 payload; ISO-8859-11/TIS-620/Windows-874 shared-byte hypothesis; "
                         "ISOB_Thai mapping is unverified; record number 0; one field; no =ET/Field 0 write.",
                         payload)
            client._emit("PREVIEW", f"Complete experimental =MR frame hex={frame.hex(' ').upper()}.", frame)
            intent = self._record(client, transaction_id, "WRITE_INTENT", "WRITE_PENDING",
                                  EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, None,
                                  "Durable intent before one =MR record; preflight FIFO was empty.",
                                  started, datetime.now(APP_TIMEZONE), snapshot, events)
            intent["mailmode_field_number"] = 1
            intent["encoding_hypothesis"] = "ISO-8859-11 shared bytes with TIS-620/Windows-874; ISOB_Thai map unverified"
            intent["mail_record_number"] = 0
            intent["mail_fifo_before"] = [fifo_before_1.fifo_entries, fifo_before_2.fifo_entries]
            self.journal.append(intent)

            client.send_experimental_thai_mailmode_field1(
                EXPERIMENTAL_THAI_FIELD1_TEXT,
                production_stopped_confirmed=True,
                triggers_inhibited_confirmed=True,
                sole_writer_confirmed=True,
                command_echo_disabled_confirmed=True,
                empty_fifo_preflight_confirmed=True)
            fifo_after_1 = client.get_mail_status()
            fifo_after_2 = client.get_mail_status()

            if (fifo_after_1.fifo_entries != 1 or fifo_after_2.fifo_entries != 1 or
                    fifo_after_1 != fifo_after_2):
                return self._result(client, transaction_id, "FAILED", "MAIL_FIFO_UNEXPECTED",
                                    EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, None,
                                    "After the one =MR attempt, two ?SM samples did not prove exactly one staged record; "
                                    "no !FF was sent and no retry is allowed.", started, snapshot, events)

            current_field0 = client.get_external_text()

            if current_field0 != baseline:
                # The mail payload is never resent and !FF is not used to mask a changed Field 0.
                return self._result(client, transaction_id, "FAILED", "FIELD0_CHANGED_UNEXPECTEDLY",
                                    EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, current_field0,
                                    "Field 0 ?ET changed after =MR; no retry or queue clear was attempted.",
                                    started, snapshot, events)

            result = self._result(
                client, transaction_id, "STAGED_UNVERIFIED", "EXPERIMENTAL_MAILMODE_FIELD1_STAGED",
                EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, current_field0,
                "One Field 1 =MR candidate was staged; two stable ?SM samples reported one FIFO entry and "
                "?ET remained unchanged. Payload identity/rendering is unverified. FIFO was intentionally left untouched; "
                "do not start printing. Obtain separate approval and isolate the device before any cleanup.",
                started, snapshot, events)
            return result
        except (CommunicationError, ProtocolError, OSError, ValueError) as exc:
            category = self._error_category(exc, events)
            result = self._result(client, transaction_id, "FAILED", category,
                                  EXPERIMENTAL_THAI_FIELD1_TEXT, baseline, None,
                                  self._safe_message(exc), started, snapshot, events)
            return result
        finally:
            client._on_event = previous_sink

    def record_status_snapshot(self, client: LJ3Client,
                                         snapshot: PrinterSnapshot,
                                         events: tuple[Event, ...] = ()) -> TransactionResult:
        """Durably record a read-only status sample; sends no additional commands."""
        now = datetime.now(APP_TIMEZONE)
        return self._result(client, str(uuid4()), "STATUS_ONLY", "READ_ONLY_STATUS", "",
                                     None, None, "Read-only ?RS/?EX/?JL status sample.", now, snapshot,
                                     list(events))

    def record_database_error(self, client: LJ3Client, transaction_id: str,
                              error: Exception) -> bool:
        """Record a sanitized SQL outage locally; no credentials/driver text are retained."""
        now = datetime.now(APP_TIMEZONE)
        record = {
            "record_type": "DATABASE_ERROR",
            "error_event_id": str(uuid4()),
            "transaction_id": transaction_id,
            "printer_ip": client.settings.ip,
            "printer_port": client.settings.port,
            "category": "DATABASE_PERSISTENCE_FAILED",
            "error_code": type(error).__name__,
            "message": f"SQL persistence failed ({type(error).__name__}); details suppressed.",
            "occurred_at": as_iso(now),
        }
        try:
            self.journal.append(record)
            return True
        except OSError:
            return False

    def _execute_locked(self, client: LJ3Client, text: str,
                        expected_job_name: str | None,
                        operator_confirmations: tuple[str, ...], *,
                        experimental_payload: bytes | None = None) -> TransactionResult:
        transaction_id = str(uuid4())
        started = datetime.now(APP_TIMEZONE)
        baseline: str | None = None
        snapshot: PrinterSnapshot | None = None
        events: list[Event] = []
        previous_sink = client._on_event

        def capture(event: Event) -> None:
            events.append(event)
            if previous_sink is not None:
                previous_sink(event)

        client._on_event = capture
        try:
            if operator_confirmations:
                client._emit("SAFETY", "Operator confirmations: " + "; ".join(operator_confirmations))
            snapshot = read_printer_snapshot(client)
            blockers = snapshot.blockers()
            if blockers:
                return self._result(client, transaction_id, "BLOCKED", "PRINTER_NOT_READY", text,
                                    None, None, "; ".join(blockers), started, snapshot, events)
            if expected_job_name and not snapshot.has_loaded_job(expected_job_name):
                return self._result(client, transaction_id, "BLOCKED", "EXPECTED_JOB_MISMATCH", text,
                                    None, None,
                                    f"Expected loaded job {expected_job_name!r}; printer reports "
                                    f"{snapshot.loaded_job_name!r}.", started, snapshot, events)
            baseline = client.get_external_text()
            if experimental_payload is not None:
                client._emit(
                    "EXPERIMENT",
                    "Unverified ISO-8859-11 hypothesis; "
                    f"font=16x10_SCG; character-set selector disabled; "
                    f"payload_length={len(experimental_payload)}; "
                    f"payload_hex={experimental_payload.hex(' ').upper()}; "
                    "no UTF-8 or fallback encoding used.",
                    experimental_payload)
            record = self._record(client, transaction_id, "WRITE_INTENT", "WRITE_PENDING", text,
                                  baseline, None, "Durable intent recorded before the single write.",
                                  started, datetime.now(APP_TIMEZONE), snapshot, events)
            self.journal.append(record)
            if experimental_payload is not None:
                # This dedicated method sends exactly one isolated ISO-8859-11 frame.
                client.set_external_text_experimental_iso8859_11(
                    text, write_safety_confirmed=True,
                    command_echo_disabled_confirmed=True)
                _, readback_payload = client.get_external_text_experimental_raw()
                readback = readback_payload.decode("iso8859_11", errors="replace")
                outcome = "VERIFIED" if readback_payload == experimental_payload else "MISMATCH"
                category = ("EXPERIMENTAL_ISO8859_11_MATCH" if outcome == "VERIFIED"
                            else "EXPERIMENTAL_ISO8859_11_MISMATCH")
                message = ("Experimental ISO-8859-11 bytes matched exactly on same-session ?ET; "
                           "visual character rendering remains unverified.")
            else:
                # This is the only standard ASCII printer write in the transaction path.
                client.set_external_text(text, write_safety_confirmed=True,
                                         command_echo_disabled_confirmed=True)
                readback = client.get_external_text()
                outcome = "VERIFIED" if readback == text else "MISMATCH"
                category = "SUCCESS" if outcome == "VERIFIED" else "READBACK_MISMATCH"
                message = "Exact same-session readback comparison completed."
            result = self._result(client, transaction_id, outcome, category, text, baseline,
                                  readback, message,
                                  started, snapshot, events)
            return result
        except (CommunicationError, ProtocolError, OSError, ValueError) as exc:
            category = self._error_category(exc, events)
            message = self._safe_message(exc)
            result = self._result(client, transaction_id, "FAILED", category, text, baseline,
                                  None, message, started, snapshot, events)
            return result
        finally:
            client._on_event = previous_sink

    @staticmethod
    def _error_category(exc: Exception, events: list[Event]) -> str:
        if isinstance(exc, ResponseTimeout):
            return "TIMEOUT"
        if isinstance(exc, ProtocolError):
            return "PROTOCOL_ERROR"
        if isinstance(exc, CommunicationError):
            return "COMMUNICATION_ERROR"
        if isinstance(exc, OSError):
            return "JOURNAL_ERROR"
        if any(event.kind == "TX" for event in events):
            return "TRANSACTION_ERROR"
        return "STATUS_ERROR"

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        # SQL credentials are not involved here; still avoid exception reprs/tracebacks.
        return f"{type(exc).__name__}: {str(exc)[:500]}"

    def _result(self, client: LJ3Client, transaction_id: str, outcome: str, category: str,
                text: str, baseline: str | None, readback: str | None, message: str,
                started: datetime, snapshot: PrinterSnapshot | None,
                events: list[Event] | None = None) -> TransactionResult:
        finished = datetime.now(APP_TIMEZONE)
        elapsed = max(0.0, (finished - started).total_seconds() * 1000)
        result = TransactionResult(transaction_id, outcome, category, text, baseline,
                                   readback, message, as_iso(started), as_iso(finished),
                                   elapsed, snapshot, tuple(events or ()), True,
                                   client.settings.ip, client.settings.port)
        journaled = False
        try:
            record = result.journal_record()
            record["printer_ip"] = client.settings.ip
            record["printer_port"] = client.settings.port
            self.journal.append(record)
            journaled = True
        except OSError:
            # The caller receives the failure; no printer write may proceed without a durable intent.
            pass
        return TransactionResult(transaction_id, outcome, category, text, baseline,
                     readback, message, as_iso(started), as_iso(finished),
                                 elapsed, snapshot, tuple(events or ()), journaled,
                                 client.settings.ip, client.settings.port)

    @staticmethod
    def _record(client: LJ3Client, transaction_id: str, event_type: str, outcome: str,
                text: str, baseline: str | None, readback: str | None, message: str,
                started: datetime, finished: datetime, snapshot: PrinterSnapshot,
                events: list[Event]) -> dict[str, Any]:
        interim = TransactionResult(transaction_id, outcome, event_type, text, baseline,
                                    readback, message, as_iso(started), as_iso(finished),
                                    (finished - started).total_seconds() * 1000, snapshot,
                                    tuple(events))
        record = interim.journal_record()
        record["printer_ip"] = client.settings.ip
        record["printer_port"] = client.settings.port
        return record
