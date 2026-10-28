# OIDC authentication for the synthetic realm

Status: `fixture_tested`. Signed JWT tests use real RSA keys and mocked HTTPS JWKS responses. No live identity provider or browser login flow has been verified. `WORK4CE_MODE=demo` is required; enabling OIDC does not enable production mode or live tenant data.

Set these non-secret configuration values in environment settings:

| Variable | Requirement |
|---|---|
| `WORK4CE_AUTH_MODE` | `oidc` |
| `WORK4CE_OIDC_ISSUER` | Exact trusted HTTPS issuer URL |
| `WORK4CE_OIDC_AUDIENCE` | Dedicated API access-token audience; never reuse the browser application's client ID |
| `WORK4CE_OIDC_JWKS_URL` | Explicit trusted HTTPS JWKS endpoint, without credentials, query or fragment |
| `WORK4CE_OIDC_SUBJECT_ROLES` | JSON object mapping approved subject strings to `analyst` or `admin` |

An illustrative role mapping is `{"approved-analyst-subject":"analyst","approved-admin-subject":"admin"}`. Replace identifiers with actual approved subjects. Duplicate JSON keys and invalid roles are rejected. No dynamic identity-provider administration is provided.

Obtain a short-lived API access token using your provider's approved authentication flow and supply it securely as `WORK4CE_ACCESS_TOKEN` for the CLI or as an HTTP bearer token for API calls. Never paste tokens into source, reports or logs. Demo tokens are optional and ignored in OIDC mode.

The verifier accepts RS256 only, requires exact issuer and scalar audience plus `exp`, `iat` and nonempty `sub`, validates optional `nbf`, and limits token lifetime to one hour. Headers must use reviewed `JWT` or `at+jwt` types with a key identifier. Accepting `JWT` accommodates providers using that generic type; a dedicated API audience prevents browser ID-token substitution.

JWKS is fetched only from the configured URL with TLS verification and inherited proxy/CA trust, without redirects or token-supplied URLs. Responses are bounded to 64 KiB and 32 keys. RSA keys must be 2048–8192 bits and suitable for signature verification. Cache lifetime is 300 seconds, refreshes are rate-limited to once per 30 seconds, and expired cache data is not used during outages. Invalid tokens return a redacted 401; unavailable JWKS returns a redacted 503.

Before live testing, allow the configured identity-provider hostname through the environment network settings and verify the actual endpoint. No identity-provider secret is required for public JWKS verification. Authenticated subjects receive only server-configured roles, the fixed synthetic tenant and reviewed connector grants. Token-provided roles, permissions or tenant claims cannot elevate access.

Production identity operations, TLS deployment, account lifecycle, broader revocation policy and live-provider interoperability remain pending. JWKS cache validity can retain a removed signing key for up to 300 seconds; short token lifetimes and operational rotation procedures are required.
