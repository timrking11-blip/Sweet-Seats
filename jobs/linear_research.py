"""Offline hourly selection demonstration. No provider calls, queue or publication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jobs.research_contracts import select_hourly, timestamp


async def process_job(*args, **kwargs):
    raise RuntimeError("SS-RESEARCH-0.2: live execution/writeback deferred; use offline plan")


async def sweep(*args, **kwargs):
    raise RuntimeError("SS-RESEARCH-0.2: live Linear sweep deferred pending activation gates")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    plan = select_hourly(fixture["candidates"], fixture["approvals"], set(fixture["completed"]),
                         fixture["policy"], timestamp(fixture["now"]))
    print(json.dumps({"synthetic": True, "network_calls": 0, "planned": plan}, indent=2))


if __name__ == "__main__":
    main()
