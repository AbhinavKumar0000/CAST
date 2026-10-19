"""UTC-day HTTP request budget enforcement (PROTOCOL 8.12).

Boundary: UTC calendar day (reset at 00:00:00Z). The counter is persisted to
``eval/runs/_http_budget.json`` so every process/run on the same UTC day shares a
single count. The provider calls :meth:`DailyBudget.reserve` immediately before
every HTTP attempt (including retries), and raises :class:`BudgetExceeded` when the
next request would exceed ``cost_control.daily_request_budget``. Runners are
expected to catch this, stop cleanly, and resume after the reset - never to record
it as a model error.

Note: pre-instrumentation counts (before 2026-10-14) were estimates; the file is
seeded once with the recorded 2026-10-13 usage so today's ceiling is honoured.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "runs" / "_http_budget.json"


class BudgetExceeded(RuntimeError):
    """Raised when the UTC-day HTTP request budget is exhausted."""


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class DailyBudget:
    """UTC-day HTTP request budget, enforced PER ACCOUNT (API key).

    Each API key belongs to a separate NVIDIA account with its own ``limit`` requests/UTC-day,
    so the counter is a dict keyed by account id. ``count`` remains the sum across accounts so
    existing callers/status displays keep working.
    """

    def __init__(self, limit: int, path: Path | str = DEFAULT_PATH) -> None:
        self.limit = int(limit)
        self.path = Path(path)

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _counts_for(data: dict, today: str) -> dict:
        if data.get("date") != today:
            return {}
        counts = dict(data.get("counts") or {})
        if not counts and data.get("count"):  # migrate legacy single-counter file
            counts["legacy"] = int(data["count"])
        return {str(k): int(v) for k, v in counts.items()}

    def register_accounts(self, n: int) -> None:
        """Record how many API-key accounts share this budget (for status reporting).

        Migrates a legacy single-counter file by spreading its total evenly across the
        accounts (requests were round-robined, so this is the best estimate).
        """
        today = utc_today()
        n = max(1, int(n))
        with _LOCK:
            data = self._read()
            if data.get("date") != today:
                data = {"date": today, "counts": {}, "count": 0}
            counts = dict(data.get("counts") or {})
            if not counts and data.get("count"):
                legacy = int(data["count"])
                per, rem = divmod(legacy, n)
                counts = {str(i): per for i in range(n)}
                if rem:
                    counts["0"] = counts.get("0", 0) + rem
            data["counts"] = counts
            data["count"] = sum(counts.values())
            data["num_accounts"] = n
            data["limit_per_account"] = self.limit
            self._write(data)

    def status(self) -> dict:
        today = utc_today()
        with _LOCK:
            data = self._read()
        counts = self._counts_for(data, today)
        total = sum(counts.values())
        n_accounts = int(data.get("num_accounts") or 0) or max(1, len(counts))
        capacity = self.limit * n_accounts
        return {"utc_date": today, "count": total, "limit": self.limit,
                "num_accounts": n_accounts, "capacity": capacity,
                "accounts": counts, "remaining": max(0, capacity - total)}

    def reserve(self, n: int = 1, account=None) -> int:
        """Reserve ``n`` HTTP requests for ``account`` on the current UTC day.

        Raises :class:`BudgetExceeded` if ``account`` would cross its per-day limit.
        """
        today = utc_today()
        acct = "default" if account is None else str(account)
        with _LOCK:
            data = self._read()
            if data.get("date") != today:
                data = {"date": today, "counts": {}, "count": 0}
            counts = dict(data.get("counts") or {})
            if not counts and data.get("count"):
                counts["legacy"] = int(data["count"])
            c = int(counts.get(acct, 0))
            if c + n > self.limit:
                raise BudgetExceeded(
                    f"UTC-day HTTP budget exhausted for account '{acct}': {c}/{self.limit} used "
                    f"on {today}. Resets at 00:00:00Z. Stopping cleanly - re-run the same command "
                    f"after the reset to resume (results are resumable, nothing recorded as error)."
                )
            counts[acct] = c + n
            data["counts"] = counts
            data["count"] = sum(counts.values())
            self._write(data)
            return counts[acct]


def seed(day: str, count: int, path: Path | str = DEFAULT_PATH) -> None:
    """One-time seed of the counter for ``day`` (pre-instrumentation estimate)."""
    p = Path(path)
    with _LOCK:
        if p.exists():
            try:
                existing = json.loads(p.read_text(encoding="utf-8"))
                if existing.get("date") == day:
                    return
            except json.JSONDecodeError:
                pass
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"date": day, "count": int(count), "seeded": True}, indent=2),
                     encoding="utf-8")
