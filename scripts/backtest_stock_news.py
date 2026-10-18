"""Run or resume the July-September 2026 stock-news Jev backtest."""

import argparse
import json

from hardware_signal.stock_backtest import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, help="Smoke-test only this many ticker-day cases")
    parser.add_argument("--start", default="2026-07-01")
    parser.add_argument("--end", default="2026-09-30")
    args = parser.parse_args()
    print(json.dumps(run(max_workers=args.workers, limit=args.limit, start=args.start, end=args.end), indent=2))


if __name__ == "__main__":
    main()
