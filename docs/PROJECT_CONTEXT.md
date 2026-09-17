# Leibinger Jet3 project context

## Purpose and scope

The exclusive project root is the currently opened workspace, `D:\AI\Inkjet_LJ3`.
The intended business flow is operator Lot entry -> product/color lookup -> this
Python 3.11 application -> Ethernet -> Leibinger Jet3 print-job text.
Phase 1 is a manual communication/test tool only. No SQL, Lot monitoring,
Kepware, OPC UA, Modbus, or third-party gateway is needed for the documented
interface. No printer was contacted during development.

The future application updates ExternText in an existing printer job; it does
not create/upload a new job for each Lot. The server owns Lot/product/color
business logic; the Jet3 receives only text and has no SQL connection. A
conceptual job name such as TILE_COLOR does not establish the actual site job.

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
| Our commissioning safety policy | Stop printing before every write for the first physical test; explicitly confirm SEND; use a prepared non-Unicode Field 0 test job. This is not a documented LJ3 stop-printing requirement. |
| Unknown physical behavior | Active-print text cutover, affected product, buffering, firmware readback behavior, and persistence require device/vendor verification. |

The manuals do not state that `=ET` is permitted only when printing is stopped.
The Phase 1 guard must not be treated as a permanent production requirement.
Future automatic Lot changes still require a verified production transition
procedure before the commissioning guard is revised.

Initial inventory: `.venv/`, `manual/`, `.env`, `.gitignore`,
`requirements.txt`, `.git/`. The existing environment contains settings from
other integrations; their values are not used, displayed, or copied. Preserve
the existing `.env` and dependency list. The Phase 1 runtime uses the Python
standard library. PDF extraction utilities installed in `.venv` are development
tools only.

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
required-character rule is not fully explained. Phase 1 rejects empty writes,
does not pad/truncate, and requires the operator to check job length/offsets.

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

Phase 1 supports printable ASCII only, with documented caret escaping. It
rejects CR, LF, TAB, controls, DEL, non-ASCII, and literal backslashes (literal
backslash escaping for ET is not specified). It additionally caps the encoded
payload at 256 bytes, a conservative application restriction for escaped
carets. It never guesses or changes the printer font. Unicode sending is
deferred pending device/vendor confirmation.

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
guarantee which product receives new text during active printing. Phase 1
therefore requires operator confirmation that production is stopped and a
non-Unicode Field 0 test job is loaded before every write. This is application
policy, not a documented firmware requirement or machine-state interlock.

No ET TCP timeout/reconnect/retry contract is specified. Phase 1 uses a
configurable application deadline (default 3 s), bounded receive frames, and
no automatic reconnect or retransmission. After a failed send, delivery may
be partial/complete/unknown. Read back and inspect the printer before deciding
to resend. Each readback uses a fresh connection; each write closes its
connection without waiting for an undocumented ACK. This prevents a write's
optional echo on the same socket being mistaken for readback. There are no
transaction IDs: fresh connections cannot prove the absence of concurrent
writers or unsolicited identical ET frames. Use one controller during testing.

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
2. Implement a narrow protocol surface accepting only ET write/read commands.
3. Implement `connect`, `disconnect`, `send_command`, `set_external_text`,
   `get_external_text`, and `verify_external_text`; no startup I/O.
4. Provide the commissioning menu in order: 1 TCP-only test, 2 read current
   ExternText, 3 send fixed TEST123, 4 verify last sent text, 5 ASCII Free Text,
   6 configure session IP/port/timeout, and 0 quit.
   Show timestamped TX/RX in escaped bytes and hex, connection state, and
   errors. A comparison match is not proof of physical printing.
5. Test offline with standard-library unittest, injected sockets, and a local
   TCP simulator; never connect to a configured printer while developing.
6. Provide a stopped-production commissioning procedure. Hardware validation
   remains outstanding until an operator runs it.

## Unresolved questions and acceptance work

- Actual printer IP/port, firmware, `?ET` support, installed job/font, and
  whether optional echo/length/fixed-block modes were previously enabled.
- Validate the derived ET response shape on hardware, including escaping.
- Resolve variable-length versus required-character behavior, empty text,
  trailing spaces, job reload and power-cycle persistence.
- Resolve Unicode length, readback, supported glyphs, and supplementary planes
  before enabling a Unicode mode.
- Confirm active-print update behavior, buffering, and exact product/Lot
  boundary with the vendor and controlled physical tests. No automatic live
  production changes are authorized by this implementation.
- Establish a timeout and pacing policy from measured hardware behavior;
  determine connection limits and rapid reconnect handling.
- Validate the physical output and double-print-check configuration. ET
  readback alone cannot prove that the correct object or product was printed.

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

## Sequential commissioning menu update (17 September 2026)

The first site workflow is **1 -> 2 -> 3 -> 4**: TCP handshake only, `?ET`
read, confirmed `=ETTEST123`, then a separate `?ET` comparison. Action **5**
accepts ASCII Free Text such as `CHARCOAL GREY`; action **4** then compares
against that latest submitted value. Action **6** changes only session settings,
which initially come from local `.env`; no target IP is embedded in client or
protocol code. Startup performs no networking.

The CLI reports TCP CONNECTION OK/FAILED, SENT - UNVERIFIED for socket send
success, and a verification Result of VERIFIED, MISMATCH, or COMMUNICATION
ERROR. VERIFIED means exact readback only. Both send actions require the same
explicit SEND and stopped-production/non-Unicode Field 0 job confirmation.
A failed write invalidates previous comparison state; cancellation or rejected
input preserves it. Changing the target clears it.

Free Text identifies non-ASCII input as Unicode / Experimental and blocks it
before confirmation or connection. Reinspection of interface p.27 and script
p.25 confirms font/job-dependent hexadecimal transmission, not UTF-8, but does
not resolve Unicode length limits or readback representation. No Unicode
encoder or send path is enabled. Thai printing remains a separate controlled
physical investigation after ASCII acceptance. No SQL, automatic Lot monitor,
Kepware, OPC UA, Modbus, or automatic print start/stop commands were added.

Validation: the full offline suite (`python -m unittest discover -s tests -v`)
passed all 61 tests on 17 September 2026. Coverage includes the full CLI site
workflow with exact wire bytes through injected sockets, TCP-only results,
fixed and free-text confirmation, Thai/non-ASCII blocking, comparison results,
history invalidation, and the existing loopback transport tests. The real Jet3
was not contacted; local `.env` defaults were checked without network activity.
