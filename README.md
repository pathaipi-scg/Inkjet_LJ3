# Leibinger Jet3 manual communication tool

Python 3.11 Phase 1 tool for direct server -> Ethernet/TCP -> LJ3 communication.
It provides an interactive terminal menu for configuration, TCP connection
testing, sending ExternText, readback, and comparison. The runtime has **no
third-party dependencies**. SQL and automatic Lot monitoring are not implemented.

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
it. Default port is 3000; timeout is 3 seconds; no IP is assumed.
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
| 1 Test TCP Connection | Open and close TCP; send no LJ3 command; report TCP CONNECTION OK or TCP CONNECTION FAILED |
| 2 Read Current ExternText | Send `?ET` and display the returned ASCII value; no modification |
| 3 Send Test Text (TEST123) | Preview fixed `TEST123`, require `SEND`, transmit once using `=ET` |
| 4 Verify Last Sent Text | Send `?ET`, compare exactly with the last successfully submitted value; report VERIFIED, MISMATCH, or COMMUNICATION ERROR |
| 5 Send Free Text | Enter printable ASCII, preview, require `SEND`, transmit once using `=ET` |
| 6 Configure Target | Change this session's IP, port, and timeout; clear comparison history |
| 0 Quit | Close any local socket and exit |

Every network operation is an explicit operator action. Events show UTC
timestamps, connection status, escaped bytes, hexadecimal TX/RX, and errors.
Output is displayed in the terminal, not automatically persisted to a log file.
TX describes attempted bytes; a failed transmission may have partially reached
the printer. A successful write is labelled **SENT - UNVERIFIED** because ordinary
LJ3 commands have no guaranteed acknowledgement. Action 4 does not resend text.

First site workflow: **1 -> 2 -> 3 -> 4**. After those pass, choose **5** and
enter `CHARCOAL GREY`, then **4** to verify it. Other ASCII examples include
`RED`, `BLUE`, `COLOR A`, and `LOT260917`. Each write needs its own `SEND`.

## Before sending

Follow [the commissioning guide](docs/COMMISSIONING.md). Phase 1 sends printable
ASCII to a prepared, non-Unicode **Field Number 0** test job. Stopping printing
is **our Phase 1 commissioning safety policy for the first physical site test**.
The supplied manuals do not establish it as an ExternText protocol requirement.
Whether and when updates affect active printing remains to be verified on the
real Jet3 before future automatic Lot-driven updates are designed.
The tool rejects empty text, controls, non-ASCII, and literal backslashes.
Carets use the manual's `\^` escape. Maximum text length is 256 characters,
with an additional conservative 256-byte cap after escaping. Spaces are
preserved exactly; no padding or truncation occurs.

Confirm the job's offsets and placeholder lengths at the printer. A readback
match is labelled **VERIFIED** only after a successful `?ET`
response and exact comparison. It does not prove the job used it or
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
handshake only. High-level set/get/verify methods perform their corresponding
explicit action on a fresh connection, which closes afterward. Low-level
`send_command()` requires an explicit connection and permits only `=ET` and
`?ET`. Writes require `stopped_ascii_job_confirmed=True`; this is an operator
assertion, not an automatic machine-state check. No action retries itself.
The stopped-printing assertion is commissioning policy, not a firmware constraint.
