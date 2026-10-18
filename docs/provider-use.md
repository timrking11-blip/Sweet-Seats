# Provider use policy

## Perplexity

Perplexity may be used as a research and creative-support tool for competitive scans, naming, design inspiration and source discovery. Its output is **not** production evidence, source permission, canonical data or an implementation instruction.

- Do not submit credentials, private user data, licensed marketplace payloads, unpublished code or secrets.
- Capture source URLs and dates for factual claims, then independently verify the claim against primary provider documentation before a source is activated.
- Treat generated copy and ideas as proposed until reviewed against the product charter, accessibility standards and rights policy.
- Do not make Perplexity a runtime data dependency in the first release.

The environment placeholder is reserved for the separately approved SS-RESEARCH-0.2 path. It does not enable a provider call in this discovery increment.

## Runtime routing

The PWA uses `/api/discovery/*` as its same-origin path. Local development rewrites that path to `http://127.0.0.1:8000`; when a Render API is later provisioned, Vercel receives its HTTPS origin through the server-only `SWEET_SEATS_API_ORIGIN` build variable. This routing variable is not a credential and does not activate providers.

## Provider activation checklist

Before an adapter is enabled, record the provider's account status, terms/version, permitted collection and display, raw and derived retention, model-training/testing rights, attribution, quotas, costs, expiration, fields and failure behavior. A successful API request is insufficient.

