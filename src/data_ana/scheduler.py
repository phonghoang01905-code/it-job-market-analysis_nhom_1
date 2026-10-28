from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from data_ana.pipeline import add_arguments, execute


def next_run(now: datetime, at: str, zone: ZoneInfo) -> datetime:
    clock = datetime.strptime(at, "%H:%M").time()
    local = now.astimezone(zone)
    target = local.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
    return target if target > local else target + timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description="Chạy pipeline một lần/ngày khi máy đang bật")
    parser.add_argument("--at", default="07:15", help="Giờ địa phương HH:MM")
    parser.add_argument("--timezone", default="Asia/Ho_Chi_Minh")
    parser.add_argument("--once", action="store_true", help="Chạy ngay một lần, không chờ lịch")
    add_arguments(parser)
    args = parser.parse_args()
    zone = ZoneInfo(args.timezone)
    try:
        datetime.strptime(args.at, "%H:%M")
    except ValueError:
        parser.error("--at phải theo HH:MM, ví dụ 07:15")
    if args.once:
        raise SystemExit(execute(args))
    try:
        while True:
            target = next_run(datetime.now(zone), args.at, zone)
            print(f"Lần chạy tiếp theo: {target.isoformat()}", flush=True)
            while (remaining := (target - datetime.now(zone)).total_seconds()) > 0:
                time.sleep(min(remaining, 30))
            execute(args)
            logging.getLogger(__name__).info("Scheduler tiếp tục chờ ngày tiếp theo")
    except KeyboardInterrupt:
        print("Đã dừng scheduler")


if __name__ == "__main__":
    main()
