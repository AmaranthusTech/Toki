from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import platform


@dataclass(frozen=True)
class DoctorIssue:
    code: str
    message: str


@dataclass
class DoctorReport:
    ok: bool
    python_version: str
    ephemeris_path: str | None
    ephemeris_exists: bool
    issues: list[DoctorIssue] = field(default_factory=list)


def resolve_ephemeris_path(ephemeris_path: str | None) -> Path | None:
    if ephemeris_path:
        return Path(ephemeris_path).resolve()

    env_path = os.getenv("SHINTOKI_EPHEMERIS_PATH")
    if env_path:
        return Path(env_path).resolve()

    cwd = Path.cwd()
    for rel in ("data/de440s.bsp", "data/de421.bsp"):
        candidate = (cwd / rel).resolve()
        if candidate.exists():
            return candidate

    return None


def run_doctor(ephemeris_path: str | None) -> DoctorReport:
    issues: list[DoctorIssue] = []
    resolved = resolve_ephemeris_path(ephemeris_path)

    if resolved is None:
        issues.append(
            DoctorIssue(
                code="missing_ephemeris_path",
                message="ephemeris path is required. set --ephemeris-path or SHINTOKI_EPHEMERIS_PATH.",
            )
        )
        return DoctorReport(
            ok=False,
            python_version=platform.python_version(),
            ephemeris_path=None,
            ephemeris_exists=False,
            issues=issues,
        )

    exists = resolved.exists()
    if not exists:
        issues.append(
            DoctorIssue(
                code="ephemeris_not_found",
                message=f"ephemeris file does not exist: {resolved}",
            )
        )

    return DoctorReport(
        ok=len(issues) == 0,
        python_version=platform.python_version(),
        ephemeris_path=str(resolved),
        ephemeris_exists=exists,
        issues=issues,
    )
