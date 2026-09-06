#!/usr/bin/env python3
"""
Disneyland Wait Time Tracker
-----------------------------
Polls the free Queue-Times.com API for Disneyland (Anaheim) ride wait times
and appends each reading to a CSV file, building a history over time.

Data source: https://queue-times.com/parks/16/queue_times.json
Powered by Queue-Times.com (https://queue-times.com/en-US) - please keep
that attribution if you build anything public with this data.

USAGE
-----
One-shot (good for cron / Task Scheduler, run every 30-60 min):
    python disneyland_wait_tracker.py --once

Continuous loop (keeps running, polls on an interval):
    python disneyland_wait_tracker.py --interval 1800

Change PARK_ID to 17 for Disney California Adventure, or track both by
running the script twice with different --park-id / --outfile values.
"""

import argparse
import csv
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

DISNEYLAND_PARK_ID = 16          # Disney California Adventure = 17
API_URL = "https://queue-times.com/parks/{park_id}/queue_times.json"
DEFAULT_OUTFILE = "disneyland_wait_times.csv"
PARK_TZ = ZoneInfo("America/Los_Angeles")
CSV_HEADERS = [
    "collected_at_utc",
    "land",
    "ride",
    "wait_minutes",
    "is_open",
    "last_updated",
]


def within_operating_window(start_hour: int, end_hour: int) -> bool:
    """True if it's currently between start_hour and end_hour, Pacific time.

    Uses zoneinfo so this stays correct across daylight saving changes
    without needing the cron schedule itself to change.
    """
    now_pt = datetime.now(PARK_TZ)
    return start_hour <= now_pt.hour < end_hour


def fetch_wait_times(park_id: int) -> list[dict]:
    """Hit the API and flatten the nested lands -> rides structure into rows."""
    resp = requests.get(API_URL.format(park_id=park_id), timeout=15)
    resp.raise_for_status()
    data = resp.json()

    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []

    # Most parks return {"lands": [...]}; some flat parks return {"rides": [...]}
    lands = data.get("lands", [])
    if lands:
        for land in lands:
            for ride in land.get("rides", []):
                rows.append(_ride_row(collected_at, land.get("name", ""), ride))
    for ride in data.get("rides", []):
        rows.append(_ride_row(collected_at, "", ride))

    return rows


def _ride_row(collected_at: str, land_name: str, ride: dict) -> dict:
    return {
        "collected_at_utc": collected_at,
        "land": land_name,
        "ride": ride.get("name"),
        "wait_minutes": ride.get("wait_time"),
        "is_open": ride.get("is_open"),
        "last_updated": ride.get("last_updated"),
    }


def append_to_csv(rows: list[dict], outfile: str) -> None:
    file_exists = os.path.isfile(outfile)
    with open(outfile, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def poll_once(park_id: int, outfile: str) -> None:
    rows = fetch_wait_times(park_id)
    append_to_csv(rows, outfile)
    print(f"[{datetime.now().isoformat(timespec='seconds')}] "
          f"Logged {len(rows)} rides to {outfile}")


def main():
    parser = argparse.ArgumentParser(description="Track Disneyland ride wait times over time.")
    parser.add_argument("--park-id", type=int, default=DISNEYLAND_PARK_ID,
                         help="Queue-Times park ID (default: 16 = Disneyland Anaheim)")
    parser.add_argument("--outfile", default=DEFAULT_OUTFILE,
                         help="CSV file to append readings to")
    parser.add_argument("--once", action="store_true",
                         help="Poll a single time and exit (use with cron/Task Scheduler)")
    parser.add_argument("--interval", type=int, default=1800,
                         help="Seconds between polls when running continuously (default 1800 = 30 min)")
    parser.add_argument("--start-hour", type=int, default=8,
                         help="Only log at/after this hour, Pacific time, 24h format (default 8 = 8am)")
    parser.add_argument("--end-hour", type=int, default=22,
                         help="Stop logging at this hour, Pacific time, 24h format (default 22 = 10pm)")
    parser.add_argument("--ignore-window", action="store_true",
                         help="Log regardless of time of day (ignores --start-hour/--end-hour)")
    args = parser.parse_args()

    def in_window() -> bool:
        return args.ignore_window or within_operating_window(args.start_hour, args.end_hour)

    if args.once:
        if in_window():
            poll_once(args.park_id, args.outfile)
        else:
            print(f"[{datetime.now(PARK_TZ).isoformat(timespec='seconds')}] "
                  f"Outside {args.start_hour}:00-{args.end_hour}:00 PT window, skipping.")
        return

    print(f"Polling park {args.park_id} every {args.interval} seconds "
          f"between {args.start_hour}:00-{args.end_hour}:00 PT. Ctrl+C to stop.")
    while True:
        try:
            if in_window():
                poll_once(args.park_id, args.outfile)
            else:
                print(f"[{datetime.now(PARK_TZ).isoformat(timespec='seconds')}] Outside window, skipping.")
        except requests.RequestException as e:
            print(f"Request failed: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
