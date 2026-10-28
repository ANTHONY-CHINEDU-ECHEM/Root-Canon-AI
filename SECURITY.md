# Security and data protection

Report vulnerabilities privately to the maintainer rather than in a public issue.

## Design summary

* Identifiers (names with titles, valid NHS numbers, postcodes, dates of birth, phones, emails) are redacted
  before text reaches retrieval, a model vendor, the cache, the audit log or a feedback record.
* The audit log stores an HMAC of the redacted question keyed with `RC_AUDIT_SALT`, never the text.
* API keys are compared in constant time; governance data needs a separate admin key.
* Responses carry `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and `Cache-Control:
  no-store`; the interface is served with a restrictive Content Security Policy.
* For organisations whose information governance forbids off site processing, set `RC_LLM_PROVIDER=ollama`
  and `RC_LLM_FALLBACKS=` so no text leaves the network.

## Before production

Set a long random `RC_AUDIT_SALT`, real `RC_API_KEYS` and `RC_ADMIN_API_KEYS`, `RC_ENV=production`
(which disables keyless development access), restrict `RC_CORS_ORIGINS`, and complete a DPIA.
