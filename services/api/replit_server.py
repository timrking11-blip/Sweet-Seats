"""Run the original API without changing its contracts or permission decisions."""
import argparse
import os
from datetime import UTC, datetime

import uvicorn

from services.api.app.discovery import DEFAULT_FIXTURE, DEFAULT_STORE, FixtureStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    # Only initialize the original synthetic demo when no store was configured.
    # Never overwrite observations or fall back from a configured database.
    if not os.environ.get("SWEET_SEATS_LOCAL_DATABASE_URL") and not DEFAULT_STORE.exists():
        import json

        FixtureStore().seed(json.loads(DEFAULT_FIXTURE.read_text()), datetime.now(UTC))
    uvicorn.run("services.api.app.main:app", uds=args.socket, access_log=False)


if __name__ == "__main__":
    main()
