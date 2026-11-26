"""Read-only aggregation of documented JET3 status inquiries."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from .client import LJ3Client
from .protocol import ExternState, PrinterStatus

BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")


TriState = bool | None


@dataclass(frozen=True)
class PrinterSnapshot:
    sampled_at: datetime
    status: PrinterStatus
    extern_state: ExternState
    loaded_job: str

    @property
    def printing(self) -> TriState:
        if self.status.machine_state == 6:
            return True
        if 1 <= self.status.machine_state <= 5:
            return False
        return None

    @property
    def printgo_high(self) -> TriState:
        if self.extern_state.printgo in (0, 1):
            return self.extern_state.printgo == 1
        return None

    @property
    def externtext_ready(self) -> TriState:
        """Only state 4 and no reported error are accepted as write-ready."""
        if self.status.machine_state not in range(1, 7):
            return None
        return self.status.machine_state == 4 and self.status.error == 0

    @property
    def trigger_inhibited(self) -> TriState:
        # ?EX reports live inputs/PrintGo, not whether the line has inhibited triggers.
        return None

    @property
    def act_speed(self) -> Decimal:
        return self.status.act_speed

    @property
    def loaded_job_name(self) -> str:
        # ?JL may append tab-delimited metadata after the loaded path.
        path = self.loaded_job.split("\t", 1)[0].replace("\\\\", "\\").replace("/", "\\")
        return path.rsplit("\\", 1)[-1]

    def has_loaded_job(self, expected_name: str) -> bool:
        return self.loaded_job_name.casefold() == expected_name.casefold()

    def blockers(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.externtext_ready is not True:
            reasons.append("printer is not documented Ready for Action with error 0")
        if self.printgo_high is not False:
            reasons.append("PrintGo signal is high or unknown")
        if self.printing is not False:
            reasons.append("printer is reporting printing or its printing state is unknown")
        return tuple(reasons)


def read_printer_snapshot(client: LJ3Client) -> PrinterSnapshot:
    """Query ?RS, ?EX, and ?JL sequentially on the client's current TCP session."""
    client.connect()
    status = client.get_printer_status()
    extern_state = client.get_extern_state()
    loaded_job = client.get_loaded_job()
    return PrinterSnapshot(datetime.now(BANGKOK), status,
                           extern_state, loaded_job)
