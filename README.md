# Leibinger Jet3 manual communication tool

Python 3.11 tool for direct server -> Ethernet/TCP -> LJ3 communication, with
an optional SQL Server audit/recovery integration. Standard printer
communication remains ASCII-only; a separate, explicitly experimental
ISO-8859-11 Thai hypothesis is available as action 11 and is not a supported
encoding guarantee. A distinct action 12 stages one experimental Mailmode
Field 1 record without writing `=ET`/Field 0; it is not part of the confirmed
Thai solution and must not be used for that workflow. The selected Field 0
`=ET` configuration with `ISOB_Thai`, 24x20 font, and ISO-8859-11 has completed
a physical print test for one combined Lot/color string; print quality and
complete character verification still need improvement. Core communication
uses the standard library; database support requires `pyodbc` and a Microsoft
SQL Server ODBC driver. Lot/product lookup is not implemented.

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
| 7 Automatic ExternText Transaction | Read `?RS`, `?EX`, `?JL`, baseline `?ET`; enforce readiness; send one `=ET`; verify exact same-session `?ET`; journal and report result |
| 8 Read Printer Status | Read-only `?RS`, `?EX`, and `?JL`; preserve undocumented fields as opaque data and report unobservable conditions as UNKNOWN |
| 9 Database Status | Inspect configured SQL Server version, permissions, and `inkjet` tables/views; never print credentials |
| 10 Recover Local Transaction Log | Idempotently persist journal entries to SQL; sends no printer commands |
| 11 Experimental Thai ISO-8859-11 =ET (UNVERIFIED) | Legacy Field 0 hypothesis only; this writes the global `=ET` value and can replace the Lot Number. Do not use for Mailmode Field 1. |
| 12 Experimental Thai Mailmode Field 1 (UNVERIFIED) | One hardcoded `สีเทานก` candidate; previews raw `=MR0<TAB>...<CR>` bytes, requires the job's EXTTXT parameter 3 = 1, exact Field 0 baseline, four safety attestations, and two empty-FIFO `?SM` samples. It submits one record, checks FIFO status and unchanged `?ET`, then intentionally leaves the FIFO untouched and reports `STAGED_UNVERIFIED`. Do not start printing; this application has no FIFO-clear action. |
| 0 Quit | Close any local socket and exit |

Every network operation is an explicit operator action. Events show UTC
timestamps, connection status, escaped bytes, hexadecimal TX/RX, response/send
timings, and errors. The automatic path persists structured evidence to a local
journal before attempting SQL delivery.
TX describes attempted bytes; a failed transmission may have partially reached
the printer. A successful write is labelled **SENT - UNVERIFIED** because ordinary
LJ3 commands have no guaranteed acknowledgement. Action 4 does not resend text.

Use **7** for one automatic transaction: enter printable ASCII and confirm the
physical safeguards once. It checks status/readiness and baseline before the
single write, then verifies an exact same-session readback. Legacy actions **3**
and **5** still provide manual single writes followed separately by **4**; they
do not include the full status/baseline transaction. Option **8** is read-only
status. Other ASCII examples include `RED`, `BLUE`, `COLOR A`, and `LOT260917`.

## Before sending

Follow [the commissioning guide](docs/COMMISSIONING.md). Communication-only
`=ET`/`?ET` tests do not require a Field 0 object or verified job offsets; they
do not test print-job integration or printed output. Stopping printing and
inhibiting triggers are **our commissioning safety policy for a physical
write**; the supplied manuals do not establish stopping as an ExternText
protocol requirement. Option 7 checks documented machine state and the live
PrintGo signal; it blocks unless state is 4 (Ready for Action), error is 0, and
PrintGo is low. This is a conservative application rule, not a vendor guarantee
about `=ET`. `?EX` cannot prove that a PLC/line has inhibited triggers. Production
stop, trigger inhibition, absence of an external writer, and `!EM` echo state
cannot all be machine-queried and remain operator attestations/UNKNOWN. The
per-printer lock serializes writes and transactions inside this application
process only; it cannot exclude other clients/controllers. Active-production
cutover remains unverified.
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

Free Text and all ordinary ASCII write/transaction paths reject non-ASCII
input before network activity. The original interface manual says Unicode-font
ExternText/Mailing data must be hexadecimal-coded, but does not state the
encoding name or a general `ISOB_Thai` mapping. For `สีเทานก`, ISO-8859-11,
TIS-620, and Windows-874 codecs produce the same seven bytes; that coincidence
does not identify the font's mapping. Action 12 remains an experimental raw-byte
Mailmode hypothesis for Field 1 and is not needed for the confirmed Field 0
workflow. Action 11 is limited to the earlier fixed Thai phrase; it does not
implement this combined Lot/color value. The physical test described below
demonstrates the selected configuration for one sample, not a general encoding
or production guarantee. Active-production update timing remains unverified.

## Physical communication validation (2026-11-26)

Using the updated application at `172.28.169.248:3000`, the operator confirmed
printing stopped, triggers inhibited, no competing ExternText writer, and echo
disabled. Read-only `?RS` returned nozzle 4 (closed), machine 4 (Ready for
Action), error 0, headcover 0 (closed), ActSpeed 230 m/min, plus one opaque
undocumented field `0`; response time was 31.000 ms. One `=ET` write of
`4691125P` was followed by `?ET` on the same TCP session. The exact readback
was `4691125P` (**VERIFIED**) in 3016.000 ms. The write-submit time was
0.000 ms; ordinary write acknowledgement is not specified. No retry occurred.

The communication tests above did not verify Field 0 integration or physical
printing at that time. A later, separately confirmed test below has now
demonstrated the combined value on Field 0 and printed it on paper. Lot/product
lookup and automatic Lot monitoring remain **NOT IMPLEMENTED**.

## Confirmed Thai Field 0 physical test (2026-11-26)

The operator confirmed the following test configuration on the JET3:

- Job `CB-LOT-TEST`; one External Text Field 0 using character set `ISOB_Thai`.
- Font `24x20`; placeholder length `30`.
- Protocol `=ET`; ISO-8859-11 payload; no Mailmode, `=MR`, or FIFO operation.
- Text: `4691125P สีเทานกพิราบ`.

The operator confirmed TCP communication, exact raw write/readback byte match,
correct mixed English/numeric/Thai display on the HMI, and physical Thai
printing on paper. The one write frame was sent exactly once:

- `=ET` TX: `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`
- `?ET` TX: `5E 30 3F 45 54 0D`
- Raw `?ET` RX: `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`

Result: **VERIFIED — exact payload match**; the HMI display and physical
printing were operator-confirmed. Print quality and complete physical
character verification still require improvement. This is a successful test of
the stated job/font/text combination, not a blanket guarantee for other Thai
text, jobs, offsets, or production timing. No printing was started during the
subsequent documentation/Git task. Full evidence is in
[docs/JET3_ONSITE_COMMISSIONING.md](docs/JET3_ONSITE_COMMISSIONING.md).

## SQL Server integration

The SQL implementation reads the existing `.env` names `SQL_DRIVER`,
`SQL_SERVER`, `SQL_PORT` (optional; default 1433), `SQL_DB`, `SQL_USER`,
`SQL_PASS`, and `SQL_TRUST_SERVER_CERTIFICATE`. It strictly uses the local
`SQL_SERVER`; it does not silently substitute a host. The current ignored
`.env` intentionally says `127.0.0.1` because the application and SQL Server
are on the same physical server (`10.28.255.19`). Option 9 and normal database
persistence were verified through localhost to database `CB`, with all
approved `inkjet` tables/views present. Do not copy credentials into project
files or share `.env` contents.

Install a Microsoft SQL Server ODBC driver and optional Python dependency from
[requirements-mssql.txt](requirements-mssql.txt). Inspect the commissioned
server with `python -m lj3.db --inspect --server 10.28.255.19`; apply
repeatable migrations with `python -m lj3.db --migrate --server 10.28.255.19`.
That explicit override applies only to the migration/inspection process; normal
application operations remain strictly configured from `.env`. Migration
scripts are in [sql/migrations/](sql/migrations/).

The authorized schema contains five tables (`PrinterMaster`, `PrinterStatus`,
`StatusLog`, `TransactionLog`, `ErrorLog`) and four views (`vw_PrinterStatus`,
`vw_TransactionHistory`, `vw_ErrorHistory`, `vw_DailySummary`) under `inkjet`.
Times are stored as Asia/Bangkok UTC+07:00 wall time in `datetime2(3)` (which
does not itself carry a timezone). Unsupported trigger-inhibition, production
stop, and echo facts remain nullable/UNKNOWN.

Each automatic transaction writes an append-only durable local record to
`logs/pending_transactions.jsonl`, including a write-intent record before the
single printer write. If SQL is unavailable, the result stays locally journaled.
Option 10 replays the journal idempotently; an interrupted write intent becomes
`WRITE_OUTCOME_UNKNOWN`. Recovery never sends printer commands or retries a
write. The journal path is ignored by Git. SQL exceptions are sanitized; no
credential or connection-string values are logged.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fake sockets and a TCP simulator bound only to `127.0.0.1` with an
ephemeral port. They do not read the real `.env` or use a physical printer.
Temporary test files are created and removed inside this workspace.

The live SQL integration test is opt-in. Set `INKJET_SQL_TEST_SERVER` to an
authorized host and run `python -m unittest tests.test_db -v`. It uses local
`.env` credentials, checks actual persistence, views, and idempotency, and
deletes only its own synthetic rows. The authorized server was verified as SQL
Server 2019 (`15.0.2000.5`); required permissions were present and all nine
requested `inkjet` objects were created. A later separately authorized Option 8
check sent only read-only `?RS`, `?EX`, and `?JL` and verified the sample in
`inkjet.PrinterStatus` and `inkjet.StatusLog`. No `=ET` write or Option 7 was
run. See [the onsite commissioning record](docs/JET3_ONSITE_COMMISSIONING.md)
for raw frames and decoded results.

The pre-existing `requirements.txt` is preserved. Core communication needs no
third-party packages; optional SQL support is declared in
[requirements-mssql.txt](requirements-mssql.txt). PDF analysis packages are not
runtime dependencies.

## Code and protocol documentation

- [Project context and manual references](docs/PROJECT_CONTEXT.md)
- [Protocol framing and parsing](lj3/protocol.py)
- [LJ3Client transport and verification](lj3/client.py)
- [Workspace-local configuration](lj3/config.py)
- [Terminal menu](lj3/__main__.py)
- [Status aggregation](lj3/status.py)
- [Transaction and per-printer lock](lj3/transaction.py)
- [SQL persistence and recovery](lj3/db.py)

The library does no network I/O at construction. `connect()` performs a TCP
handshake only. High-level operations open a session when needed and reuse it
for sequential menu actions; the session remains open until quit, target
reconfiguration, or a communication/protocol failure. Option 1 leaves the
connection open. No action silently reconnects or retries within a failed
operation. The allowlist supports `=ET` and read-only `?ET`, `?RS`, `?EX`, and
`?JL`; there is no arbitrary command console or job-load command. Unknown status
fields remain opaque. The automatic transaction checks documented machine
state/error/PrintGo and requires operator confirmation for production stop,
trigger inhibition, no external writer, and disabled echo. The application
cannot verify all those conditions; its process-local lock cannot exclude
external clients. Verification uses exact text and Python `repr` values so
whitespace differences remain visible.
