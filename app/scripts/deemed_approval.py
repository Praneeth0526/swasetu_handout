# -*- coding: utf-8 -*-
"""
Nightly deemed-approval job.

Under the Purvanchal Right to Public Services Act, an application not processed
within the statutory SLA stands approved. This job marks such applications
DEEMED_APPROVED and notifies the applicant by SMS.

Scheduled via cron, 02:00 daily. See deploy/crontab.
"""

import os
import sys
import logging
import configparser
from datetime import datetime, timedelta

import psycopg2
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load configuration - support consolidated app.ini with fallback
config = configparser.ConfigParser()
CONFIG_PATHS = [
    os.path.join(BASE_DIR, "config", "app.ini"),
    os.path.join(BASE_DIR, "config", "settings.ini"),
]

config_loaded = False
for path in CONFIG_PATHS:
    if os.path.exists(path):
        with open(path) as fh:
            config.read_file(fh)
        config_loaded = True
        break

if not config_loaded:
    # Default fallback values matching environment defaults
    if not config.has_section("database"):
        config.add_section("database")
    if not config.has_section("app"):
        config.add_section("app")
    if not config.has_section("pension"):
        config.add_section("pension")

DB_HOST = os.environ.get("DB_HOST", config.get("database", "host", fallback="db"))
DB_PORT = int(os.environ.get("DB_PORT", config.get("database", "port", fallback="5432")))
DB_NAME = os.environ.get("DB_NAME", config.get("database", "name", fallback="sewasetu"))
DB_USER = os.environ.get("DB_USER", config.get("database", "user", fallback="sewasetu"))
DB_PASS = os.environ.get("DB_PASSWORD", config.get("database", "password", fallback="sewasetu123"))

SLA_DAYS = int(os.environ.get("SLA_DAYS", config.get("pension", "sla_days", fallback="15")))
SMS_GATEWAY_URL = os.environ.get("SMS_GATEWAY_URL", config.get("app", "sms_gateway_url", fallback="http://smsgw:8025"))


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def process_deemed_approvals(conn=None):
    """
    Process all applications exceeding SLA_DAYS in PENDING status.
    Returns (approved_count, approved_list).
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        cur = conn.cursor()
        now = datetime.now()
        cutoff = now - timedelta(days=SLA_DAYS)
        cur.execute(
            """UPDATE applications
               SET status = 'DEEMED_APPROVED', decided_at = %s, decided_by = 'RTPS-AUTO'
               WHERE status = 'PENDING' AND submitted_at < %s
               RETURNING application_no, mobile""",
            (now, cutoff))
        rows = cur.fetchall()
        conn.commit()

        for app_no, mobile in rows:
            try:
                requests.post(SMS_GATEWAY_URL + "/api/send", json={
                    "to": mobile,
                    "text": "Sewa Setu: your pension application %s stands approved "
                            "under the RTPS Act." % app_no}, timeout=5)
            except Exception as e:
                logging.warning(f"Failed to send SMS to {mobile}: {e}")

        log_msg = "%s deemed approval: %d applications approved" % (
            now.strftime("%Y-%m-%d %H:%M:%S"), len(rows))
        print(log_msg)
        cur.close()
        return len(rows), [r[0] for r in rows]
    finally:
        if should_close:
            conn.close()


def main():
    count, _ = process_deemed_approvals()
    return count


if __name__ == "__main__":
    sys.exit(main())
