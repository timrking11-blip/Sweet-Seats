# User API v0.1: signed-in workflows

Status: **proposed; built and tested locally; not deployed.** No Notion decision covers
it yet ([gap register](../phase-assessment.md) G-04, G-05). Traces to SS-ADR-001 ("user-
scoped access policies protect preferences and outcomes") and SS-DATA-0.1 User,
ArtistFollow, NotificationSubscription.

## Identity

- The client sends a Supabase Auth access token: `Authorization: Bearer <token>`.
- `app/auth.py` verifies it on the server: HS256 only (the token cannot choose
  `none` or another algorithm, and `crit` is refused), signature, `exp` (exclusive, no
  leeway), `nbf` and `iat` (30 s skew), issuer, audience `authenticated`, role
  `authenticated`, not anonymous, and a canonical UUID `sub`.
- Every rejection answers `401 Sign-in required.` with
  `WWW-Authenticate: Bearer error="invalid_token"`. The client learns nothing about
  which check failed. Missing configuration answers `503`; it never guesses.
- Server-only configuration: `SWEET_SEATS_SUPABASE_JWT_SECRET` (at least 32 characters)
  and `SWEET_SEATS_SUPABASE_ISSUER` (`https://<project>.supabase.co/auth/v1`).
- Asymmetric signing keys (JWKS) are not supported yet. They need a reviewed crypto
  dependency (owner decision).

## Ownership

`app/me.py` runs each request in one transaction as the `authenticated` role, with only
`{"sub", "role"}` from the verified token as `request.jwt.claims`. No query filters by
`user_id`: row-level security decides, so another account's row is simply absent (404).
Request bodies forbid unknown fields, so a client cannot name a `user_id`.
`test_isolation_comes_from_row_level_security_not_api_filters` removes the role switch
and shows the same code then leaks every account. The isolation tests therefore prove RLS
enforcement, not API filtering.

Deployment needs a database login that may `SET ROLE authenticated` (like Supabase's
`authenticator`), never the service role. This increment accepts loopback databases only.

## Endpoints

| Method and path | Effect |
|---|---|
| `GET /v1/me` | Own profile, follows and subscriptions. Endpoint references are never returned. |
| `PUT /v1/me/profile` | Create or update locale and IANA time zone. `409` if Supabase Auth does not know the subject. |
| `PUT /v1/me/follows/{artist_id}` | Follow (idempotent). `404` unknown artist; `409` no profile. |
| `DELETE /v1/me/follows/{artist_id}` | Unfollow (disables the follow). Queued alerts for it are suppressed before any send (`not_following`). |
| `POST /v1/me/subscriptions/{id}/revoke` | Withdraw consent. One way and idempotent; the database stamps the time. Pending deliveries are suppressed (`no_current_consent`). |
| `POST /v1/me/deletion-request` | `202`, creating the profile row if needed (`409` if Supabase Auth does not know the subject). Planning, sending and outcome recording stop at once; follows and the profile can no longer be changed (`409`). The user cannot withdraw it; the purge waits for the retention decision. |

All `/v1/me` responses are `Cache-Control: private, no-store`.

## Database rules (`20261029100000_user_consent_integrity.sql`)

- `notification_subscriptions`: signed-in users may only update `revoked_at`. No insert,
  delete or other column, because creating a subscription needs a verified endpoint and a
  consent version (a server flow; the vendor is an owner decision). A user revocation is
  stamped `now()` and cannot be changed or reversed.
- `user_profiles`: user-set `outcome_consent_at` and `deletion_requested_at` are stamped
  `now()`, and a new outcome consent version re-stamps the time. Users cannot delete the
  row (that would cascade away consent and delivery evidence and drop the deletion
  request); erasure is a server purge. After a deletion request the profile and follows
  are read-only for the user, and the request cannot be withdrawn.
- `anon` and `authenticated` lose `TRUNCATE`, `TRIGGER` and `REFERENCES` on user and
  outbox tables (TRUNCATE ignores RLS).
- Still open: consent versions are client-chosen strings with no history (G-15); any
  unexpired token can request deletion, with no recent-sign-in or session-revocation
  check (G-16); users can read their own `endpoint_ref` through the Data API.
- Service-role workers are unaffected. The SQL tests and nine negative controls pin each rule.

## Not included

Subscription creation and endpoint verification; outcome recording endpoints; a purge
job; data export; a web UI for these flows; rate limiting of the API itself; access-log
redaction (follow paths reveal music taste).
