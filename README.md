# Leibinger Jet3 manual communication tool

Python 3.11 Phase 1 tool for direct server -> Ethernet/TCP -> LJ3 communication.
It provides an interactive terminal menu for configuration, TCP connection
testing, sending ExternText, readback, and comparison. The runtime has **no
third-party dependencies**. MES/SQL integration and automatic Lot monitoring
are not implemented.

## Run

From this workspace in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m lj3
```

Startup only loads configuration and displays the menu. It does not connect,
send commands, poll, retry, or change printer settings.

Choose **6** to set the printer IPv4 address, TCP port, and timeout for this
session. Alternatively, add the entries from [.env.example](.env.example) to
the existing project `.env`. Preserve its existing settings; do not overwrite
it. Default port is 3000; timeout is 10 seconds; no IP is assumed.
`.env` is ignored by Git and must not be committed.
The site reservation is configured in the local `.env`, so it is prefilled
when this workspace's program starts. It remains editable through action 6.
There is no site-specific IP in the client, protocol, or versioned defaults.

The `.env` reader accepts `KEY=value`, optional matching quotes, and whole-line
comments. It reads only `LJ3_IP`, `LJ3_PORT`, and `LJ3_TIMEOUT_SECONDS`, from this
workspace. There is no parent-directory search, interpolation, or shell
execution. Settings changed in the menu are not saved to disk.

| Action | Behavior |
| --- | --- |
| 1 Test TCP Connection | Open or reuse TCP; send no LJ3 command; report TCP CONNECTION OK or TCP CONNECTION FAILED |
| 2 Read Current ExternText | Send `?ET` and display the returned ASCII value; no modification |
| 3 Send Test Text (TEST123) | Preview fixed `TEST123`, require `SEND` after confirming production stopped, triggers inhibited, and no competing writer, plus `ECHO OFF`; transmit once using `=ET` |
| 4 Verify Last Sent Text | Send `?ET` on the same live session as the last write, compare exactly, and report VERIFIED, MISMATCH, or COMMUNICATION ERROR |
| 5 Send Free Text | Enter printable ASCII, preview, require `SEND` after confirming production stopped, triggers inhibited, and no competing writer, plus `ECHO OFF`; transmit once using `=ET` |
| 6 Configure Target | Change this session's IP, port, and timeout; clear comparison history |
| 7 Read Printer Status | Send read-only `?RS`; display the five documented `=RS` fields and preserve extra fields as opaque bytes |
| 0 Quit | Close any local socket and exit |

Every network operation is an explicit operator action. Events show UTC
timestamps, connection status, escaped bytes, hexadecimal TX/RX, response/send
timings, and errors.
Output is displayed in the terminal, not automatically persisted to a log file.
TX describes attempted bytes; a failed transmission may have partially reached
the printer. A successful write is labelled **SENT - UNVERIFIED** because ordinary
LJ3 commands have no guaranteed acknowledgement. Action 4 does not resend text.

First site workflow: **1 -> 2 -> 3 -> 4**; optionally use **7** for read-only
printer state before proceeding. After those pass, choose **5** and
enter `CHARCOAL GREY`, then **4** to verify it. Other ASCII examples include
`RED`, `BLUE`, `COLOR A`, and `LOT260917`. Each write needs its own `SEND`.

## Before sending

Follow [the commissioning guide](docs/COMMISSIONING.md). Communication-only
`=ET`/`?ET` tests do not require a Field 0 object or verified job offsets; they
do not test print-job integration or printed output. Stopping printing and
inhibiting triggers are **our commissioning safety policy for a physical
write**; the supplied manuals do not establish stopping as an ExternText
protocol requirement. The write confirmation also asks the operator to confirm
there is no competing ExternText writer. Whether and when updates affect active
printing remains unverified before future automatic Lot-driven updates.
The tool rejects empty text, controls, non-ASCII, and literal backslashes.
Carets use the manual's `\^` escape. Maximum text length is 256 characters,
with an additional conservative 256-byte cap after escaping. Spaces are
preserved exactly; no padding or truncation occurs.

For a later print-integration test, confirm the job's offsets and placeholder
lengths at the printer; this is not a prerequisite for communication testing.
A readback match is labelled **VERIFIED** only after a successful `?ET`
response and exact comparison. Option 4 is bound to the same still-open TCP
session as the most recent write; it refuses to reconnect and label a different
session as verification. It does not prove the job used it or
that a product was printed correctly. No start/stop, nozzle, job upload, or
arbitrary raw command is exposed by the tool.

Free Text detects non-ASCII input (including Thai `สีเทา`, `สีแดง`, `น้ำตาล`)
and displays **Unicode / Experimental - SEND BLOCKED** before confirmation or
network activity. Interface manual p.27 requires hexadecimal text according
to the Unicode font/job, not UTF-8. Its length limits and readback details are
insufficient to guarantee correct Unicode behavior, so no Unicode encoder or
send is enabled. Prove ASCII first, then investigate the font/job and encoding
with the vendor and a separate controlled physical experiment. Active-production
update timing also remains unverified.

## Physical communication validation (2026-11-26)

Using the updated application at `172.28.169.248:3000`, the operator confirmed
printing stopped, triggers inhibited, no competing ExternText writer, and echo
disabled. Read-only `?RS` returned nozzle 4 (closed), machine 4 (Ready for
Action), error 0, headcover 0 (closed), ActSpeed 230 m/min, plus one opaque
undocumented field `0`; response time was 31.000 ms. One `=ET` write of
`4691125P` was followed by `?ET` on the same TCP session. The exact readback
was `4691125P` (**VERIFIED**) in 3016.000 ms. The write-submit time was
0.000 ms; ordinary write acknowledgement is not specified. No retry occurred.

Communication testing does not verify Field 0 integration or physical printing;
both remain **NOT TESTED**. MES/SQL integration and automatic Lot monitoring
are **NOT IMPLEMENTED**. The current print job was left unchanged.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fake sockets and a TCP simulator bound only to `127.0.0.1` with an
ephemeral port. They do not read the real `.env` or use a physical printer.
Temporary test files are created and removed inside this workspace.

The pre-existing `requirements.txt` is preserved and is not needed by this
tool. See [requirements-phase1.txt](requirements-phase1.txt). PDF analysis
packages installed in the existing virtual environment are not runtime
dependencies.

## Code and protocol documentation

- [Project context and manual references](docs/PROJECT_CONTEXT.md)
- [Protocol framing and parsing](lj3/protocol.py)
- [LJ3Client transport and verification](lj3/client.py)
- [Workspace-local configuration](lj3/config.py)
- [Terminal menu](lj3/__main__.py)

The library does no network I/O at construction. `connect()` performs a TCP
handshake only. High-level operations open a session when needed and reuse it
for sequential menu actions; the session remains open until quit, target
reconfiguration, or a communication/protocol failure. Option 1 leaves the
connection open. No action silently reconnects or retries within a failed
operation. `send_command()` permits only `=ET`, `?ET`, and `?RS`; status queries
decode the five documented fields and retain extra fields without interpreting
them. Writes require operator confirmation that printing is stopped, triggers
are inhibited, no other ExternText writer is active, and optional `!EM` command
echo is disabled. The `!EM` confirmation prevents an echoed write frame from
being mistaken for same-session readback; the app does not change or detect that
mode. Field 0 verification is not required for communication testing. The
stopped-printing assertion is commissioning policy, not a firmware constraint.
Writes remain **SENT - UNVERIFIED** until action 4 returns an exact readback.
Verification prints Python `repr` values so whitespace differences are visible.
