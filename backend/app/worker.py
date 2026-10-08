"""Ingest worker entrypoint (placeholder).

Real adapters (Google News RSS, GDELT, X provider) register here once
implemented; until then this loop only keeps the container alive and logs
the configured interval.
"""

import logging
import time

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")


def main() -> None:
    interval_s = max(1, settings.ingest_interval_min) * 60
    log.info(
        "ingest worker started (interval=%s min); no source adapters registered yet",
        settings.ingest_interval_min,
    )
    while True:
        time.sleep(interval_s)
        log.info("ingest tick (no adapters registered yet)")


if __name__ == "__main__":
    main()
