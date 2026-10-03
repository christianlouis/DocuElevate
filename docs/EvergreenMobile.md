# Evergreen native mobile compatibility

Evergreen supports the existing native app's login callback at
`docuelevate://callback`. A development Expo callback is accepted only for
localhost/127.0.0.1 and the scoped `/--/callback` or `/callback` paths. HTTP,
arbitrary custom schemes, credentials, query strings, and fragments are
rejected.

After a successful browser OAuth or local login, the callback receives an
opaque bearer token. The database stores only its SHA-256 hash. Tokens expire
after 30 days and can be revoked with `POST /api/auth/mobile/revoke`; expired,
revoked, or unknown tokens receive JSON 401 responses. Token issuance failures
return `error=mobile_token_failed` to the validated native callback.
OAuth callback destinations are bound to the provider's generated state, so
overlapping web and native logins cannot consume each other's destination.
Pending native destinations expire after ten minutes and are bounded to eight
entries per browser session.

Bearer access is deliberately limited to identity, language preference, file
list/detail, and the existing UI upload route. Signed-in browser sessions retain
the existing access model; mobile bearer authentication does not
unlock settings, integrations, diagnostics, or administrative APIs.

The token profile is a snapshot of the existing single-user identity:
`owner_id`, `display_name`, `email`, `avatar_url`, `is_admin`, and
`preferred_language`. `POST /api/i18n/language` persists the supplied language
on the token snapshot (and in the browser session when applicable). Evergreen
continues to use one shared document set; this backport does not add
multitenancy, device registration, QR login, or push delivery.

The isolated `evergreen_mobile_tokens` table is created idempotently during the
existing startup `metadata.create_all` initialization. It is additive and does
not alter file or workflow tables. Existing rows remain intact when startup is
repeated. Removing this table is not part of normal upgrade or rollback; a
rollback should remove only the code that references it after preserving the
database snapshot.

Mobile sign-in requires `AUTH_ENABLED=true` and either the existing local admin
credentials or the configured OAuth provider. With authentication disabled,
Evergreen does not register login routes and cannot issue mobile tokens.

Run the focused regression tests with:

```sh
pytest tests/test_evergreen_mobile.py tests/test_evergreen_mobile_postgres.py
```

The PostgreSQL test is skipped unless `MOBILE_TEST_POSTGRES_URL` points to a
local database named `docuelevate_test`. CI supplies PostgreSQL 16 and runs the
test inside a disposable schema. It exercises actual application startup twice,
checks that existing file rows survive, and authenticates a persisted token
after restart. The HTTP tests cover local login and mocked OAuth; a real iPhone
SSO round trip remains a deployment smoke test.
