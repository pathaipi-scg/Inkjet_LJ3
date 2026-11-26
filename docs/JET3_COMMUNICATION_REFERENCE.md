# LEIBINGER JET3 Communication Reference

**Audience:** developers, maintainers, and AI coding agents working on this repository.
**Last reviewed:** 2026-11-26.
**Status:** implementation reference for the current working tree, including uncommitted changes. This document distinguishes code/test behavior from the operator-confirmed physical commissioning result. It is not a vendor specification and does not authorize printer operations.

> **Safety boundary:** Do not connect to, write to, or start printing on a physical JET3 while using this reference for software work. The ISO-8859-11 path and Mailmode path described below are experimental, limited application paths. The selected physically demonstrated solution is the operator-confirmed Field 0 `=ET` setup in §13; the current general CLI does not offer a user-entered combined Thai string through the ordinary transaction workflow.

## Contents

1. [Purpose and evidence conventions](#1-purpose-and-evidence-conventions)
2. [Architecture and operational boundary](#2-architecture-and-operational-boundary)
3. [Protocol command inventory](#3-protocol-command-inventory)
4. [TCP transport and frame handling](#4-tcp-transport-and-frame-handling)
5. [Text validation, escaping, and Thai encoding](#5-text-validation-escaping-and-thai-encoding)
6. [Configuration](#6-configuration)
7. [Python implementation examples](#7-python-implementation-examples)
8. [Status inquiries and readiness](#8-status-inquiries-and-readiness)
9. [Write transactions, concurrency, and local journal](#9-write-transactions-concurrency-and-local-journal)
10. [SQL persistence, recovery, and sensitive data](#10-sql-persistence-recovery-and-sensitive-data)
11. [CLI actions and offline development](#11-cli-actions-and-offline-development)
12. [Troubleshooting](#12-troubleshooting)
13. [Verification, tests, and physical commissioning result](#13-verification-tests-and-physical-commissioning-result)

## 1. Purpose and evidence conventions

This is a repository-specific, standalone guide to the Python application’s JET3 communication implementation: command construction, TCP framing, supported and experimental paths, state reads, write verification, local/SQL audit behavior, and observed physical test result. It summarizes source and tests; consult the cited implementation for exact behavior when changing code.

Evidence labels used here:

- **Implementation:** behavior visible in current source. Unless a subsection says otherwise, a source description is not proof of device behavior.
- **Offline-tested:** behavior exercised by unit tests with fake sockets or a loopback TCP simulator. It proves the tested software scenario, not printer firmware behavior.
- **Operator-confirmed:** physical setup/result reported by the site operator and recorded in the commissioning documentation; it was not independently inspected or repeated while preparing this reference.
- **Unknown/not established:** not guaranteed by the protocol extracts, source, tests, or the limited physical result.

Current working-tree source may include uncommitted changes. The implementation and tests were inspected as present locally; their presence does not mean they are part of the last commit. Do not silently generalize a test value, one printer configuration, or one physical sample to other jobs or firmware.

## 2. Architecture and operational boundary

The package is a Python 3.11 terminal tool. `lj3.config` loads local settings; `lj3.protocol` validates/builds commands and parses frames; `lj3.client.LJ3Client` owns a TCP session and emits communication events; `lj3.status` collects read-only status; `lj3.transaction` coordinates guarded writes; `lj3.journal` persists local JSON Lines; and `lj3.db` handles optional SQL Server persistence and migrations. `lj3.__main__` provides the menu. `Inkjet.bat` launches the package entry point.

The application changes External Text on an already loaded job. It does not create/upload jobs, query a production database for Lot/product/color, make the printer connect to SQL, inhibit PLC triggers, stop production, or initiate printing. Status facts that cannot be queried remain unknown; software readiness is not a machine-safety interlock. The per-printer lock only serializes operations in this Python process, not another process, computer, PLC, HMI, or external writer.

Core communications use Python’s standard library. Optional SQL Server integration uses `pyodbc` and a compatible Microsoft ODBC driver (see `requirements-mssql.txt`). No design in this guide makes arbitrary commands safe; never add a generic send console or infer permission to execute a command simply because its response syntax parses.

## 3. Protocol command inventory

Frames use ASCII device address `0` (byte `0x30`). The command spellings below are literal; `?` denotes an inquiry and `=` denotes a parameter write in the documented command set.

| Command | Direction / purpose | Application status and constraints |
| --- | --- | --- |
| `?ET` | Read current External Text (Field 0) | Read-only. Normal response decoder expects printable ASCII; the experimental raw decoder is used for the ISO-8859-11 experiment. |
| `=ET{text}` | Set External Text (Field 0) | Write. Ordinary path accepts validated printable ASCII only. ISO-8859-11 path is explicitly experimental and strictly encodes its fixed test value. A successful socket send is not a device acknowledgement. |
| `?RS` | Read documented printer status | Read-only. Decodes five documented status fields and preserves extra values as opaque data. |
| `?EX` | Read ExternText state/status | Read-only. Parses documented fields; PrintGo is taken from the documented parameter position, extras remain uninterpreted. |
| `?JL` | Read loaded job name | Read-only. Trailing tab-delimited metadata can follow the path. |
| `?SM` | Read Mailmode/FIFO status | Read-only, used only by the experimental Mailmode Field 1 path. Reports counts/state, not the identity or contents of individual queued records. |
| `=MR0<TAB>{data}` | Stage one Mailmode Field 1 record | Experimental fixed application path only; not required for the selected Thai Field 0 workflow. It is not a general-purpose write API. |

The normal command builder/client restrict outbound commands to the implementation allowlist. There is no arbitrary command prompt. In particular, do not add or manually send `!GO` (print start), `!FF` (FIFO clear), `!EM` (echo setting), or job-editing commands as part of routine documentation/testing. The code intentionally does not expose a FIFO clear operation: queue counts cannot prove record identity or rule out a competing writer. The exact allowlist is in `lj3/protocol.py` and `lj3/client.py`; the isolated Mailmode builder/transaction is in those modules and `lj3/transaction.py`.

## 4. TCP transport and frame handling

### Outbound frame

The basic un-length-prefixed command frame is:

```text
^ 0 COMMAND [PAYLOAD] CR
```

In bytes, this is `0x5E 0x30`, followed by command/payload bytes and a final `0x0D` carriage return. `0` is the ASCII address character, not NUL. The client does not add spaces, padding, a newline, or an acknowledgement expectation. Example read inquiry: `5E 30 3F 45 54 0D` (`^0?ET\r`). Example ASCII write: `^0=ETTEST123\r`.

### Inbound parser and socket behavior

The response parser handles socket fragmentation and multiple frames received together. It accepts a response with the five-decimal-digit length header in the documented position and validates the declared length through the terminating CR. A single optional LF after CR is tolerated. It rejects malformed, overlong, padded/noisy, unterminated, and otherwise ambiguous data rather than guessing. The parser’s frame bound is 4096 bytes; the client separately caps buffered incoming data while waiting for a response at 65,536 bytes.

TCP is a byte stream: one `recv()` is not guaranteed to equal one printer response. The client accumulates input until a complete protocol frame can be parsed. It uses the configured timeout for connection and response operations. A response wait has one absolute deadline; unsolicited frames do not restart that deadline. Timeout, protocol error, or transport failure closes the session. A later explicit user operation may reconnect, but the client does not automatically retry or replay the failed operation.

A successful `sendall()` for a write means only that the local socket accepted the bytes. The ordinary `=ET` command has no documented acknowledgement in this implementation. It is reported as sent/unverified until a distinct `?ET` returns the expected value. If transport fails during/after a write, delivery may be ambiguous: do not automatically repeat it.

See `lj3/protocol.py` for frame parsing and `lj3/client.py` for socket buffering, deadlines, receive limits, and error handling. These details are offline-tested with fake sockets and loopback tests, not verified against every firmware variant.

## 5. Text validation, escaping, and Thai encoding

### Ordinary text path

The regular `=ET` path accepts 1–256 characters of printable ASCII (`0x20` through `0x7E`). It rejects empty writes, control characters, TAB/CR/LF, DEL, non-ASCII characters, and literal backslashes. A caret (`^`) is escaped as the protocol’s documented `\^` sequence. Spaces are retained exactly; the encoded payload is also limited to 256 bytes. Empty readback is permitted for observation, even though an empty write is not.

Do not treat this ASCII validator as support for arbitrary Unicode or Thai. The normal user-entered free-text path deliberately refuses non-ASCII input.

### ISO-8859-11 experimental path

A separate experimental encoder uses Python’s strict `iso8859_11` codec. It does not fall back to UTF-8 or silently replace unsupported characters. It enforces its own length and control-byte checks, and uses a raw `?ET` decoder to preserve bytes for exact verification. This path is not a general Unicode feature and is not the ordinary Option 7 transaction. The current Option 11 is a fixed experiment (`สีเทานก`), not a user-configurable combined Lot/Thai value. Its software test and its historical physical configuration are not the same test.

For the operator-confirmed combined value, the recorded payload is:

```text
Text: 4691125P สีเทานกพิราบ
Payload: 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA
```

The exact write frame is `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`. `?ET` is `5E 30 3F 45 54 0D`. The raw response frame recorded for the successful test exactly matched the write frame. These bytes are evidence for that single test, not a universal mapping for all Thai text/fonts.

The physical result used `ISOB_Thai`, font `24x20`, one External Text Field 0, and placeholder length 30. A successful byte round trip only proves stored/read-back bytes match; it cannot alone prove glyph coverage, correct composition, print quality, or all-character correctness. The normal ASCII encoder’s caret-escaping behavior should not be assumed for the separate experimental encoder; maintainers must review both validation functions before reusing the latter for arbitrary input.

## 6. Configuration

Printer settings are loaded from the project-local `.env` only; the loader does not search parent folders or use process-environment fallback. Recognized keys:

| Key | Default / validation |
| --- | --- |
| `LJ3_IP` | Empty/unconfigured by default; required for network actions; IPv4 validation. |
| `LJ3_PORT` | `3000`; integer 1–65535. |
| `LJ3_TIMEOUT_SECONDS` | `10.0`; range 0.1–60 seconds. |

The parser supports `KEY=value`, matching single/double quotes, and whole-line comments. It ignores unrelated keys. It does not implement shell interpolation, `export`, inline comments, or multiline values. Duplicate recognized keys and malformed settings fail without printing supplied values. In-menu target changes are session-only. Do not put credentials in the printer settings or commit `.env`.

Optional SQL settings are described in §10. Use `.env.example` only as a template and verify it against the deployed local configuration; template values are not proof of the active environment. Never copy a real server address, username, password, or connection string into source, docs, tests, logs, or this reference.

## 7. Python implementation examples

Examples are interface sketches based on the current package; they are not executed here. The first is a read-only inquiry and the second is a validation/encoding demonstration that performs no network operation.

### Read-only `?ET` using the client

```python
from lj3.config import load_settings
from lj3.client import LJ3Client

settings = load_settings()
client = LJ3Client(settings)
try:
    client.connect()
    value = client.get_external_text()
    print(value)
finally:
    client.disconnect()
```

This opens a TCP connection and sends a read-only inquiry, so use it only in an authorized environment. It is not an offline example. The client may retain a session between explicit menu actions; callers should always close it in a `finally` block. Avoid logging production text unless required by approved audit policy.

### Validate a candidate without connecting

```python
from lj3.protocol import encode_experimental_iso8859_11

text = "4691125P สีเทานกพิราบ"
payload = encode_experimental_iso8859_11(text)
print(payload.hex(" ").upper())
```

This computes candidate bytes locally only. It does not build/send a command and does not establish that the printer’s currently loaded job/font uses that mapping. For an actual frame builder, inspect `build_experimental_iso8859_11_frame` and its guard conditions in `lj3/protocol.py`; do not call a send/write method without a separately approved commissioning plan and explicit safety preflight.

### Isolated loopback/fake transport for tests

Follow the fixture patterns in `tests/test_client.py` and `tests/test_loopback.py`: inject a fake socket or bind a simulator to `127.0.0.1` with an ephemeral port. Do not point tests at a printer IP, production DNS name, or port. Assert exact bytes, timeout behavior, and no retry; tests must not start a print or clear a queue.

## 8. Status inquiries and readiness

`read_printer_snapshot()` issues read-only `?RS`, `?EX`, and `?JL` inquiries sequentially and records raw event evidence. The decoders preserve unknown extra fields rather than assigning undocumented meanings.

- `?RS`: five documented status values are interpreted; additional fields are opaque.
- `?EX`: extracts the documented ExternText state; PrintGo is interpreted from its documented field position. Reserved/extra fields remain opaque.
- `?JL`: decodes the loaded job name while tolerating trailing tab-separated metadata.
- `?SM`: only used for the experimental Mailmode FIFO count check; count is not record identity.

The application marks printing true for the documented active state, false for recognized idle/ready states, and otherwise unknown. ExternText readiness requires the implementation’s specific ready state and zero printer error. The automatic status gate blocks unless readiness passes, printing is known false, and PrintGo is low. Option 7 also checks the expected job `CB-LOT-TEST.job`. Unknown values block rather than being treated as safe; these software gates are not a complete safety preflight.

These reads do not verify physical trigger inhibition, production-stop state, sole-writer exclusivity outside this process, command echo configuration, paper/marking quality, or that a subsequent product will be correct. Operator attestations and local site safety procedure remain separate requirements; status parsing is not a safety-rated interlock.

## 9. Write transactions, concurrency, and local journal

The automatic transaction path is designed as a one-shot operation: acquire a non-blocking per-printer process lock; collect read-only snapshot and job gates; record a baseline; persist write intent; issue a single write; and, where supported, perform same-session readback and store the result. A mismatch or uncertain transport outcome is reported as failure/unknown, not success. There is no automatic retry. **Current CLI prompt limitation:** Option 7 asks the operator to confirm external triggers are inhibited and echo is disabled, and states that this application is the only writer; it does not explicitly ask whether production is stopped. The transaction API’s safety flag covers stopped printing/triggers/no competing writer, so do not treat the CLI’s current prompt or a ready status as proof that production has stopped. Follow site controls and resolve this gap before relying on Option 7 for a physical write.

The lock is an in-process lock keyed by case-folded host and port. It prevents two cooperating threads/operations in this process from queueing behind one another, but cannot stop another application, machine, PLC, or HMI from writing. It must not be described as distributed locking.

The local JSON Lines journal defaults to `logs/pending_transactions.jsonl`. It appends compact JSON, flushes, and calls `fsync`. A write-intent record is persisted before an automatic transaction’s write; if that journal write fails, the printer write is not attempted. Interrupted pending intent becomes `WRITE_OUTCOME_UNKNOWN` during recovery. Recovery is for persistence only: it does not create a printer client, send commands, or replay a write. Malformed journal records cause recovery to fail visibly rather than being silently accepted.

The journal is runtime data and should remain ignored/untracked. It can contain requested/baseline/readback text and raw TX/RX hex; do not attach it publicly without redaction and authorization. Manual send/read menu actions are not all equivalent to the fully audited automatic transaction path.

### Mailmode caveat

Option 12 is experimental, fixed Field 1 Mailmode behavior. It checks stable empty FIFO counts before staging one hard-coded `=MR` candidate and observes the post-write count. It intentionally does not clear the FIFO or start printing. If the count is unexpected, the transaction fails and leaves the queue untouched. Since `?SM` exposes counts but not queued-record identities, it cannot prove the one queued record belongs to this client or safely authorize `!FF`. A staged success is `STAGED_UNVERIFIED`, not a print success. Do not use Mailmode for the confirmed Field 0 solution.

## 10. SQL persistence, recovery, and sensitive data

SQL Server support is optional and separate from printer transport. The application opens SQL connections only for configured SQL operations; the printer has no SQL connection. `pyodbc` plus an available ODBC driver is required. The driver selector can try supported installed drivers; connection encryption is requested by the implementation. SQL schema/migrations live in `sql/migrations/`.

Recognized SQL settings are `SQL_DRIVER`, `SQL_SERVER`, `SQL_DB`, `SQL_USER`, `SQL_PASS`, `SQL_TRUST_SERVER_CERTIFICATE`, and `SQL_PORT`. The required connection values are server, database, user, and password. Defaults in code include automatic driver selection, port 1433, and certificate trust disabled. Treat real `.env` values and connection strings as secrets; do not print them, commit them, or copy them into diagnostic messages. An explicit server override for a migration/inspection process is not a replacement for normal configured application settings.

The schema is under `inkjet` and contains five tables: `PrinterMaster`, `TransactionLog`, `PrinterStatus`, `StatusLog`, and `ErrorLog`; views include `vw_PrinterStatus`, `vw_TransactionHistory`, `vw_ErrorHistory`, and `vw_DailySummary`. Migrations are repeatable/idempotent in the intended workflow and split SQL batches on `GO`. Persisted events include timestamps, event kinds, messages, and raw data hex; transaction records use a UUID and parameterized SQL values. Times are converted to Asia/Bangkok wall time for SQL `datetime2(3)` (that SQL type does not itself retain timezone metadata).

The local journal is the recovery source when SQL is unavailable. SQL replay is idempotent by transaction identifier; successful persistence is recorded so recovery can skip already-persisted records. An interrupted write intent is retained as an unknown outcome and is not retried. Database errors are sanitized: do not expose credentials, full connection strings, or detailed exception text to users.

Audit retention requires care: although credentials are not intentionally stored in the schema/journal, transaction text and raw payload bytes are recorded and may contain production Lot data. Apply site retention/access controls to both SQL tables and the local journal. The live SQL integration test is opt-in via `INKJET_SQL_TEST_SERVER`; do not run it unless authorized, as it connects to SQL and writes/deletes its own synthetic rows.

## 11. CLI actions and offline development

Launch with `python -m lj3` (or repository `Inkjet.bat` on Windows). The menu currently exposes:

| Action | Behavior |
| --- | --- |
| 1 | TCP connect test only. |
| 2 | Read External Text (`?ET`). |
| 3 | Send fixed ASCII test value. |
| 4 | Verify the most recent manual write using a distinct inquiry; it will not silently reconnect and claim same-session verification. |
| 5 | Send validated free text (ASCII only). |
| 6 | Change target for this process session. |
| 7 | Guarded automatic one-shot transaction with job/readiness checks and audit persistence. |
| 8 | Read-only status snapshot and logging. |
| 9 | Inspect configured SQL/schema state. |
| 10 | Recover/replay local journal records to SQL; no printer commands. |
| 11 | Experimental fixed ISO-8859-11 `=ET` test. |
| 12 | Experimental fixed Mailmode Field 1 staging/check. |
| 0 | Quit. |

Menu numbering and prompts can evolve; confirm `lj3/__main__.py` before writing automation around the interactive menu. The separate database module supports inspection and migration flags; a migration changes a database and must be run only with explicit authorization and the intended server/database.

Offline suite command from the project root (with the project virtual environment installed):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fakes and loopback only for printer protocol behavior. The optional SQL integration test is not part of a safe offline-only run unless its opt-in server setting is present. Verify test configuration and environment variables before executing; do not point test fixtures to a physical printer.

## 12. Troubleshooting

| Symptom | Interpretation and safe next step |
| --- | --- |
| TCP connection refused/times out | Check local configuration, network route, endpoint/port, and authorized device availability. A TCP connection alone does not establish printer readiness. Do not repeatedly probe production equipment. |
| No complete response before deadline | The response may be delayed, fragmented, or absent. Check the captured frame and configured timeout. The client uses an absolute response deadline and does not retry. A write timeout leaves delivery uncertain. |
| Invalid frame, length, padding, or extra bytes | Preserve raw TX/RX evidence; compare address, CR termination, optional LF, declared length, and parser limits. Do not strip arbitrary bytes or loosen validation without protocol evidence and tests. |
| `?ET` cannot decode existing Thai | The regular reader expects ASCII. Use raw-byte diagnostics only in an authorized, explicitly designed workflow; do not infer a codec from visual text or silently decode with replacement. |
| Write says sent but not verified | `sendall()` is not an acknowledgement. Perform only the explicitly planned readback in the same live session. Never replay a possibly delivered write automatically. |
| Status/PrintGo/job gate blocks | Treat unknown/error/active-print/high-PrintGo/wrong-job as a block. Resolve via the site’s approved procedure; do not bypass the guard by sending low-level commands. |
| ISO-8859-11 encodes but glyphs are wrong/incomplete | Byte encoding and glyph rendering are separate. Check the configured character set/font, Field 0 placeholder/offset and rendered HMI value; revalidate print quality and every required character under controlled commissioning. |
| Mailmode FIFO count is nonzero or unstable | Do not clear it. Counts do not identify records, and another writer may race. Leave it untouched and use the selected Field 0 workflow if that is the approved design. |
| SQL unavailable or migration fails | Preserve the sanitized error and local journal. Check driver installation, configured server/database, permissions, and migration state out of band. Do not print secrets or retry printer writes as part of SQL recovery. |
| Duplicate local lock | Another cooperating in-process operation is active. Wait for the operation to finish; the lock does not report external writers. |

Never troubleshoot by enabling automatic retries, clearing the FIFO, starting print, weakening frame validation, or echoing environment/SQL credentials.

## 13. Verification, tests, and physical commissioning result

### Offline verification coverage

The current suite contains 104 tests across protocol, client, CLI/config, transaction, database, and loopback behavior. Covered cases include exact command/frame construction, allowlisting, text and encoding restrictions, fragmented/coalesced responses, CR/optional-LF and length parsing, status decoders, timeouts, no-retry behavior, same-session verification, safety/preflight blocks, lock contention, journal failure/recovery, Mailmode queue anomaly handling without FIFO clearing, SQL batch/persistence/recovery logic, and loopback simulation. The offline run for this reference discovered 104 tests: 103 passed and the opt-in live SQL integration test was skipped with its server setting disabled. The live SQL integration test is a separate network/database test and must not be conflated with printer-offline tests.

Tests establish behavior of code under simulated inputs. They do not prove a specific printer, firmware, font, job, live network, or printed output. The working tree has uncommitted implementation and test files as of this reference; read the actual checkout and test output before making future claims about released behavior.

### Operator-confirmed physical Thai test — 2026-11-26

The operator confirmed the following one test configuration:

| Item | Confirmed value |
| --- | --- |
| Job | `CB-LOT-TEST` |
| Command | `=ET` |
| Encoding | ISO-8859-11 |
| Character set | `ISOB_Thai` |
| Font | `24x20` |
| External Text Field | `0` |
| Placeholder length | `30` |
| Text | `4691125P สีเทานกพิราบ` |

The operator reported successful TCP communication, exact raw write/readback payload equality, correct mixed English/numeric/Thai display on the HMI, and physical Thai printing demonstrated on paper. Print quality and complete physical character verification still require improvement. Mailmode, `=MR`, and FIFO were not needed or used. The recorded raw write frame and readback are shown in §5 and in `docs/JET3_ONSITE_COMMISSIONING.md`.

This is a limited operator-confirmed result, not an independently reproduced result in this documentation task. It does **not** certify arbitrary Thai strings, all glyphs, general Unicode support, every printer/job/font/firmware, production cutover timing, product correctness, or final print quality. The experiment is distinct from the fixed Option 11 test and from the experimental Mailmode Option 12 implementation. No physical printer connection or command was made while preparing this reference.

### Maintainer change checklist

Before changing this protocol layer:

1. Read the actual command manuals/extracts under `docs/manual-extracted/` and inspect the current source, not only this summary.
2. Keep the command allowlist narrow and distinguish inquiry from mutation.
3. Add offline tests for exact bytes, fragmented reads, malformed responses, timeout, failure ambiguity, and no retries.
4. Keep experimental encodings separate from ordinary ASCII behavior; never silently decode/replace bytes.
5. Preserve unknown status fields and unknown physical states; fail closed at transaction gates.
6. Keep write intent durable before transmission and make recovery database-only, never printer-replay.
7. Do not expose secrets or include `.env`, runtime logs, SQL connection material, or temporary artifacts in commits.
8. Physical commissioning requires a separate authorized plan; this reference does not authorize connection, writing, FIFO access, or printing.
