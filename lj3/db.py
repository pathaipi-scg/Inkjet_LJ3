"""SQL Server persistence, idempotent migrations, and local-journal recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re
import argparse
from typing import Any
from uuid import UUID

from .config import PROJECT_ROOT
from .journal import TransactionJournal

BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")
SQL_KEYS = {"SQL_DRIVER", "SQL_SERVER", "SQL_DB", "SQL_USER", "SQL_PASS",
            "SQL_TRUST_SERVER_CERTIFICATE", "SQL_PORT"}
EXPECTED_TABLES = {"PrinterMaster", "PrinterStatus", "StatusLog", "TransactionLog", "ErrorLog"}
EXPECTED_VIEWS = {"vw_PrinterStatus", "vw_TransactionHistory", "vw_ErrorHistory", "vw_DailySummary"}


class DatabaseError(RuntimeError):
    """Safe user-facing database error; never contains a connection string."""


@dataclass(frozen=True)
class DatabaseSettings:
    driver: str
    server: str
    database: str
    username: str
    password: str
    trust_server_certificate: bool
    port: int = 1433


def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in SQL_KEYS:
            continue
        if key in result:
            raise DatabaseError(f"Duplicate {key} in project .env.")
        value = value.strip()
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise DatabaseError(f"Invalid quoting for {key} in project .env.")
            value = value[1:-1]
        result[key] = value
    return result


def load_database_settings(path: Path | None = None) -> DatabaseSettings:
    values = _read_env(path or PROJECT_ROOT / ".env")
    required = ("SQL_SERVER", "SQL_DB", "SQL_USER", "SQL_PASS")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise DatabaseError("SQL configuration is incomplete; required keys: " + ", ".join(missing))
    try:
        port = int(values.get("SQL_PORT", "1433"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise DatabaseError("SQL_PORT must be an integer from 1 to 65535.") from exc
    trust_text = values.get("SQL_TRUST_SERVER_CERTIFICATE", "false").lower()
    if trust_text not in {"true", "false", "yes", "no", "1", "0"}:
        raise DatabaseError("SQL_TRUST_SERVER_CERTIFICATE must be true or false.")
    return DatabaseSettings(values.get("SQL_DRIVER", "AUTO"), values["SQL_SERVER"],
                            values["SQL_DB"], values["SQL_USER"], values["SQL_PASS"],
                            trust_text in {"true", "yes", "1"}, port)


def _quoted_odbc(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def _to_db_time(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(BANGKOK).replace(tzinfo=None)


def _safe_sqlstate(exc: Exception) -> str:
    for argument in getattr(exc, "args", ()):
        if isinstance(argument, str) and re.fullmatch(r"[A-Z0-9]{5}", argument):
            return argument
    return "unknown"


class SqlRepository:
    def __init__(self, settings: DatabaseSettings | None = None, *, connect_factory=None,
                 server_override: str | None = None):
        self.settings = settings
        self._connect_factory = connect_factory
        self.server_override = server_override

    def _connect(self, server_override: str | None = None):
        settings = self.settings or load_database_settings()
        server_override = server_override or self.server_override
        if self._connect_factory:
            return self._connect_factory(settings, server_override)
        try:
            import pyodbc
        except ImportError as exc:
            raise DatabaseError("pyodbc is not installed; install requirements-mssql.txt.") from exc
        installed = pyodbc.drivers()
        requested = settings.driver
        if requested.upper() == "AUTO":
            driver = next((name for prefix in ("ODBC Driver 18 for SQL Server",
                                               "ODBC Driver 17 for SQL Server",
                                               "SQL Server")
                           for name in installed if name == prefix), None)
        else:
            driver = requested if requested in installed else None
        if not driver:
            raise DatabaseError("Configured SQL ODBC driver is not installed or available.")
        host = server_override or settings.server
        server = host if "," in host or "\\" in host else f"{host},{settings.port}"
        connection_string = ";".join((
            f"DRIVER={_quoted_odbc(driver)}", f"SERVER={_quoted_odbc(server)}",
            f"DATABASE={_quoted_odbc(settings.database)}", f"UID={_quoted_odbc(settings.username)}",
            f"PWD={_quoted_odbc(settings.password)}", "Encrypt=yes",
            "TrustServerCertificate=" + ("yes" if settings.trust_server_certificate else "no"),
            "Connection Timeout=5", "APP=Inkjet_LJ3"))
        try:
            return pyodbc.connect(connection_string, timeout=5, autocommit=False)
        except Exception as exc:
            # Driver exceptions can echo credential-bearing connection fragments.
            raise DatabaseError(f"SQL connection failed ({type(exc).__name__}); details suppressed.") from None

    def inspect(self, server_override: str | None = None) -> dict[str, Any]:
        connection = self._connect(server_override)
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT DB_NAME(), CONVERT(varchar(128), SERVERPROPERTY('ProductVersion')),
                HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE'),
                HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE VIEW'),
                HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'ALTER ANY SCHEMA')""")
            database, version, create_table, create_view, alter_schema = cursor.fetchone()
            cursor.execute("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID(?)", ("inkjet",))
            tables = sorted(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT name FROM sys.views WHERE schema_id=SCHEMA_ID(?)", ("inkjet",))
            views = sorted(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT SCHEMA_ID(?)", ("inkjet",))
            schema_exists = cursor.fetchone()[0] is not None
            cursor.execute("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT')", ("inkjet.PrinterMaster",))
            select_permission = cursor.fetchone()[0]
            cursor.execute("SELECT IS_SRVROLEMEMBER('sysadmin')")
            is_sysadmin = cursor.fetchone()[0]
            return {"database": database, "version": version,
                    "sql_server_2019": str(version).startswith("15."),
                    "create_table": bool(create_table), "create_view": bool(create_view),
                    "alter_schema": bool(alter_schema), "select_permission": select_permission,
                    "is_sysadmin": bool(is_sysadmin), "schema_exists": schema_exists,
                    "tables": tables, "views": views,
                    "missing_tables": sorted(EXPECTED_TABLES - set(tables)),
                    "missing_views": sorted(EXPECTED_VIEWS - set(views))}
        except Exception as exc:
            raise DatabaseError(f"SQL inspection failed ({type(exc).__name__}); details suppressed.") from None
        finally:
            connection.close()

    def migrate(self, migration_dir: Path | None = None,
                server_override: str | None = None) -> list[str]:
        path = migration_dir or PROJECT_ROOT / "sql" / "migrations"
        scripts = sorted(path.glob("*.sql"))
        if not scripts:
            raise DatabaseError("No SQL migration scripts were found.")
        connection = self._connect(server_override)
        applied: list[str] = []
        try:
            cursor = connection.cursor()
            for script in scripts:
                batches = re.split(r"(?im)^\s*GO\s*(?:--.*)?$", script.read_text(encoding="utf-8"))
                for batch in batches:
                    if batch.strip():
                        cursor.execute(batch)
                applied.append(script.name)
            connection.commit()
            return applied
        except Exception as exc:
            connection.rollback()
            raise DatabaseError(f"SQL migration failed ({type(exc).__name__}); transaction rolled back.") from None
        finally:
            connection.close()

    def persist_record(self, record: dict[str, Any]) -> bool:
        """Insert/update one journal record atomically; return False if already finalized."""
        settings = self.settings or load_database_settings()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            ip = str(record.get("printer_ip", ""))
            port = int(record.get("printer_port", 0))
            code = f"LJ3-{ip}:{port}"[:64]
            cursor.execute("SELECT PrinterId FROM inkjet.PrinterMaster WHERE PrinterCode=?", (code,))
            row = cursor.fetchone()
            if row:
                printer_id = row[0]
            else:
                created = _to_db_time(datetime.now(BANGKOK))
                cursor.execute("""INSERT INTO inkjet.PrinterMaster
                    (PrinterCode, PrinterName, IpAddress, TcpPort, IsEnabled, CreatedAt)
                    OUTPUT INSERTED.PrinterId VALUES (?, ?, ?, ?, 1, ?)""",
                    code, code, ip or "unknown", port or settings.port, created)
                printer_id = cursor.fetchone()[0]

            transaction_id = str(UUID(str(record["transaction_id"])))
            outcome = str(record.get("outcome", "FAILED"))
            if outcome == "WRITE_PENDING":
                outcome = "WRITE_OUTCOME_UNKNOWN"
            started = _to_db_time(record["started_at"])
            completed = _to_db_time(record["completed_at"])
            cursor.execute("SELECT Outcome FROM inkjet.TransactionLog WHERE TransactionId=?", transaction_id)
            existing = cursor.fetchone()
            if existing and existing[0] not in {"WRITE_OUTCOME_UNKNOWN", "WRITE_PENDING"}:
                connection.commit()
                return False
            values = (printer_id, started, completed, str(record.get("requested_text", "")),
                      record.get("baseline_text"), record.get("readback_text"), outcome,
                      str(record.get("category", "UNKNOWN"))[:48], str(record.get("message", ""))[:1000],
                      Decimal(str(record.get("elapsed_ms", 0))))
            if existing:
                cursor.execute("""UPDATE inkjet.TransactionLog SET PrinterId=?, StartedAt=?, CompletedAt=?,
                    RequestedText=?, BaselineText=?, ReadbackText=?, Outcome=?, ErrorCategory=?, Message=?, ElapsedMs=?
                    WHERE TransactionId=?""", (*values, transaction_id))
            else:
                cursor.execute("""INSERT INTO inkjet.TransactionLog
                    (TransactionId, PrinterId, StartedAt, CompletedAt, RequestedText, BaselineText,
                     ReadbackText, Outcome, ErrorCategory, Message, ElapsedMs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    transaction_id, *values)

            snapshot = record.get("snapshot")
            if snapshot:
                cursor.execute("SELECT StatusId FROM inkjet.PrinterStatus WHERE TransactionId=?", (transaction_id,))
                status_exists = cursor.fetchone()
                status_values = (printer_id, transaction_id, _to_db_time(snapshot["sampled_at"]),
                    snapshot.get("nozzle_state"), snapshot.get("machine_state"), snapshot.get("printer_error"),
                    snapshot.get("headcover"), snapshot.get("act_speed"), snapshot.get("extern_actual_speed"),
                    snapshot.get("extern_max_speed"), snapshot.get("inputs"), snapshot.get("direction"),
                    snapshot.get("printgo") == 1 if snapshot.get("printgo") is not None else None,
                    snapshot.get("printing"),
                    snapshot.get("machine_state") == 4 and snapshot.get("printer_error") == 0
                        if snapshot.get("machine_state") is not None else None,
                    snapshot.get("production_stopped"), snapshot.get("trigger_inhibited"),
                    snapshot.get("command_echo_enabled"), snapshot.get("loaded_job"),
                    __import__("json").dumps(snapshot.get("unknown_status_fields", [])))
                if status_exists:
                    cursor.execute("""UPDATE inkjet.PrinterStatus SET PrinterId=?, ObservedAt=?, NozzleState=?,
                        MachineState=?, PrinterError=?, Headcover=?, ActSpeed=?, ExternActualSpeed=?, ExternMaxSpeed=?,
                        Inputs=?, EncoderDirection=?, PrintGoHigh=?, IsPrinting=?, ExternTextReady=?, ProductionStopped=?,
                        TriggersInhibited=?, CommandEchoEnabled=?, LoadedJob=?, UnknownStatusFields=? WHERE TransactionId=?""",
                        (status_values[0], *status_values[2:], transaction_id))
                else:
                    cursor.execute("""INSERT INTO inkjet.PrinterStatus
                        (PrinterId, TransactionId, ObservedAt, NozzleState, MachineState, PrinterError, Headcover,
                         ActSpeed, ExternActualSpeed, ExternMaxSpeed, Inputs, EncoderDirection, PrintGoHigh,
                         IsPrinting, ExternTextReady, ProductionStopped, TriggersInhibited, CommandEchoEnabled,
                         LoadedJob, UnknownStatusFields)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", *status_values)

            import json
            for event in record.get("events", []):
                event_at = _to_db_time(event.get("timestamp", completed.isoformat()))
                message = str(event.get("message", ""))[:1000]
                event_type = str(event.get("kind", "INFO"))[:32]
                cursor.execute("""IF NOT EXISTS (SELECT 1 FROM inkjet.StatusLog WHERE TransactionId=?
                    AND EventAt=? AND EventType=? AND Message=?)
                    INSERT INTO inkjet.StatusLog (PrinterId, TransactionId, EventAt, EventType, Severity, Message, DataHex, ElapsedMs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    transaction_id, event_at, event_type, message, printer_id, transaction_id, event_at,
                    event_type, "ERROR" if event_type == "ERROR" else "INFO", message,
                    event.get("data_hex"), event.get("elapsed_ms"))
            if outcome not in {"VERIFIED", "STATUS_ONLY", "STAGED_UNVERIFIED"}:
                error_code = record.get("category")
                message = str(record.get("message", ""))[:1000]
                cursor.execute("""IF NOT EXISTS (SELECT 1 FROM inkjet.ErrorLog
                    WHERE TransactionId=? AND ErrorCategory=? AND Message=?)
                    INSERT INTO inkjet.ErrorLog
                    (PrinterId, TransactionId, OccurredAt, ErrorCategory, ErrorCode, Message, Details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    transaction_id, str(error_code)[:48], message, printer_id, transaction_id, completed,
                    str(error_code)[:48], str(error_code)[:64], message,
                    json.dumps({"outcome": outcome}, ensure_ascii=True))
            connection.commit()
            return True
        except DatabaseError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise DatabaseError(f"SQL persistence failed ({type(exc).__name__}, SQLSTATE {_safe_sqlstate(exc)}); "
                                "details suppressed.") from None
        finally:
            connection.close()

    def persist_database_error(self, record: dict[str, Any]) -> bool:
        """Store a sanitized SQL outage/error event, idempotent by transaction/category/message."""
        settings = self.settings or load_database_settings()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            ip = str(record.get("printer_ip", ""))
            port = int(record.get("printer_port", 0))
            code = f"LJ3-{ip}:{port}"[:64]
            cursor.execute("SELECT PrinterId FROM inkjet.PrinterMaster WHERE PrinterCode=?", (code,))
            row = cursor.fetchone()
            if row:
                printer_id = row[0]
            else:
                cursor.execute("""INSERT INTO inkjet.PrinterMaster
                    (PrinterCode, PrinterName, IpAddress, TcpPort, IsEnabled, CreatedAt)
                    OUTPUT INSERTED.PrinterId VALUES (?, ?, ?, ?, 1, ?)""",
                    code, code, ip or "unknown", port or settings.port,
                    _to_db_time(datetime.now(BANGKOK)))
                printer_id = cursor.fetchone()[0]
            transaction_id = str(UUID(str(record["transaction_id"])))
            category = str(record.get("category", "DATABASE_ERROR"))[:48]
            message = str(record.get("message", "Database persistence failed."))[:1000]
            cursor.execute("""IF NOT EXISTS (SELECT 1 FROM inkjet.ErrorLog
                WHERE TransactionId=? AND ErrorCategory=? AND Message=?)
                INSERT INTO inkjet.ErrorLog
                (PrinterId, TransactionId, OccurredAt, ErrorCategory, ErrorCode, Message, Details)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                transaction_id, category, message, printer_id, transaction_id,
                _to_db_time(record["occurred_at"]), category,
                str(record.get("error_code", ""))[:64], message,
                "SQL error details intentionally suppressed")
            connection.commit()
            return True
        except Exception as exc:
            connection.rollback()
            raise DatabaseError(f"SQL error-log persistence failed ({type(exc).__name__}, "
                                f"SQLSTATE {_safe_sqlstate(exc)}); details suppressed.") from None
        finally:
            connection.close()

    def recover(self, journal: TransactionJournal | None = None) -> tuple[int, int]:
        """Replay journal data idempotently; this method has no printer client."""
        journal = journal or TransactionJournal()
        latest: dict[str, dict[str, Any]] = {}
        errors: dict[str, dict[str, Any]] = {}
        for record in journal.pending_records():
            if record.get("record_type") == "DATABASE_ERROR":
                errors[str(record.get("error_event_id", record["transaction_id"]))] = record
            else:
                latest[str(record["transaction_id"])] = record
        succeeded = failed = 0
        for record in latest.values():
            try:
                self.persist_record(record)
                succeeded += 1
            except DatabaseError:
                failed += 1
        for record in errors.values():
            try:
                self.persist_database_error(record)
                succeeded += 1
            except DatabaseError:
                failed += 1
        return succeeded, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="JET3 SQL Server schema management (no printer I/O).")
    parser.add_argument("--migrate", action="store_true", help="apply idempotent project migrations")
    parser.add_argument("--inspect", action="store_true", help="inspect SQL version, permissions, and inkjet objects")
    parser.add_argument("--server", help="explicit SQL host override; otherwise SQL_SERVER in .env is used")
    args = parser.parse_args()
    try:
        settings = load_database_settings()
        repository = SqlRepository(settings, server_override=args.server)
        if args.migrate:
            print("Applied migrations: " + ", ".join(repository.migrate()))
        if args.inspect or not args.migrate:
            info = repository.inspect()
            print(f"Database={info['database']}; SQL Server={info['version']}; SQL 2019={info['sql_server_2019']}")
            print(f"Permissions: sysadmin={info['is_sysadmin']}, create table={info['create_table']}, "
                  f"create view={info['create_view']}, alter schema={info['alter_schema']}")
            print(f"inkjet schema={info['schema_exists']}; tables={info['tables']}; views={info['views']}")
        return 0
    except DatabaseError as exc:
        print(f"Database operation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
