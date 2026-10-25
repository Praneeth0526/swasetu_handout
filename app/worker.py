# -*- coding: utf-8 -*-
"""
Sewa Setu Background Worker
Handles asynchronous background tasks, statutory RTPS deemed approval processing,
and periodic health heartbeats.
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime

# Add app directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from app.scripts.deemed_approval import process_deemed_approvals
except ImportError:
    from scripts.deemed_approval import process_deemed_approvals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s"
)
logger = logging.getLogger("worker")


class SewaSetuWorker:
    def __init__(self, interval_seconds=3600):
        self.interval = interval_seconds
        self.running = False

    def run_rtps_deemed_approval(self):
        """Execute the RTPS deemed approval job and log results."""
        logger.info("Executing statutory RTPS deemed approval sweep...")
        try:
            count, app_nos = process_deemed_approvals()
            logger.info("RTPS deemed approval sweep completed: %d applications processed." % count)
            if app_nos:
                logger.info("Processed application numbers: %s" % (", ".join(app_nos[:10]) + ("..." if len(app_nos) > 10 else "")))
            return count, app_nos
        except Exception as e:
            logger.error("Error executing RTPS deemed approval: %s" % e, exc_info=True)
            return 0, []

    def start(self):
        """Continuous execution loop."""
        self.running = True
        logger.info("Sewa Setu Worker started (Interval: %ds)" % self.interval)
        while self.running:
            self.run_rtps_deemed_approval()
            logger.info("Worker sleeping for %ds until next sweep..." % self.interval)
            try:
                time.sleep(self.interval)
            except KeyboardInterrupt:
                logger.info("Worker received shutdown signal. Exiting.")
                self.running = False
                break


def main():
    parser = argparse.ArgumentParser(description="Sewa Setu Background Worker")
    parser.add_argument("--run-once", action="store_true", help="Run pending tasks once and exit")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("WORKER_INTERVAL", 3600)),
                        help="Interval in seconds between task runs (default: 3600)")
    args = parser.parse_args()

    worker = SewaSetuWorker(interval_seconds=args.interval)
    if args.run_once:
        count, _ = worker.run_rtps_deemed_approval()
        sys.exit(0 if count >= 0 else 1)
    else:
        worker.start()


if __name__ == "__main__":
    main()
