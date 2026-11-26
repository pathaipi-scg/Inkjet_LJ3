"""Run with python -m lj3. No network activity until an operator chooses an action."""

import argparse

from .client import CommunicationError, Event, LJ3Client
from .config import Settings, load_settings
from .db import DatabaseError
from .protocol import (PrinterStatus, build_command,
                      build_experimental_iso8859_11_frame,
                      encode_experimental_iso8859_11,
                      EXPERIMENTAL_THAI_FIELD1_TEXT,
                      build_experimental_thai_mailmode_field1_frame,
                      encode_experimental_thai_field1_iso8859_11_hypothesis)


def print_event(event: Event) -> None:
    print(f"[{event.timestamp}] {event.kind}: {event.message}")
    if event.data is not None:
        print(f"  bytes={event.data!r}\n  hex={event.data.hex(' ').upper()}")
    if event.elapsed_ms is not None:
        print(f"  elapsed_ms={event.elapsed_ms:.3f}")


def display_printer_status(status: PrinterStatus) -> None:
    nozzle_names = {0: "invalid (standby or initialization)", 1: "opens", 2: "is open",
                    3: "closes", 4: "is closed", 5: "in between"}
    machine_names = {1: "Standby", 2: "Initialization phase", 3: "Interval or Service Panel",
                     4: "Ready for Action", 5: "Ready for Printstart", 6: "Printing"}
    nozzle = nozzle_names.get(status.nozzle_state, f"unknown code {status.nozzle_state}")
    machine = machine_names.get(status.machine_state, f"unknown code {status.machine_state}")
    error = "no error" if status.error == 0 else f"error code {status.error}"
    headcover = {0: "closed", 1: "open"}.get(status.headcover, f"unknown code {status.headcover}")
    print("Printer status (=RS):")
    print(f"  Nozzle state: {status.nozzle_state} ({nozzle})")
    print(f"  Machine state: {status.machine_state} ({machine})")
    print(f"  Error: {status.error} ({error})")
    print(f"  Headcover: {status.headcover} ({headcover})")
    print(f"  ActSpeed: {status.act_speed} m/min")
    if status.additional_parameters:
        print("  Additional undocumented parameters (opaque): "
              f"{status.additional_parameters!r}; raw_tail={status.additional_parameters_raw!r}")


def display_snapshot(snapshot) -> None:
    display_printer_status(snapshot.status)
    print(f"  Loaded job (?JL): {snapshot.loaded_job!r}")
    print(f"  PrintGo signal (?EX Par6): {'HIGH' if snapshot.printgo_high else 'LOW' if snapshot.printgo_high is False else 'UNKNOWN'}")
    print(f"  Printing: {'YES' if snapshot.printing else 'NO' if snapshot.printing is False else 'UNKNOWN'}")
    print(f"  ExternText ready: {'YES' if snapshot.externtext_ready else 'NO' if snapshot.externtext_ready is False else 'UNKNOWN'}")
    print("  Print triggers inhibited: UNKNOWN (not reported by documented inquiries)")
    print(f"  Sampled at ({snapshot.sampled_at.tzinfo}): {snapshot.sampled_at.isoformat(timespec='milliseconds')}")


def configure(current: Settings) -> Settings:
    ip = input(f"Printer IPv4 [{current.ip or 'not configured'}]: ").strip() or current.ip
    port = input(f"TCP port [{current.port}]: ").strip()
    timeout = input(f"Timeout seconds [{current.timeout}]: ").strip()
    result = Settings(ip, int(port) if port else current.port,
                      float(timeout) if timeout else current.timeout)
    result.validate()
    return result


def main() -> int:
    argparse.ArgumentParser(description="Manual LJ3 ASCII ExternText test tool; no startup networking.").parse_args()
    try:
        settings = load_settings()
    except (ValueError, OSError) as exc:
        print(f"Configuration error: {exc}")
        return 2
    client = LJ3Client(settings, print_event)
    last_sent: str | None = None
    print("Leibinger Jet3 - Manual Phase 1 Tool")
    print("Standard ExternText paths are ASCII-only; Option 11 is one unverified Thai encoding hypothesis.")
    print("Communication testing does not verify Field 0 integration or physical printing.")
    print("Stopped printing is our test policy; the manuals do not establish it as an ET requirement.")
    print("No startup connection or commands. All actions below are manual.")
    print("Readback match does not prove physical printing. No supported general Unicode mode.")
    try:
        while True:
            print(f"\nTarget: {settings.ip or '(not configured)'}:{settings.port}\n"
                  f"Status: {'connected' if client.connected else 'disconnected'}")
            print("\n1  Test TCP Connection\n2  Read Current ExternText\n"
                "3  Send Test Text (TEST123)\n4  Verify Last Sent Text\n"
                "5  Send Free Text\n6  Configure Target\n"
                "7  Automatic ExternText Transaction\n8  Read Printer Status\n"
                "9  Database Status\n10 Recover Local Transaction Log\n"
                "11 Experimental Thai ISO-8859-11 =ET (UNVERIFIED)\n"
                "12 Experimental Thai Mailmode Field 1 (UNVERIFIED)\n0  Quit")
            action = input("Action: ").strip()
            try:
                if action == "0":
                    return 0
                if action == "6":
                    candidate = configure(settings)
                    client.disconnect()
                    settings = candidate
                    client = LJ3Client(settings, print_event)
                    last_sent = None
                    print("Session settings changed; .env was not modified.")
                elif action == "7":
                    from .transaction import TransactionService

                    text = input("ExternText to submit (printable ASCII): ")
                    if not text.isascii():
                        print("Unicode / Experimental - TRANSACTION BLOCKED; no printer command sent.")
                        continue
                    print("Automatic checks verify the expected CB-LOT-TEST.job, Ready for Action, "
                          "not printing, no reported error, and low PrintGo before the write.")
                    print("Trigger inhibition and !EM command-echo state cannot be queried. "
                          "The user has confirmed this application is the only ExternText writer.")
                    if input("Confirm external triggers are inhibited and !EM echo is disabled; "
                             "type SEND to continue: ") != "SEND":
                        print("Cancelled; no printer command sent.")
                        continue
                    result = TransactionService().execute(
                        client, text, write_safety_confirmed=True,
                        command_echo_disabled_confirmed=True,
                        expected_job_name="CB-LOT-TEST.job",
                        operator_confirmations=(
                            "external triggers inhibited",
                            "application is the only ExternText writer",
                            "!EM command echo disabled"))
                    print(f"Transaction ID: {result.transaction_id}\nOutcome: {result.outcome}"
                          f"\nCategory: {result.category}\nMessage: {result.message}")
                    if result.snapshot:
                        display_snapshot(result.snapshot)
                    print(f"Baseline: {result.baseline_text!r}\nRequested: {result.requested_text!r}"
                          f"\nReadback: {result.readback_text!r}\nElapsed: {result.elapsed_ms:.3f} ms")
                    print(f"Local durable journal: {'SAVED' if result.journaled else 'FAILED'}")
                    try:
                        from .db import SqlRepository
                        SqlRepository().persist_record(result.journal_record() | {
                            "printer_ip": settings.ip, "printer_port": settings.port})
                        print("Database transaction/error persistence: SAVED")
                    except Exception as exc:
                        from .transaction import TransactionService
                        db_error_logged = TransactionService().record_database_error(
                            client, result.transaction_id, exc)
                        print(f"Database transaction/error persistence: FAILED ({type(exc).__name__}); "
                              "no credentials or driver details displayed. "
                              f"Local database-failure event: {'SAVED' if db_error_logged else 'FAILED'}. "
                              "Use recovery after DB access is restored.")
                    last_sent = result.requested_text if result.outcome in {"VERIFIED", "MISMATCH"} else None
                    if result.outcome == "VERIFIED":
                        print("VERIFIED - exact same-session readback; physical printing is unverified.")
                    elif result.outcome == "MISMATCH":
                        print("MISMATCH - do not retry automatically; inspect printer state.")
                    else:
                        print("No automatic retry. If a write may have been transmitted, inspect using read-only inquiry.")
                elif action == "8":
                    from .status import read_printer_snapshot
                    from .transaction import TransactionService
                    status_events = []
                    previous_sink = client._on_event

                    def capture_status_event(event: Event) -> None:
                        status_events.append(event)
                        if previous_sink is not None:
                            previous_sink(event)

                    client._on_event = capture_status_event
                    try:
                        snapshot = read_printer_snapshot(client)
                    finally:
                        client._on_event = previous_sink
                    display_snapshot(snapshot)
                    status_record = TransactionService().record_status_snapshot(
                        client, snapshot, tuple(status_events))
                    if status_record.journaled:
                        try:
                            from .db import SqlRepository
                            SqlRepository().persist_record(status_record.journal_record() | {
                                "printer_ip": settings.ip, "printer_port": settings.port})
                            print("Status sample: saved to local journal and SQL Server.")
                        except Exception as exc:
                            db_error_logged = TransactionService().record_database_error(
                                client, status_record.transaction_id, exc)
                            print(f"Status sample: saved locally; SQL persistence failed ({type(exc).__name__}); "
                                  f"database-failure event {'SAVED' if db_error_logged else 'FAILED'}.")
                    else:
                        print("Status sample could not be durably written to the local journal.")
                elif action == "11":
                    from .transaction import TransactionService
                    experimental_text = "สีเทานก"
                    payload = encode_experimental_iso8859_11(experimental_text)
                    frame = build_experimental_iso8859_11_frame(experimental_text)
                    print("EXPERIMENTAL ONLY: ISO-8859-11 is an unverified hypothesis for this printer/font.")
                    print("The manuals require hexadecimal text with Unicode fonts but do not confirm this encoding.")
                    print("Reported font=16x10_SCG; character-set selector is disabled; no job/font/settings will be changed.")
                    print(f"Exact text: {experimental_text!r}; Unicode characters={len(experimental_text)}; encoded bytes={len(payload)}")
                    print(f"ISO-8859-11 payload hex: {payload.hex(' ').upper()}")
                    print(f"Complete =ET TCP frame hex: {frame.hex(' ').upper()}")
                    print("Preflight requires active job CB-LOT-TEST.job, Ready for Action, not printing, error 0, and PrintGo LOW.")
                    print("The operator must confirm production stopped, external triggers inhibited, this is the only writer, and !EM echo is disabled.")
                    if input("Confirm ALL four conditions and type SEND for exactly one experimental transmission: ") != "SEND":
                        print("Cancelled; no connection or printer command sent.")
                        continue
                    confirmations = (
                        "production stopped",
                        "external triggers inhibited",
                        "application is the only ExternText writer",
                        "!EM command echo disabled",
                    )
                    result = TransactionService().execute_experimental_iso8859_11(
                        client, write_safety_confirmed=True,
                        command_echo_disabled_confirmed=True,
                        operator_confirmations=confirmations)
                    print(f"Transaction ID: {result.transaction_id}\nOutcome: {result.outcome}"
                          f"\nCategory: {result.category}\nMessage: {result.message}")
                    if result.snapshot:
                        display_snapshot(result.snapshot)
                    print(f"Baseline: {result.baseline_text!r}\nRequested: {result.requested_text!r}"
                          f"\nReadback: {result.readback_text!r}\nElapsed: {result.elapsed_ms:.3f} ms")
                    print(f"Local durable journal: {'SAVED' if result.journaled else 'FAILED'}")
                    try:
                        from .db import SqlRepository
                        SqlRepository().persist_record(result.journal_record())
                        print("Database transaction/error persistence: SAVED")
                    except Exception as exc:
                        db_error_logged = TransactionService().record_database_error(
                            client, result.transaction_id, exc)
                        print(f"Database persistence failed ({type(exc).__name__}); "
                              f"local failure event {'SAVED' if db_error_logged else 'FAILED'}.")
                    if result.outcome == "VERIFIED":
                        print("BYTE MATCH ONLY - printer visual rendering is unverified; await operator inspection.")
                    elif result.outcome == "MISMATCH":
                        print("EXPERIMENTAL BYTE MISMATCH - do not retry or send another encoding.")
                    else:
                        print("Experimental outcome not verified. Do not retry; inspect current value before further action.")
                elif action == "12":
                    from .transaction import TransactionService
                    payload = encode_experimental_thai_field1_iso8859_11_hypothesis(
                        EXPERIMENTAL_THAI_FIELD1_TEXT)
                    frame = build_experimental_thai_mailmode_field1_frame(
                        EXPERIMENTAL_THAI_FIELD1_TEXT)
                    print("EXPERIMENTAL ONLY: this is one =MR Mailmode record for Field 1, not =ET.")
                    print("ISOB_Thai encoding is unverified. For this exact text, ISO-8859-11, TIS-620, and Windows-874 codecs produce the same candidate bytes; that does not prove the font mapping.")
                    print("The original manuals require hex-coded data for Unicode fonts; the reported font name lacks the documented '~' Unicode-font marker. Confirm the job's EXTTXT parameter 3 is Field Number 1 and the font's byte mapping before proceeding.")
                    print(f"Field 1 text: {EXPERIMENTAL_THAI_FIELD1_TEXT!r}; candidate bytes: {payload.hex(' ').upper()}")
                    print(f"Complete =MR frame hex: {frame.hex(' ').upper()}")
                    if input("Type FIELD 1 CONFIRMED only if the loaded job's EXTTXT parameter 3 is 1: ") != "FIELD 1 CONFIRMED":
                        print("Cancelled; no connection or printer command sent.")
                        continue
                    if input("Type USE HYPOTHESIS to authorize this unverified single-byte mapping for the isolated test: ") != "USE HYPOTHESIS":
                        print("Cancelled; no connection or printer command sent.")
                        continue
                    expected_field0 = input("Expected current Field 0 Lot Number (exact printable ASCII): ")
                    if (not expected_field0.isascii() or not expected_field0.isprintable() or
                            not expected_field0 or "\\" in expected_field0):
                        print("Invalid baseline; no connection or printer command sent.")
                        continue
                    if input("Confirm production stopped, triggers inhibited, sole writer, and !EM echo disabled; type SEND: ") != "SEND":
                        print("Cancelled; no connection or printer command sent.")
                        continue
                    confirmations = (
                        "production stopped", "external triggers inhibited",
                        "application is the only ExternText writer",
                        "!EM command echo disabled")
                    result = TransactionService().execute_experimental_thai_mailmode_field1(
                        client, expected_field0,
                        production_stopped_confirmed=True,
                        triggers_inhibited_confirmed=True,
                        sole_writer_confirmed=True,
                        command_echo_disabled_confirmed=True,
                        operator_confirmations=confirmations)
                    print(f"Transaction ID: {result.transaction_id}\nOutcome: {result.outcome}"
                          f"\nCategory: {result.category}\nMessage: {result.message}")
                    if result.snapshot:
                        display_snapshot(result.snapshot)
                    print(f"Field 0 baseline: {result.baseline_text!r}\nField 1 requested: {result.requested_text!r}"
                          f"\nField 0 after test: {result.readback_text!r}\nElapsed: {result.elapsed_ms:.3f} ms")
                    print(f"Local durable journal: {'SAVED' if result.journaled else 'FAILED'}")
                    if result.outcome == "STAGED_UNVERIFIED":
                        print("STOP: one FIFO entry remains staged. Do not start printing. This application will not clear it; obtain separate approval and isolate the device before cleanup.")
                    try:
                        from .db import SqlRepository
                        SqlRepository().persist_record(result.journal_record())
                        print("Database transaction/status persistence: SAVED")
                    except Exception as exc:
                        db_error_logged = TransactionService().record_database_error(
                            client, result.transaction_id, exc)
                        print(f"Database persistence failed ({type(exc).__name__}); "
                              f"local failure event {'SAVED' if db_error_logged else 'FAILED'}.")
                    print("No =ET was sent. No print-start command was sent. Mailmode content/rendering is not read back.")
                elif action == "9":
                    from .db import SqlRepository, load_database_settings
                    db_settings = load_database_settings()
                    info = SqlRepository(db_settings).inspect()
                    print(f"SQL target: {db_settings.server}:{db_settings.port}; database={db_settings.database}")
                    print(f"SQL Server version: {info['version']} (2019: {info['sql_server_2019']})")
                    print(f"Permissions: sysadmin={info['is_sysadmin']}, create table={info['create_table']}, "
                          f"create view={info['create_view']}, alter schema={info['alter_schema']}")
                    print(f"inkjet schema exists={info['schema_exists']}; tables={info['tables']}; views={info['views']}")
                    print(f"Missing expected tables={info['missing_tables']}; views={info['missing_views']}")
                elif action == "10":
                    from .db import SqlRepository
                    imported, failed = SqlRepository().recover()
                    print(f"Database recovery complete: {imported} records processed; {failed} failed. "
                          "Recovery performs no printer commands and is idempotent.")
                elif action == "1":
                    try:
                        client.connect()
                        print("TCP CONNECTION OK")
                        print("TCP only; this does not prove printer identity or command support.")
                    except (ValueError, CommunicationError) as exc:
                        print(f"TCP CONNECTION FAILED\nERROR: {exc}")
                elif action in ("3", "5"):
                    text = "TEST123" if action == "3" else input("Free Text (ASCII; spaces are preserved): ")
                    if not text.isascii():
                        print("Unicode / Experimental - SEND BLOCKED")
                        print("The LJ3 manual requires hexadecimal text for Unicode fonts/jobs, not UTF-8. "
                              "Unicode length limits and readback behavior are not fully specified. "
                              "No connection or command sent. Prove ASCII operation first; "
                              "confirm the font/job and transmission rules before a controlled Thai experiment.")
                        continue
                    wire = build_command("=ET", text)
                    settings.validate()
                    print(f"Target: {settings.ip}:{settings.port}\nText to send:\n{text}\n"
                          f"Preview: {wire!r}\nHex: {wire.hex(' ').upper()}")
                    print("Communication-only write - confirm at the printer: production is stopped; print triggers are inhibited; "
                          "no other controller is writing ExternText.")
                    print("The current print job will not be modified. Field 0 integration and physical printing remain NOT TESTED.")
                    if input("Type SEND to confirm and transmit once: ") != "SEND":
                        print("Cancelled; no connection or command sent.")
                        continue
                    print("Same-session readback is ambiguous if optional command echo (!EM) is enabled.")
                    if input("Type ECHO OFF only if printer command echo is confirmed disabled: ") != "ECHO OFF":
                        print("Cancelled; no connection or command sent.")
                        continue
                    last_sent = None  # An uncertain write invalidates previous comparison state.
                    client.set_external_text(text, write_safety_confirmed=True,
                                             command_echo_disabled_confirmed=True)
                    last_sent = text
                    print("SENT - UNVERIFIED")
                elif action == "2":
                    print(f"Current Jet3 ExternText:\n{client.get_external_text()}")
                elif action == "4":
                    if last_sent is None:
                        print("No completed send for this target in this session. Use Read after an uncertain write.")
                        continue
                    print(f"Sent (exact repr): {last_sent!r}")
                    try:
                        result = client.verify_external_text(last_sent)
                    except (ValueError, CommunicationError) as exc:
                        print(f"Result:\nCOMMUNICATION ERROR\nERROR: {exc}")
                        continue
                    print(f"Jet3 Readback (exact repr): {result.actual!r}\n\nResult:\n"
                          f"{'VERIFIED' if result.matched else 'MISMATCH'}")
                    print("Comparison only; verify the job and a physical sample separately.")
                else:
                    print("Choose an action from the menu.")
            except (ValueError, CommunicationError, DatabaseError) as exc:
                print(f"ERROR: {exc}")
    except (EOFError, KeyboardInterrupt):
        print("\nExiting; interrupted writes may have reached the printer. No retry.")
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
