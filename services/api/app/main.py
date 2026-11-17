from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field, HttpUrl

from .discovery import DiscoveryError
from .discovery_postgres import DiscoveryStore, configured_store
from .me import router as me_router
from .waitlist import router as waitlist_router
from .webhooks import router as webhooks_router

app = FastAPI(
    title="Sweet Seats API",
    version="0.1.0",
    description="Server-side contracts for provenance-first concert discovery.",
)


@app.middleware("http")
async def discovery_cache_policy(request: Request, call_next):
    """Permission decisions are current reads, never reusable cached responses.

    Cover handled errors as well as successes so an earlier allowed response or
    a temporary denial cannot become a cached substitute for the next check.
    """
    response = await call_next(request)
    path = request.url.path
    # Signed-in responses are per user and must never be shared by a cache either.
    if path in {"/v1/events", "/v1/me", "/v1/waitlist"} or path.startswith(
        ("/v1/events/", "/v1/me/", "/v1/waitlist/")
    ):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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


def discovery_store() -> DiscoveryStore:
    try:
        return configured_store()
    except DiscoveryError:
        raise HTTPException(status_code=503, detail="Local discovery data unavailable.") from None


def discovery_now() -> datetime:
    return datetime.now(UTC)


def _read_feed(store: DiscoveryStore, now: datetime) -> dict:
    try:
        return store.feed(now)
    except (DiscoveryError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Local discovery data unavailable. Seed the synthetic fixture.",
        ) from None


@app.get("/v1/events")
def events(store: DiscoveryStore = Depends(discovery_store), now: datetime = Depends(discovery_now),
           limit: Annotated[int, Query(ge=1, le=100)] = 100,
           offset: Annotated[int, Query(ge=0)] = 0):
    feed = _read_feed(store, now)
    total = len(feed["events"])
    return {**feed, "events": feed["events"][offset:offset + limit],
            "pagination": {"limit": limit, "offset": offset, "total": total,
                           "next_offset": offset + limit if offset + limit < total else None}}


@app.get("/v1/events/{event_id}")
def event_detail(event_id: UUID, store: DiscoveryStore = Depends(discovery_store),
                 now: datetime = Depends(discovery_now)):
    feed = _read_feed(store, now)
    event = next((e for e in feed["events"] if e["event_id"] == str(event_id)), None)
    if event is None:
        raise HTTPException(status_code=404, detail="Event unavailable or not permitted for display.")
    return {"mode": feed["mode"], "generated_at": feed["generated_at"], "event": event}


app.include_router(me_router)
app.include_router(waitlist_router)
app.include_router(webhooks_router)
