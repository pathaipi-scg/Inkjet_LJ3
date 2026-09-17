"""Run with python -m lj3. No network activity until an operator chooses an action."""

import argparse

from .client import CommunicationError, Event, LJ3Client
from .config import Settings, load_settings
from .protocol import build_command


def print_event(event: Event) -> None:
    print(f"[{event.timestamp}] {event.kind}: {event.message}")
    if event.data is not None:
        print(f"  bytes={event.data!r}\n  hex={event.data.hex(' ').upper()}")


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
    print("ASCII / Field 0 only. Phase 1 commissioning policy: printing stopped, test job prepared.")
    print("Stopped printing is our test policy; the manuals do not establish it as an ET requirement.")
    print("No startup connection or commands. All actions below are manual.")
    print("Readback match does not prove physical printing. No Unicode mode.")
    try:
        while True:
            print(f"\nTarget: {settings.ip or '(not configured)'}:{settings.port}\n"
                  f"Status: {'connected' if client.connected else 'disconnected'}")
            print("\n1  Test TCP Connection\n2  Read Current ExternText\n"
                  "3  Send Test Text (TEST123)\n4  Verify Last Sent Text\n"
                  "5  Send Free Text\n6  Configure Target\n0  Quit")
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
                    finally:
                        client.disconnect()
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
                    print("Phase 1 commissioning policy - confirm at the printer: production is stopped; a non-Unicode test job uses "
                          "Field 0; lengths/offsets match this value.")
                    if input("Type SEND to confirm and transmit once: ") != "SEND":
                        print("Cancelled; no connection or command sent.")
                        continue
                    last_sent = None  # An uncertain write invalidates previous comparison state.
                    client.set_external_text(text, stopped_ascii_job_confirmed=True)
                    last_sent = text
                    print("SENT - UNVERIFIED")
                elif action == "2":
                    print(f"Current Jet3 ExternText:\n{client.get_external_text()}")
                elif action == "4":
                    if last_sent is None:
                        print("No completed send for this target in this session. Use Read after an uncertain write.")
                        continue
                    print(f"Sent:\n{last_sent}")
                    try:
                        result = client.verify_external_text(last_sent)
                    except (ValueError, CommunicationError) as exc:
                        print(f"Result:\nCOMMUNICATION ERROR\nERROR: {exc}")
                        continue
                    print(f"Jet3 Readback:\n{result.actual}\n\nResult:\n"
                          f"{'VERIFIED' if result.matched else 'MISMATCH'}")
                    print("Comparison only; verify the job and a physical sample separately.")
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
