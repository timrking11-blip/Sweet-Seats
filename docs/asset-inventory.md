# Asset inventory

Status: engineering inventory, 2026-10-29. **Not legal advice and not a licence
decision.** It keeps six questions apart: who authored an asset, what permits its use,
whether it is confidential, whether it is exclusive, whether it differentiates the
product, and how mature it is. Answering one does not answer another.

Session observations (2026-10-29, not stored in the repository): `gh repo view`
reported the repository **private** with **no licence**; `git log origin/main` showed
commits by the owner's accounts, many co-authored by Claude, and six authored by
`copilot-swe-agent[bot]`. The README says not to publish a licence until the owner
decides.

Qualifications:
- A private repository is confidential while access stays restricted. It does not prove
  exclusive ownership.
- AI-assisted authorship may limit copyright protection in some jurisdictions. Treat
  protectability as an open legal question; this document does not answer it.
- An AI research report establishes neither originality nor source rights.
- A permitted derivative of a provider record keeps that provider's conditions.
- User data is held under consent and privacy duties. It is not unrestricted company
  property.
- Public metadata access and generic agent orchestration are not a moat.

| Asset / path | Origin | Rights basis | Confidentiality | State | Possible differentiation | Evidence gap |
|---|---|---|---|---|---|---|
| Reconciliation and identity rules: `services/api/app/discovery.py`, `discovery_postgres.py`, foundation and discovery migrations | Owner repo; AI-assisted | Owner's work product; protectability open | Private repo | Existing; fixtures only | Fewer wrong merges and splits than a single-source baseline | No error-rate benchmark; G-12 cases missing |
| Curated venue/artist crosswalks and correction history | Not yet created (synthetic crosswalks only) | Owner-curated mappings; underlying identifiers keep their source terms (MBID CC0, Ticketmaster IDs under Ticketmaster terms) | Would be private | Proposed | Accumulated review decisions are the most plausible durable asset | None collected |
| Event-change and alert rules: `services/api/app/alerts.py` | Owner repo; AI-assisted | Owner's work product | Private | Existing (log transport) | More relevant, fewer obsolete alerts | Pilot alert-quality measures |
| Rights enforcement: `source_permissions`, `source_use_is_permitted`, run ledger, SQL tests, negative controls | Owner repo; AI-assisted | Owner's work product | Private | Existing, CI-tested | Trust and compliance; not a moat by itself | — |
| API and PWA workflows: `services/api/app/main.py`, `me.py`, `apps/web` | Owner repo; AI-assisted; on Next.js, React, FastAPI | Own code over open-source frameworks under their licences | Private | Local only | Generic | Usability evidence |
| Synthetic fixtures and test suites: `tests/fixtures/discovery`, `services/api/tests`, `supabase/tests` | Owner repo; invented names (not verified against real acts) | Owner's work product | Private | Existing | Evaluation discipline | Real-panel benchmark |
| Research contracts: `docs/contracts/research-v0.*`, `jobs/`, `adapters/` | Owner repo | Owner's work product | Private | Existing, disabled | Process | — |
| Claude Code agent prompts: `.claude/agents/*` | **Adapted** from VoltAgent/awesome-claude-code-subagents | MIT licence; notice kept in `docs/agents.md` and each file | Private copy of public material | Existing | None (public templates) | Keep notices |
| Third-party dependencies: `services/api/requirements-*.lock`, `apps/web/package-lock.json` | Third parties | Each package's own licence | Public | Existing | None | No licence-compatibility review recorded |
| ESLint glob adapter: `apps/web/tools/next-lint-glob` | Owner repo, backed by `tinyglobby` | Own adapter; dependency under its licence | Private | Existing | None | — |
| Provider-derived records (future) | Ticketmaster, official calendars, MusicBrainz | Each provider's terms and recorded permissions. MusicBrainz core is CC0 (public domain, so not exclusive). Ticketmaster content has caching and removal duties. | Not ours to treat as confidential property | None live (synthetic-only guard) | Freshness and lead time, not the data itself | Source approvals |
| User preferences, consent, outcomes | Users | Consent and privacy obligations; deletion rights | Personal data | Schema and local API | Consented feedback could improve relevance | Consent copy, retention, purge (G-06) |
| GrokBot reports and other external research | GrokBot (xAI) and others | Provider terms; cited sources keep their own rights | As the owner shares them | Advisory only | None | See [research handoff](research-handoff.md) |
| Future models and datasets | — | Need training/test permissions per source and use | — | None | Only with licensed history and evaluation | Phases 4–6 |

Do not apply a blanket proprietary notice over dependencies, adapted templates or provider
data. Choosing a repository licence, or none, is an owner decision.
