"""Run with python -m app.worker. One shared worker controls outbound load.

SIGTERM/SIGINT (docker stop) finish the current step and requeue the running job, so a
restart continues it instead of leaving it stuck. A crash is recovered by heartbeat age.
"""

import logging
import signal
import threading
import time
from pathlib import Path
from tempfile import gettempdir

from app.core.config import get_settings
from app.core.logging import configure_logging, log_event
from app.services.collection import run_next
from app.services.maintenance import run_maintenance

HEARTBEAT = Path(gettempdir()) / "relationship-worker.heartbeat"
MAINTENANCE_INTERVAL = 600
logger = logging.getLogger("relationships.worker")


def heartbeat():
    HEARTBEAT.touch()


def main():
    settings = get_settings()
    configure_logging(settings.log_level)
    problems = settings.production_problems()
    if problems:
        for problem in problems:
            log_event(logger, "config.invalid", logging.CRITICAL, problem=problem)
        raise SystemExit("Unsafe production configuration.")
    stop = threading.Event()

    def request_stop(signum, _frame):
        log_event(logger, "worker.stopping", signal=signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    log_event(logger, "worker.started")
    next_maintenance = 0.0
    failures = 0
    while not stop.is_set():
        heartbeat()
        if time.monotonic() >= next_maintenance:
            # Housekeeping failures must never block research jobs.
            next_maintenance = time.monotonic() + MAINTENANCE_INTERVAL
            try:
                run_maintenance()
            except Exception:
                log_event(logger, "maintenance.error", logging.ERROR, exc_info=True)
        try:
            worked = run_next(stop_event=stop, on_heartbeat=heartbeat)
            failures = 0
        except Exception:
            # Usually the database is unavailable; back off instead of spinning.
            failures += 1
            log_event(logger, "worker.error", logging.ERROR, exc_info=True, failures=failures)
            worked = False
        stop.wait(1 if worked else min(30, 2 * 2 ** min(failures, 4)))
    log_event(logger, "worker.stopped")


if __name__ == "__main__":
    main()
