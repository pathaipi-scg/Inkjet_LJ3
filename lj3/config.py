"""Settings from this project's .env only; never searches parent directories."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEYS = {"LJ3_IP", "LJ3_PORT", "LJ3_TIMEOUT_SECONDS"}


@dataclass(frozen=True)
class Settings:
    ip: str = ""
    port: int = 3000
    timeout: float = 3.0

    def validate(self, *, require_ip: bool = True) -> None:
        if self.ip:
            IPv4Address(self.ip)
        elif require_ip:
            raise ValueError("Configure LJ3_IP or enter a printer IPv4 address first.")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("TCP port must be an integer from 1 to 65535.")
        if not math.isfinite(self.timeout) or not 0.1 <= self.timeout <= 60:
            raise ValueError("Timeout must be finite and between 0.1 and 60 seconds.")


def load_settings() -> Settings:
    """Small explicit .env subset: KEY=value, optional matching quotes, comments.

    Ignore all unrelated settings. No interpolation, shell evaluation, export,
    multiline values, inline comments, or environment-variable fallback.
    """
    values: dict[str, str] = {}
    path = PROJECT_ROOT / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in KEYS:
                continue
            if key in values:
                raise ValueError(f"Duplicate {key} in project .env.")
            value = value.strip()
            if value[:1] in ("'", '"'):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError(f"Unclosed quote for {key} in project .env.")
                value = value[1:-1]
            values[key] = value
    try:
        settings = Settings(
            values.get("LJ3_IP", ""),
            int(values.get("LJ3_PORT", "3000")),
            float(values.get("LJ3_TIMEOUT_SECONDS", "3")),
        )
        settings.validate(require_ip=False)
    except ValueError as exc:
        # Do not echo .env values into logs, even on malformed configuration.
        raise ValueError("Invalid LJ3 settings in project .env; check IP, port, and timeout.") from exc
    return settings
