from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from .discovery import DiscoveryError, FixtureStore

app = FastAPI(
    title="Sweet Seats API",
    version="0.1.0",
    description="Server-side contracts for provenance-first concert discovery.",
)


class SourceContext(BaseModel):
    source_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    source_url: HttpUrl
    observed_at: datetime
    adapter_version: str
    permission_id: str


class NormalizedEventRecord(BaseModel):
    """A source record, not a canonical event.

    Reconciliation assigns the Sweet Seats event UUID only after identity checks.
    """

    source: SourceContext
    vendor_event_id: str
    title: str
    local_date: date
    timezone: str = "America/New_York"
    starts_at: datetime | None = None
    status: Literal["scheduled", "rescheduled", "postponed", "cancelled", "unknown"] = "unknown"
    artist_names: list[str] = []
    venue_name: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sweet-seats-api"}


@app.get("/v1/discovery/mode")
def discovery_mode() -> dict[str, str]:
    return {
        "mode": "synthetic",
        "notice": "No live provider is active until its SourcePermission gate passes.",
    }


def discovery_store() -> FixtureStore:
    return FixtureStore()


def discovery_now() -> datetime:
    return datetime.now(UTC)


def _read_feed(store: FixtureStore, now: datetime) -> dict:
    try:
        return store.feed(now)
    except (DiscoveryError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Local discovery data unavailable. Seed the synthetic fixture.",
        ) from None


@app.get("/v1/events")
def events(store: FixtureStore = Depends(discovery_store), now: datetime = Depends(discovery_now),
           limit: Annotated[int, Query(ge=1, le=100)] = 100,
           offset: Annotated[int, Query(ge=0)] = 0):
    feed = _read_feed(store, now)
    total = len(feed["events"])
    return {**feed, "events": feed["events"][offset:offset + limit],
            "pagination": {"limit": limit, "offset": offset, "total": total,
                           "next_offset": offset + limit if offset + limit < total else None}}


@app.get("/v1/events/{event_id}")
def event_detail(event_id: UUID, store: FixtureStore = Depends(discovery_store),
                 now: datetime = Depends(discovery_now)):
    feed = _read_feed(store, now)
    event = next((e for e in feed["events"] if e["event_id"] == str(event_id)), None)
    if event is None:
        raise HTTPException(status_code=404, detail="Event unavailable or not permitted for display.")
    return {"mode": feed["mode"], "generated_at": feed["generated_at"], "event": event}


