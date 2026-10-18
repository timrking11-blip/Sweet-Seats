# Provider: Ticketmaster Discovery API v2

Status: **planned, disconnected**. The adapter exists and is tested offline against synthetic fixtures. No permission is approved and no live request has been made.

## Access tier

| Product | Access | Sweet Seats use |
| --- | --- | --- |
| Discovery API v2 (events, venues, attractions, classifications) | Open. Free developer key, default quota 5000 calls/day and 5 requests/second | The only Ticketmaster product this adapter calls |
| Partner API (cart, reserve, purchase) | Partner-only | Out of scope |
| Top Picks and Availability | Partner-only | Out of scope; there is no seat or inventory data here |
| Tickets SDK (Ignite) | Needs a Ticketmaster integration rep | Out of scope |

## Terms constraints (developer terms of use)

- Event Content may not be cached beyond reasonable periods needed to provide the service. The registry entry keeps `raw_retention` false, and the adapter discards raw payloads after mapping.
- Ticketmaster's core experience may not be replicated. Sweet Seats links out through the event `url` and does not sell, reserve or check out tickets.
- No revenue may be derived from the content except as the terms allow (for example, affiliate programmes).
- Content must be removed within 24 hours of a Ticketmaster request. Any future persistence path needs a removal runbook before activation.
- `priceRanges` are kept only as optional display metadata (`price_policy: display_only_not_price_history`). They never enter the source event record and are never stored as price history.

Check these against the current terms before activation. They are a summary, not legal review.

## What the adapter does

`services/api/app/ticketmaster.py`

- **Mapping (fixture-first).** `map_event` / `map_event_search` turn `events/{id}` and `events.json` responses into the source event record that `discovery.normalize` accepts:
  - Credits come from `_embedded.attractions`, taken in billing order. The first is the headliner and the rest are support.
  - Venue identity comes from `_embedded.venues[0].id`. Identity is still resolved only through reviewed venue and artist mappings, never by name.
  - `dates.start` is mapped as follows. `starts_at` comes only from Ticketmaster's UTC `dateTime`. It is null when `dateTBA`, `dateTBD`, `timeTBA` or `noSpecificTime` is set, and local times are never re-zoned.
  - `dates.status.code` maps onsale, offsale and rescheduled to `scheduled`, `postponed` to `postponed`, and `cancelled` to `cancelled`. Anything else becomes `unknown`. The raw code is kept in display metadata.
  - The `url` purchase link becomes `ticket_url` and `source_url`.
  - Test events, events without credits or a local date, and malformed events are skipped with a fixed code. The rest of the page still maps.
  - `map_venue(_search)` and `map_attraction(_search)` produce unreviewed identity candidates. Images and external links are dropped.
- **Permission gate.** `collect_events` calls `discovery.permitted(source, "collect", now)`, the Python mirror of `source_use_is_permitted`, before anything else. The enable flag is checked next. Both fail closed with zero requests.
- **Live client.** `TicketmasterClient.from_env()` returns `None` unless `SWEET_SEATS_TICKETMASTER_ENABLED=true` and `TICKETMASTER_API_KEY` are both set.
  - It allows 5 requests per second and stops locally at 5000 requests per UTC day.
  - It reads `Rate-Limit-Available` and `Rate-Limit-Reset`, and refuses requests until the reset time once the quota is spent.
  - It retries 429 and 5xx responses with exponential backoff, honouring `Retry-After` and capping each wait at 30 s.
  - Only allow-listed endpoints and query parameters are accepted.
  - The key goes only into the request query string. It is never logged; debug logs show `apikey=[REDACTED]`. Errors are fixed codes, and transport exceptions are dropped because they can embed the keyed URL.
- **Registry.** `services/api/app/source_registry.py` holds `ticketmaster-discovery` with `access_status: planned`. It marks `collect` and `display` as candidate uses, and every permission use is false.

Offline check (no network):

```bash
cd services/api && python -m app.ticketmaster
```

## Activation needs a separate owner approval

Nothing in this change activates the provider. Activation requires all of the following:

1. Owner approval recorded as a SourcePermission: terms URL and version, evidence, `approved_at`, `expires_at`, and explicit per-use grants. Candidate uses are not grants.
2. `access_status` moved to `approved` or `active` in the canonical `sources` table, not only in the Python registry.
3. A decision on derived retention, and on any raw retention (the current expectation is none), plus a 24-hour removal runbook.
4. Attribution and display review against the terms.
5. `SWEET_SEATS_TICKETMASTER_ENABLED=true` and a server-only `TICKETMASTER_API_KEY` set in the deployment environment. Never commit the key.

Fixtures in `tests/fixtures/ticketmaster/` are hand-written and synthetic. Every artist, venue, ID and URL is invented, and they use reserved `.invalid` domains.
