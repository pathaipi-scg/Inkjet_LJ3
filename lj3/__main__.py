"""Run with python -m lj3. No network activity until an operator chooses an action."""

import argparse

from .client import CommunicationError, Event, LJ3Client
from .config import Settings, load_settings
from .protocol import PrinterStatus, build_command


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
    print("ASCII ExternText only. Communication testing does not verify Field 0 integration or physical printing.")
    print("Stopped printing is our test policy; the manuals do not establish it as an ET requirement.")
    print("No startup connection or commands. All actions below are manual.")
    print("Readback match does not prove physical printing. No Unicode mode.")
    try:
        while True:
            print(f"\nTarget: {settings.ip or '(not configured)'}:{settings.port}\n"
                  f"Status: {'connected' if client.connected else 'disconnected'}")
            print("\n1  Test TCP Connection\n2  Read Current ExternText\n"
                "3  Send Test Text (TEST123)\n4  Verify Last Sent Text\n"
                "5  Send Free Text\n6  Configure Target\n7  Read Printer Status\n0  Quit")
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
                elif action == "7":
                    display_printer_status(client.get_printer_status())
                else:
                    print("Choose an action from the menu.")
            except (ValueError, CommunicationError) as exc:
                print(f"ERROR: {exc}")
    except (EOFError, KeyboardInterrupt):
        print("\nExiting; interrupted writes may have reached the printer. No retry.")
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
