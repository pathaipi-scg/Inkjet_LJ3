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
    print("Leibinger Jet3 - manual Phase 1 tool")
    print("ASCII / Field 0 only. Phase 1 commissioning policy: printing stopped, test job prepared.")
    print("Stopped printing is our test policy; the manuals do not establish it as an ET requirement.")
    print("No startup connection or commands. All actions below are manual.")
    print("Readback match does not prove physical printing. No Unicode mode.")
    try:
        while True:
            print(f"\nTarget {settings.ip or '(not configured)'}:{settings.port} | "
                  f"timeout {settings.timeout:g}s | {'connected' if client.connected else 'disconnected'}")
            print("1 Configure target (session only)\n2 Test TCP connection (no LJ3 command)\n"
                  "3 Send ExternText\n4 Read ExternText\n5 Verify last submitted value (read only)\n0 Quit")
            action = input("Action: ").strip()
            try:
                if action == "0":
                    return 0
                if action == "1":
                    candidate = configure(settings)
                    client.disconnect()
                    settings = candidate
                    client = LJ3Client(settings, print_event)
                    last_sent = None
                    print("Session settings changed; .env was not modified.")
                elif action == "2":
                    try:
                        client.connect()
                        print("TCP reachable; this does not prove printer identity or command support.")
                    finally:
                        client.disconnect()
                elif action == "3":
                    text = input("ExternText (spaces are preserved): ")
                    wire = build_command("=ET", text)
                    settings.validate()
                    print(f"Target: {settings.ip}:{settings.port}\nText: {text!r}\n"
                          f"Preview: {wire!r}\nHex: {wire.hex(' ').upper()}")
                    print("Phase 1 commissioning policy - confirm at the printer: production is stopped; a non-Unicode test job uses "
                          "Field 0; lengths/offsets match this value.")
                    if input("Type SEND to confirm and transmit once: ") != "SEND":
                        print("Cancelled; no connection or command sent.")
                        continue
                    last_sent = None  # An uncertain write invalidates previous comparison state.
                    client.set_external_text(text, stopped_ascii_job_confirmed=True)
                    last_sent = text
                elif action == "4":
                    print(f"Current ExternText (ASCII interpretation): {client.get_external_text()!r}")
                elif action == "5":
                    if last_sent is None:
                        print("No completed send for this target in this session. Use Read after an uncertain write.")
                        continue
                    result = client.verify_external_text(last_sent)
                    print(f"{'VERIFIED (exact readback)' if result.matched else 'MISMATCH'}: sent={result.expected!r}, returned={result.actual!r}")
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
