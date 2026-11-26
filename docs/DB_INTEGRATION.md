# JET3 automatic transaction and SQL Server integration

## Scope and commissioning guard

This implementation provides one automatic ExternText transaction, structured printer-state snapshots, SQL persistence, and durable local recovery. It does not retrieve the Lot from MES, look up a product/color, upload/reload a job, acknowledge errors, start/stop printing, or trigger a physical print. The existing printer job is not changed by software.

The automatic path is: validate ASCII -> acquire the in-process lock for the configured printer -> read `?RS`, `?EX`, and `?JL` -> apply documented readiness gates -> read baseline using `?ET` -> append/fsync a local write-intent record -> issue exactly one `=ET` -> read `?ET` on the same socket -> compare exact text -> append/fsync the final result -> persist to SQL when available. Any error is reported with a stable transaction ID and category. No automatic write retry is performed. If delivery is uncertain, do not repeat it blindly.

The readiness gate requires machine state 4 (Ready for Action), error 0, and a low PrintGo signal. This is a conservative application rule, not a vendor guarantee of `=ET` acceptance. State codes and PrintGo are decoded only as defined in the supplied interface protocol manual. Unknown codes/invalid responses are never READY. A high or unavailable PrintGo blocks the write.

The protocol does not report whether production is stopped, whether an external PLC has inhibited triggers, or whether another external client is writing. `?EX` PrintGo low is only a live signal level, not proof of an inhibit. The supplied manual documents `!EM` to enable command echo but no status inquiry or disable command; echo state remains UNKNOWN and must be confirmed disabled before a transaction. Option 7 asks the operator to confirm inhibited triggers and disabled echo; it states that this application is the only ExternText writer but does not explicitly ask the operator to attest that production is stopped. The transaction API's safety flag represents stopped production, trigger inhibition, and no competing writer, so this is a prompt/contract gap. A ready-state/PrintGo check is not proof that production has stopped. Resolve the gap and use independent site controls before relying on Option 7 for a physical write. The application cannot enforce physical attestations.

A process-wide per-printer re-entrant lock serializes automatic transactions and direct ExternText writes within this Python process. It cannot exclude a second application process, unrelated host, PLC, HMI, or other TCP client.

## Status meanings

| Condition | Source | Meaning |
| --- | --- | --- |
| TCP connected | Socket | Transport only; not printer identity or readiness |
| Protocol valid | Complete parsed `=RS`, `=EX`, `=JL` | The documented frames were received and decoded |
| ExternText-ready | `=RS` machine state 4 and error 0 | Application's required write gate |
| Printing | `=RS` state 6 | Known when a valid recognized state is received; other recognized states report not currently in the manual's Printing state |
| PrintGo high/low | `=EX` Par6 | Live sensor signal only |
| Production stopped | Not exposed in the supported inquiries | UNKNOWN |
| Trigger inhibition | Not exposed in the supported inquiries | UNKNOWN |
| Command echo enabled | No documented status inquiry | UNKNOWN |
| Physical print/readability | Not verified by `?ET` | NOT TESTED by a communication transaction |

`?JL` is used only to read the loaded job name. The client allowlist does not expose the state-changing `=JL` job-load command. Undocumented response fields are retained as opaque values and not assigned speculative meaning.

## Outcomes and categories

The structured result includes transaction UUID, printer endpoint, requested text, baseline, readback, outcome/category, message, Asia/Bangkok start/end timestamps, elapsed milliseconds, status snapshot, raw frame evidence (hex), and local-journal persistence state.

Outcomes include `VERIFIED`, `MISMATCH`, `BLOCKED`, and `FAILED`. Categories distinguish invalid text, missing operator attestation, unknown echo state, application-lock busy, printer not ready, timeout, protocol error, communication error, and database failure. `VERIFIED` means only that the exact string returned from same-session `?ET` equals the requested string; it does not mean that a product was marked correctly.

## Durable local journal and recovery

The append-only `logs/pending_transactions.jsonl` journal is flushed and fsynced. A write-intent record is persisted before the `=ET` frame; if that disk write fails, the transaction does not send the printer write. Final results/status samples are journaled before database delivery. SQL credentials and connection strings are never placed in the journal. Printer TX/RX evidence is represented as hex.

`TransactionJournal.pending_records()` validates the full journal and fails closed on malformed lines. SQL recovery collapses each transaction UUID to its latest local record. `WRITE_PENDING` is stored as `WRITE_OUTCOME_UNKNOWN`; this is an audit state only. Recovery never constructs an `LJ3Client`, never sends a printer command, and never retries `=ET`. SQL insert/update operations are parameterized and idempotent by transaction UUID; recovery can be run repeatedly.

## SQL Server schema

The deployment target approved for this commissioning is SQL Server `10.28.255.19`, database `CB`, schema `inkjet`. Migration scripts create only these five tables and four views:

| Object | Purpose |
| --- | --- |
| `inkjet.PrinterMaster` | Endpoint identity and enabled flag |
| `inkjet.PrinterStatus` | Latest/transaction-associated documented and nullable state fields |
| `inkjet.StatusLog` | Timestamped transaction events and raw frame hex |
| `inkjet.TransactionLog` | Requested, baseline, readback, outcome, category, timings |
| `inkjet.ErrorLog` | Structured failures/mismatches and diagnostic category |
| `inkjet.vw_PrinterStatus` | Latest status per printer |
| `inkjet.vw_TransactionHistory` | Joined transaction history |
| `inkjet.vw_ErrorHistory` | Joined error history |
| `inkjet.vw_DailySummary` | Verified/mismatch/failed/blocked daily counts, excluding status-only samples |

SQL syntax is SQL Server 2019 compatible. Schema/table/index creation is guarded and repeatable; views are created or altered by project-owned migrations. No unrelated objects are dropped. Foreign keys link status/log rows to the printer and transaction. The TCP port is SQL `int` so the full 1–65535 range is representable.

Application timestamps use `Asia/Bangkok` at UTC+07:00. They are converted to local naive datetimes before insertion into `datetime2(3)`; this type does not retain a zone. Consumers must interpret these columns as Bangkok local time. No SQL login password is stored in the repository or database objects.

## Configuration and migration commands

Database settings are read only from the project-local `.env` using the existing keys:

- `SQL_DRIVER` (`AUTO` selects installed ODBC Driver 18, then 17, then legacy SQL Server driver)
- `SQL_SERVER`
- `SQL_PORT` (optional, defaults to 1433)
- `SQL_DB`
- `SQL_USER`
- `SQL_PASS`
- `SQL_TRUST_SERVER_CERTIFICATE`

The local `.env` contains `SQL_SERVER=127.0.0.1`, intentionally: the application and SQL Server `10.28.255.19` run on the same physical server. SQL credentials were not printed, and `.env` was not changed. Normal menu database operations use this configured localhost endpoint without an override; this path was verified to reach database `CB` and the approved `inkjet` schema objects.

Install Python support using `pip install -r requirements-mssql.txt` and install a supported Microsoft SQL Server ODBC driver. To inspect the authorized server and apply migrations:

```powershell
.\.venv\Scripts\python.exe -m lj3.db --inspect --server 10.28.255.19
.\.venv\Scripts\python.exe -m lj3.db --migrate --server 10.28.255.19
```

Without `--server`, the SQL tool uses `SQL_SERVER` from `.env`. Migration scripts are repeatable and kept under `sql/migrations/`; they do not store deployment credentials.

## Validation record

The authorized host was reached using the ODBC Driver 17 for SQL Server and the local `.env` credentials (not displayed). The database reported `CB`, product version `15.0.2000.5` (SQL Server 2019). Read-only permission checks reported `sysadmin`, `CREATE TABLE`, `CREATE VIEW`, and `ALTER ANY SCHEMA` available. Before migration, the `inkjet` schema and objects were absent. After migration, the five approved tables and four approved views were present. Normal application Option 9 subsequently verified the same database/schema through `127.0.0.1:1433`.

The live integration test performed a parameterized transaction/status/log insert, read the transaction view, verified a duplicate insert was idempotently ignored, and deleted only its own synthetic transaction and printer rows. It passed. A later separately authorized Option 8 physical status check used the application and normal `.env` configuration. It sent only `?RS`, `?EX`, and `?JL`; its status snapshot was verified in `inkjet.PrinterStatus` and its 11 connection/TX/RX/timing events in `inkjet.StatusLog`. No `=ET` write or Option 7 was run. See [JET3_ONSITE_COMMISSIONING.md](JET3_ONSITE_COMMISSIONING.md) for the actual raw responses and decoded results.

To rerun offline tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To opt into the actual SQL integration test, set `INKJET_SQL_TEST_SERVER=10.28.255.19` in the test process and run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_db -v
```

The integration test requires the existing `.env` SQL credentials and permission to use/delete its own uniquely identified synthetic rows. It does not contact the printer.
