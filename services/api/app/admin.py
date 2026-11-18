"""Internal, read-only pilot report for the owner (Build Plan Step 6; proposed).

GET /v1/admin/pilot returns the latest weekly pilot_metrics rows. Only signed-in users
whose ids are listed in SWEET_SEATS_ADMIN_USER_IDS (comma-separated UUIDs) may read it;
everyone else, and everyone when the list is unset, gets the same 404 as an unknown
route, so the endpoint does not advertise itself.
"""
from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import Identity
from .discovery_postgres import PostgresStore
from .me import current_user, user_store

router = APIRouter(prefix="/v1/admin", tags=["admin"])
ADMIN_ENV = "SWEET_SEATS_ADMIN_USER_IDS"


def admin_ids() -> set[UUID]:
    ids = set()
    for part in os.environ.get(ADMIN_ENV, "").split(","):
        try:
            ids.add(UUID(part.strip()))
        except ValueError:
            continue  # A malformed entry grants nothing.
    return ids


def require_admin(user: Annotated[Identity, Depends(current_user)]) -> Identity:
    if user.user_id not in admin_ids():
        raise HTTPException(status_code=404, detail="Not Found")
    return user


@router.get("/pilot")
def pilot_report(_: Annotated[Identity, Depends(require_admin)],
                 store: Annotated[PostgresStore, Depends(user_store)],
                 weeks: Annotated[int, Query(ge=1, le=26)] = 8) -> dict:
    with store._connect() as conn:
        rows = conn.execute(
            """SELECT period_start, period_end, metrics_version, computed_at, metrics
               FROM pilot_metrics ORDER BY period_start DESC, metrics_version DESC LIMIT %s""",
            (weeks,)).fetchall()
    return {"weeks": rows}
