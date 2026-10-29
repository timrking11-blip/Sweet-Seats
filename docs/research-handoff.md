# External research handoff (GrokBot → Claude → owner)

Status: proposed working agreement, 2026-10-29. It applies
[SS-RESEARCH-0.3 §7](contracts/research-v0.3.md#7-manually-launched-tools): independent
manual research stays outside the research runner and enters the project only as an
explicitly reviewed external contribution. It adds no runtime provider, scheduler or
platform. Grok is used manually and is not a Sweet Seats integration.

## Roles

| Role | Does | Does not |
|---|---|---|
| GrokBot (manual) | Research, competitor monitoring, provider discovery, evidence gathering, proposed opportunities | Create canonical artists or events, ticket observations, features, permission grants or approved decisions |
| Claude (repository) | Verifies the findings a selected task depends on against primary sources; reconciles them with Notion decisions; implements, tests, prepares review evidence | Approve decisions, grant source rights, merge, deploy, activate or spend |
| Owner | Approves product and source decisions, spending, activation and release | — |

Verifying a research claim (it is true) is separate from approving the source use it
describes (we may do it).

## Export record

A GrokBot export enters the repository only as a reviewed record. It reuses the
SS-RESEARCH-0.2 §5 claim and evidence fields:

| Field | Meaning |
|---|---|
| `researcher` | `grokbot` plus the model or product name shown |
| `report_url`, `report_date` | The original page and date |
| `report_version` | Version label, or SHA-256 of the exported text |
| `claims[]` | Stable ID, text, kind (`fact` / `inference` / `recommendation` / `unknown`) |
| `claims[].evidence[]` | Cited primary-source URL, retrieval date, passage, and the date Claude re-verified it |
| `claims[].status` | `verified`, `contradicted`, `unverified`, `stale`, or `conflict` with a note |
| `claims[].class` | One of the classes below |
| `sensitivity`, `source_rights` | What the report may be shared with; the rights status of each cited source |
| `proposed_task` | A suggested decision or implementation task, if any |

Store exports under `docs/research/` only after review. Raw exports may contain
third-party text. Keep quotations short, and keep no payloads from licensed sources.

## Classification

Each substantive finding is classed as **already implemented**, **supported and relevant
to the next increment**, **needs primary-source verification**, **needs an owner
decision**, **deferred by phase**, or **unsupported, contradicted or stale**.

## Disclosure rules

Do not paste private source code, contracts, credentials, notification endpoints, user
records or licensed payloads into GrokBot without authorization for that specific
disclosure (the SS-RESEARCH-0.2 rule against sending secrets, private records or
licensed samples to research providers applies). Public URLs and public questions are fine.

## Review of the brief supplied on 2026-10-29

`https://sweet-seats-deep-dive-initial-knowledge-qfl2.pages.grok.bot/` redirected to a
Grok/X account sign-in (`accounts.x.ai`) in the built-in browser. **No section could be
inspected.** Claude did not sign in on the owner's behalf. No GrokBot finding is
classified here, and none is treated as accepted, deferred or rejected. To proceed,
export the brief (text or PDF) into the session, or open it while signed in so it can be
read. The claims this branch relies on (MusicBrainz licensing and rate limits) were
verified directly against primary sources instead ([MetaBrainz
readiness](metabrainz-readiness.md)).
