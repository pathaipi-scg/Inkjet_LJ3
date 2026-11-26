# Leibinger Jet3 project context

## Purpose and scope

The exclusive project root is the currently opened workspace, `D:\AI\Inkjet_LJ3`.
The intended business flow is operator Lot entry -> product/color lookup -> this
Python 3.11 application -> Ethernet -> Leibinger Jet3 print-job text. The
original Phase 1 milestone was a manual communication/test tool. The current
application additionally provides an automatic one-shot ExternText transaction,
read-only status aggregation, SQL Server audit persistence, and local recovery.
Lot/product lookup, Kepware, OPC UA, Modbus, and third-party gateways are not
implemented or required by the documented printer interface.

The application updates ExternText in an existing printer job; it does not
create/upload a new job for each Lot. Any future server-side Lot/product/color
business logic remains separate; the Jet3 receives text and has no SQL
connection. A conceptual job name such as TILE_COLOR does not establish the
actual site job.

**Latest physical validation (2026-11-26):** the operator confirmed a combined
Lot/color value printed on paper from `CB-LOT-TEST` using one External Text
Field 0, `ISOB_Thai`, 24x20, placeholder length 30, and a single ISO-8859-11
`=ET` write. Raw `?ET` bytes matched exactly. Mailmode and FIFO were not used.
Print quality and complete physical character verification remain in progress;
this evidence applies to the tested value/configuration only. See
`JET3_ONSITE_COMMISSIONING.md` for TX/RX evidence.

For developer and AI-agent implementation guidance, see the standalone
[JET3 Communication Reference](JET3_COMMUNICATION_REFERENCE.md).

## Site settings and evidence categories

The first physical test uses Server / Machine NIC -> factory Machine network
-> Jet3 TCP port 3000. The reserved site IP is stored only in ignored `.env`,
not in source, `.env.example`, or versioned documentation. It is loaded as the
local UI default and remains editable. The reservation is not proof that the
address is unused: verify allocation on site before assigning it to the Jet3.
The client relies on the operating system's route through the Machine NIC;
it does not bind or reconfigure a network adapter.

| Category | Meaning for Phase 1 |
| --- | --- |
| Documented protocol | ASCII address 0, CR framing, `=ET`/`?ET`, Field 0 semantics, powered-on state, and font-dependent encoding; see manual references below. |
| Our commissioning safety policy | For a physical communication write, stop printing, inhibit triggers, ensure there is no competing ExternText writer, and explicitly confirm SEND. This is not a documented LJ3 stop-printing requirement. Field 0 integration is a separate print-job test. |
| Unknown physical behavior | Active-print text cutover, affected product, buffering, firmware readback behavior, and persistence require device/vendor verification. One operator-confirmed Thai Field 0 print test passed, but print quality and complete physical character verification remain in progress. |

The manuals do not state that `=ET` is permitted only when printing is stopped.
The Phase 1 guard must not be treated as a permanent production requirement.
Future automatic Lot changes still require a verified production transition
procedure before the commissioning guard is revised.

The local `.env` contains settings for multiple integrations. LJ3 configuration
uses only `LJ3_*`; SQL integration uses the existing `SQL_*` keys and never
prints credentials. Preserve unrelated settings. Core printer communication
uses the standard library; optional SQL support is declared separately in
`requirements-mssql.txt`. PDF extraction utilities are development-only.

## Source manuals

All references below use PDF page numbers (also printed page numbers).

- `manual/Manual_LJ3_Interfaceprotocol.pdf`: version 1.7.7, 5 May 2014,
  27 pages. General framing p.4; dangerous script replacement p.5; action
  commands and optional reply modes pp.6-7; inquiries p.8; parameter convention
  p.9; ExternText and error list p.11; fixed block mode p.13; machine state and
  errors pp.18-19; optional CRC p.25; mailing/variable length p.26;
  Unicode and history p.27.
- `manual/Manual_LJ3_Scriptlanguage.pdf`: dated 25 April 2014, 32 pages.
  Script syntax p.3; EXTTXT pp.21-22; font selection pp.24-25. Reviewed the
  remaining sections for interactions; script/job upload is outside Phase 1.
- `manual/ManualHyperterminalLJ3Engl.pdf`: 2 June 2009, 9 pages.
  Ethernet settings p.1; HyperTerminal Ethernet connection p.4; communication
  examples p.8. Its mailing example (Fields 1 and 2) is not an ExternText example.
  The p.4 screenshot was visually checked: it selects TCP/IP (Winsock) with
  port 3000. Pages 4 and 8 are rendered alongside the text extracts.

Searchable page-labelled extracts are under `docs/manual-extracted/`.
The PDFs are authoritative if extraction formatting differs.

## Confirmed communication

### Ethernet and framing

On the Jet3, configure Settings / Basic settings / IP_Adress and a compatible
subnet mask. Under Extra / Interface settings / Connection Typ select Ethernet
and configure port **3000** (HyperTerminal p.1). The example IP is not a site
default and is not prefilled by the application. The application is the TCP
client connecting to the printer; port is configurable to match its settings.
TCP connection success alone does not identify the device or prove LJ3 readiness.

The interface is dual-master: either side can transmit independently. Frames are:

```text
^ + ASCII destination address + command group/command + parameters + CR
```

The Jet3 address is the single ASCII character `0` (hex `30`), not binary zero.
`^` is hex `5E`; final CR is hex `0D`. An optional LF may follow CR. Transmit CR
only. Data are ASCII. A literal caret in data is escaped as `\^`.
Parameters are TAB-separated unless specified otherwise. The first parameter
follows the command directly (see protocol examples such as `=JL` and `=MR`).
Do not prepend a space or TAB to the ExternText value; spaces are text.

Derived Phase 1 examples (Python byte notation, not literal backslash-r on wire):

```python
b"^0=ETBLUE\r"       # 5E 30 3D 45 54 42 4C 55 45 0D
b"^0?ET\r"          # 5E 30 3F 45 54 0D
b"^0=ETBLUE\r"      # expected parameter response to ?ET
```

The response form follows the general inquiry rule on p.8: `?XX` returns `=XX`.
`?ET` is explicitly listed there and introduced in protocol history v1.7.3;
the manual gives neither a dedicated response example nor a minimum firmware
version for it. Validate support and raw response on the physical printer.

### ExternText and job setup

`=ET` has one string parameter, up to **256 characters**, ending at CR.
The documented reaction time is **20-40 ms** (interface p.11), not a guaranteed
network timeout or print synchronization deadline.

The loaded job must contain an object using `{e}` and EXTTXT with **Field Number
0**. Fields 1 and above select mailing records, which use a different mechanism.
EXTTXT parameters are length 1-100, placeholder text, field number, character
offset 0-255, and double-print check 0/1 (script pp.21-22).
An object's placeholders and offset determine its slice of ExternText. The
largest offset-plus-placeholder count across objects determines how many
characters the job requires; insertion occurs after all required characters
have arrived. The 256-character transfer limit is not the 100-character
per-object length. Multiple objects can consume portions of the same variable.

Interface p.26 also describes variable text length and placeholders restored
on job reload or a zero string, including ExternText. Its interaction with the
required-character rule is not fully explained. Phase 1 rejects empty writes
and does not pad/truncate. Job length/offset checks are for Field 0 print
integration and are not required for `=ET`/`?ET` communication testing.

If **Check double prints** is enabled, absence of newly received external text
after PrintGo can stop printing and generate an error (script p.22). A
once-per-Lot text update must not be assumed compatible with that setting.

### Encoding and Unicode

Interface p.4 says ASCII. It does not specify an extended-ASCII code page.
Unicode fonts in a job require **ASCII hexadecimal text**, e.g. `Hello World`
becomes `00480065006C006C006F00200057006F0072006C0064` (interface p.27).
This is not a UTF-8 socket payload. Unicode font names begin with `~` (script
p.25). Supplementary characters, surrogates, Unicode readback representation,
and how the 256-character limit applies to hex expansion are not specified.

The normal text path supports printable ASCII only, with documented caret
escaping. It rejects CR, LF, TAB, controls, DEL, non-ASCII, and literal
backslashes (literal backslash escaping for ET is not specified). It additionally
caps the encoded payload at 256 bytes, a conservative application restriction
for escaped carets. A separate experimental ISO-8859-11 encoder was used for
the physical test described at the end of this document; that one confirmed
`ISOB_Thai` Field 0 configuration does not establish a general Unicode mode or
encoding guarantee. The application does not change the printer font.

### Responses, errors, and connection behavior

There is **no ordinary per-packet acknowledgement** (interface p.4). Successful
`sendall` means transport submission, not printer acceptance. `!OK` belongs to
optional CRC transactions; it is not a generic ET acknowledgement. Optional
echo (`!EM`, p.7) echoes actionable `!`/`=` commands; it is not independent
readback. Neither echo nor CRC is enabled by this application. CRC documentation
also contains an `=NR` / `=NC` inconsistency on p.25; CRC is out of scope.

The receive parser supports ordinary frames and the optional five-decimal-digit
length header after the address (`!LN`, p.7), validating its length including
the final CR. It handles TCP fragmentation, coalescing, and optional LF.
Fixed-block padding (`=FL`, p.13) is not supported: use normal unpadded mode.
Malformed data fail closed and raw bytes remain in the terminal log.

`=FC` reports CRC failure (p.13). `=RS` carries machine state and a numeric
error (pp.18-19); `=EL` contains error-list entries (p.11). Actual error texts
are in language-specific files on the printer, not these PDFs. No generic ET
NAK or invalid-command error format is specified. Report observed frames and
timeouts without inventing a device error code or claiming rejection.

Only power-on/reset/file transfer work in standby (p.4); ET needs the printer
turned on. The manuals do **not** establish that ET requires print stop, nor
guarantee which product receives new text during active printing. For
communication writes, the application requires operator confirmation that
production is stopped, triggers are inhibited, and no competing ExternText
writer is active. This is application policy, not a documented firmware
requirement or machine-state interlock. A Field 0 object and verified offsets
are needed only for a separate print-integration test.

No ET TCP timeout/reconnect/retry contract is specified. The current client
uses a configurable 10-second default deadline, bounded receive frames, and one
reusable TCP session for serialized commands. It does not reconnect or replay
within a failed operation. A write remains `SENT - UNVERIFIED` until a later
`?ET` exact comparison succeeds on the same still-open socket; if that session
is lost, verification fails without reconnecting. Because optional `!EM` can
echo actionable `=` commands, the CLI requires operator confirmation that
echo is disabled before writing for same-session verification. The app does
not inspect or change `!EM`. There are no transaction IDs or protection from
concurrent writers; use one controller during testing.

Read-only `?RS` status support decodes the manual's five fields (nozzle state,
machine state, error, headcover, ActSpeed). Any additional response fields are
preserved as opaque byte values and are not assigned undocumented meanings.
TX/RX chunks retain escaped-byte and hexadecimal logs; a timing event records
elapsed milliseconds through write submission or complete response receipt.

## Phase 1 architecture and implementation plan

```text
lj3/
  __main__.py    explicit-action terminal menu
  config.py      workspace-local .env settings and validation
  protocol.py    pure byte framing, incremental parsing, text validation
  client.py      LJ3Client, TCP deadlines, error handling, event logging
tests/          unittest protocol, fake-socket, and loopback tests
docs/           context, commissioning guide, manual extracts
.env.example    placeholders only; existing .env is preserved and ignored
README.md       launch and offline test instructions
```

1. Document evidence and restrictions before implementation (this file).
2. Implement a narrow protocol surface accepting ET write/read and RS status inquiries.
3. Implement `connect`, `disconnect`, `send_command`, `set_external_text`,
   `get_external_text`, and `verify_external_text`; no startup I/O.
4. Provide the commissioning menu in order: 1 TCP-only test, 2 read current
  ExternText, 3 send fixed TEST123, 4 verify last sent text, 5 ASCII Free Text,
  6 configure session IP/port/timeout, 7 read printer status, and 0 quit.
   Show timestamped TX/RX in escaped bytes and hex, connection state, and
   errors. A comparison match is not proof of physical printing.
5. Test offline with standard-library unittest, injected sockets, and a local
   TCP simulator; never connect to a configured printer while developing.
6. Provide a stopped-production commissioning procedure. Hardware validation
   remains outstanding until an operator runs it.

## Unresolved questions and acceptance work

- Printer address/port and `?ET` readback have been exercised; the responding
  state and exact `TEST123` match are recorded in the onsite guide. Printer
  firmware, installed job/font, and the pre-existing `!EM`/`!LN`/fixed-block
  mode configuration remain unknown.
- Validate ET response shapes for empty text, trailing spaces, and caret escapes
  on hardware; the successful readback covered `TEST123` only.
- Resolve variable-length versus required-character behavior, empty text,
  trailing spaces, job reload and power-cycle persistence.
- Resolve Unicode length, readback, supported glyphs, and supplementary planes
  before enabling a Unicode mode.
- Confirm active-print update behavior, buffering, and exact product/Lot
  boundary with the vendor and controlled physical tests. No automatic live
  production changes are authorized by this implementation.
- The 10-second client default is informed by the measured 3061.884 ms `?ET`
  response. Determine connection limits and rapid reconnect handling before
  production automation.
- Improve print quality and complete physical character verification for the
  confirmed Thai test. ET readback alone cannot prove that the correct object
  or product was printed; the paper test is separately operator-confirmed.

## Future Phase 2 (not implemented)

After Phase 1 hardware acceptance: define SQL schema and Lot-to-product/color
mapping, operator workflow, missing/ambiguous Lot behavior, validation and
authorization, audit records, idempotency, delivery/verification states,
recovery after outages, and a production-boundary procedure. Reuse LJ3Client
behind separate business logic. Never replay a stale Lot automatically after
reconnection. No SQL dependency or automatic Lot monitor is part of Phase 1.

## Implementation and offline validation

Phase 1 is implemented with the structure above and no runtime dependencies.
The terminal menu keeps configuration changes in memory; `.env.example`
documents optional persistent settings. The local `.env` now contains the
user-supplied site IP and port; its unrelated entries are preserved.
See `README.md` and `docs/COMMISSIONING.md` for operation and site acceptance.

On 16 September 2026, Python 3.11.1 ran 49 passing unittest tests covering
framing, escaping, limits, injection rejection, incremental parsing, CR/LF,
length-mode responses, deadlines, disconnects, device errors, no retries,
separate readback streams, exact comparison, configuration, startup/cancellation
silence, and a real TCP loopback simulator. These prove the implemented
contract against the supplied manuals and simulated responses; they do not
substitute for the pending physical Jet3 acceptance.

The final pre-commit review also loaded the actual local site settings and
started/exited the real terminal menu with socket creation prohibited. No
socket was created. Explicit sends remain UNVERIFIED; only successful `?ET`
readback with exact comparison produces VERIFIED (readback only). Regression
tests cover mismatches and readback timeouts without a VERIFIED result.

Git review confirmed `.env` and `.venv/` are ignored, untracked, and absent
from the index and current HEAD. No reserved site IP, existing local password/
secret values, or private-key markers were found in HEAD, index, or nonignored
project files. Public manual example IPs and loopback test addresses are not
site configuration. No commit or staging changes were made. Three supplied
manuals and the original requirements file were already staged; Phase 1
implementation files remain untracked pending a commit. Git 2.36.1 required a
temporary workspace-local global-config override for its repository ownership
check; the override was removed and no user/global Git settings were changed.

## Sequential commissioning menu update (17 September 2026; historical behavior)

The first site workflow is **1 -> 2 -> 3 -> 4**: TCP handshake only, `?ET`
read, confirmed `=ETTEST123`, then a separate `?ET` comparison. Action **5**
accepts ASCII Free Text such as `CHARCOAL GREY`; action **4** then compares
against that latest submitted value. Action **6** changes only session settings,
which initially come from local `.env`; no target IP is embedded in client or
protocol code. Startup performs no networking.

At that date, the CLI reported TCP CONNECTION OK/FAILED, SENT - UNVERIFIED for
socket send success, and VERIFIED/MISMATCH/COMMUNICATION ERROR for readback.
Its then-current write prompt required a non-Unicode Field 0 job confirmation;
this was application policy and was later removed for communication-only
testing. Later implementation changes added persistent sessions, action 7
status, and same-session verification. The current write confirmation covers
stopped production, inhibited triggers, no competing ExternText writer, and
disabled `!EM` echo; Field 0 is not a communication prerequisite.
A failed write invalidates previous comparison state; cancellation or rejected
input preserves it. Changing the target clears it.

Free Text identifies non-ASCII input as Unicode / Experimental and blocks it
before confirmation or connection. Reinspection of interface p.27 and script
p.25 confirms font/job-dependent hexadecimal transmission, not UTF-8, but does
not resolve Unicode length limits or readback representation. No general
Unicode encoder or send path is enabled. Thai printing was still a separate
controlled physical investigation at that point in the historical record; the
specific later Field 0 test is documented below. No SQL, automatic Lot monitor,
Kepware, OPC UA, Modbus, or automatic print start/stop commands were added.

Validation: the full offline suite (`python -m unittest discover -s tests -v`)
passed all 61 tests on 17 September 2026. Coverage includes the full CLI site
workflow with exact wire bytes through injected sockets, TCP-only results,
fixed and free-text confirmation, Thai/non-ASCII blocking, comparison results,
history invalidation, and the existing loopback transport tests. The real Jet3
was not contacted; local `.env` defaults were checked without network activity.

## Communication implementation follow-up (26 November 2026)

The operator-reported physical read-only diagnostic received `?RS` state
values for nozzle 4 (closed), machine 4 (Ready for Action), error 0 (none),
headcover 0 (closed), and ActSpeed 230 m/min. The response had one additional
numeric field; its meaning is not documented and is intentionally not inferred.
On the same TCP connection, `?ET` returned `TEST123` with an exact match in
3061.884 ms. That subsequent readback verifies the one earlier write; no write
was repeated, and no physical print was performed in that diagnostic.

Based on that evidence, the application now defaults to a 10-second timeout,
reuses a TCP session for sequential inquiries, offers a read-only `?RS` menu
action, and binds `?ET` verification to the same still-open socket as the last
write. Status decoding supports the five manual fields and preserves extra
fields opaquely. TX/RX raw bytes/hex and elapsed timings are retained. The CLI
requires operator confirmation that optional `!EM` echo is disabled before a
write that will be verified on the same connection; it does not inspect or
change that printer mode. There are no automatic write retries. The physical
job-rendering and print-output tests remain unperformed.

Offline validation on 26 November 2026 passed all 69 unittest tests, including
protocol/status parsing, fake-socket client and CLI tests, and localhost-only
TCP session tests. No physical-printer command was sent during this code update.

## Lot Number physical communication validation (26 November 2026)

Using the updated application at `172.28.169.248:3000` with the 10-second
timeout, the operator confirmed printing stopped, print triggers inhibited, no
competing ExternText writer, and `!EM` echo disabled. The current print job was
not modified. The read-only status request `?RS` TX was `b'^0?RS\r'` (hex
`5E 30 3F 52 53 0D`); RX was `b'^0=RS4\t4\t0\t0\t230\t0\r'` (hex
`5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`), with a
31.000 ms response. Documented status: nozzle closed, machine Ready for Action,
no error, headcover closed, ActSpeed 230 m/min. The extra trailing field `0`
is undocumented and remains opaque.

The application sent one `=ET` frame, `b'^0=ET4691125P\r'` (hex
`5E 30 3D 45 54 34 36 39 31 31 32 35 50 0D`); write-submit time was
0.000 ms and no ordinary write acknowledgement is specified. It then sent
`?ET` on the same TCP session: TX `b'^0?ET\r'` (hex `5E 30 3F 45 54 0D`),
RX `b'^0=ET4691125P\r'` (hex `5E 30 3D 45 54 34 36 39 31 31 32 35 50 0D`).
Response time was 3016.000 ms; expected and returned values matched exactly:
**VERIFIED**. No retry, job change, setting change, restart, or print start
occurred.

At this communication milestone, tests were complete for the ASCII values
`TEST123` and `4691125P`, while Field 0/job integration and physical printing
remained **NOT TESTED**; the later Thai test below supersedes that status for
its specific sample. MES/product lookup and automatic Lot monitoring remain
**NOT IMPLEMENTED**.

## Automatic transaction and SQL Server implementation (26 November 2026)

Menu option 7 now performs an automatic one-shot transaction: validate the text;
read-only `?RS`, `?EX`, and `?JL` checks; baseline `?ET`; durable write intent;
one `=ET`; same-session exact `?ET` verification; and structured result/error
logging. It requires Ready for Action (machine state 4), error 0, and PrintGo
low. Unknown/invalid status is never treated as READY. Stopped production,
trigger inhibition, absence of an external writer, and `!EM` echo state cannot
all be queried and remain operator attestation/UNKNOWN. The process-wide
per-printer lock only serializes this application's writes/transactions; it
cannot exclude external clients. Options 8, 9, and 10 provide read-only status,
SQL inspection, and idempotent local-journal recovery respectively.

The local append-only journal is `logs/pending_transactions.jsonl`. It is
fsynced before a write; a failed write-intent journal operation blocks the
printer write. Recovery persists audit data only. An interrupted write intent
is represented as `WRITE_OUTCOME_UNKNOWN`; it never causes a printer retry.

The approved SQL Server `10.28.255.19`, database `CB`, reported version
`15.0.2000.5` (SQL Server 2019). Read-only checks confirmed sysadmin,
`CREATE TABLE`, `CREATE VIEW`, and `ALTER ANY SCHEMA` permissions. The
`inkjet` schema was initially absent. Migrations created the five approved
tables (`PrinterMaster`, `PrinterStatus`, `StatusLog`, `TransactionLog`,
`ErrorLog`) and four views (`vw_PrinterStatus`, `vw_TransactionHistory`,
`vw_ErrorHistory`, `vw_DailySummary`). Live integration testing exercised
parameterized inserts, view reads, idempotent journal recovery, and cleanup of
its own synthetic rows. No unrelated objects were modified or deleted.

The existing local `.env` has `SQL_SERVER=127.0.0.1`; this is intentional
because the application and SQL Server run on the same physical server
`10.28.255.19`. Credentials were not printed or changed. Normal menu SQL
inspection and persistence were later verified through localhost. A separately
authorized read-only Option 8 status check was performed on the physical printer
and its row/events were verified in SQL; no `=ET` write or Option 7 was run.
Full implementation and the result evidence are in
[DB_INTEGRATION.md](DB_INTEGRATION.md) and
[JET3_ONSITE_COMMISSIONING.md](JET3_ONSITE_COMMISSIONING.md). At that point in
the history, job integration and physical printing remained untested. The
later Thai Field 0 physical test below supersedes that status for its specific
job/font/text combination; any new production step still requires separate
approval.

## Combined Lot Number and Thai color Field 0 physical test (26 November 2026)

The operator confirmed the JET3 job configuration: `CB-LOT-TEST`, one External
Text Field 0 with character set `ISOB_Thai`, font `24x20`, and placeholder
length `30`. The selected protocol was `=ET` with ISO-8859-11 encoding. The
test value was `4691125P สีเทานกพิราบ`. No Mailmode, `=MR`, or FIFO command was
used.

The write was sent exactly once after the existing safety preflight. The
operator confirmed successful TCP communication, exact raw write/readback
payload match, correct mixed English/numeric/Thai display on the HMI, and
physical Thai printing on paper. Exact frames:

- `=ET` TX: `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`
- `?ET` TX: `5E 30 3F 45 54 0D`
- Raw `?ET` RX: `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`

**Result:** `VERIFIED` by exact raw payload match; HMI rendering and printing
on paper were operator-confirmed. Print quality and complete physical
character verification still require improvement. The evidence supports this
specific Field 0 job/font/value combination only; it does not validate
arbitrary Thai strings, active-production cutover, or general Unicode support.
No printer command, application change, or print start occurred during the
subsequent documentation and Git work.
