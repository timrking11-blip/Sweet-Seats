# SS-RESEARCH-0.2 validation

Date: 2026-10-15. Environment: Python 3.12, standard library.

- `python3 -m unittest discover -s tests -v`: 12 tests passed.
- `python3 -m jobs.linear_research --fixture tests/fixtures/research/hourly.json`: one synthetic planned request, zero network calls.
- `python3 -m compileall -q adapters jobs services tests`: passed.

Coverage: exact execution/publication digest binding, approver membership, expiry, scope/classification/mode denial, completed-run suppression, newly approved revision reruns, evidence linkage, timestamp/budget validation and disabled legacy network entry points.

The first discovery command was invoked from the parent workspace and failed because tests/ was not there; rerunning from the repository root produced the passing results above.

These tests replace the prior scaffold's seven tests because automatic comment posting and in-memory webhook acknowledgement are intentionally withdrawn. Historical tests/code remain in the parent commit.

Not run / not claimed: real authentication, provider/API contracts, paid research, live Linear, durable Postgres jobs/outbox, migrations, scheduler deployment, restart/lease recovery, delivery retries or CI execution. No production resources modified.
