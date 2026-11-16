# Web authentication

All paths below are under `/api/v1`. The frontend and API must be on the same site
for SameSite=Strict refresh cookies; allowed frontend origins are exact values in
`CORS_ORIGINS`. Frontend implementation and mobile-client integration are outside
this change. Store access tokens in memory, not persistent browser storage.

## Password then SMS

1. Send `POST /auth/login` with JSON `{"mobile":"09121234567","password":"..."}`
   and the configured frontend `Origin` header. A successful password check returns
   202 with `challenge_id`, masked `destination`, `expires_in`, and
   `resend_after_seconds`. It creates no authenticated session.
2. Send `POST /auth/verify-sms` with `{"challenge_id":"UUID","code":"123"}`.
   Development (`ENVIRONMENT=dev`, `SMS_MODE=fixed`) uses `123` and sends no SMS.
   Other environments require a configured HTTP SMS adapter and random six-digit codes.
3. Successful verification returns 200 with `access_token`, `token_type`, `expires_in`,
   `user`, and `csrf_token`. It sets a host-only `crm_refresh` HttpOnly cookie scoped
   to `/api/v1/auth`, SameSite=Strict and Secure outside local development. Refresh
   tokens never appear in JSON or URLs. Include browser credentials on auth requests.
4. Send the access token as `Authorization: Bearer ...` for application endpoints.

Challenges expire in five minutes and allow five wrong codes. Resend via
`POST /auth/resend-sms` with `challenge_id` after the 60-second cooldown. A replacement
ID invalidates the previous one and retains failed attempts and the original expiry.
Repeated password login shares the per-user send cooldown. Consumed, invalidated,
expired, pending-delivery, and failed-delivery challenges cannot authenticate.

Five wrong passwords lock the account for fifteen minutes. Errors use stable codes:
`invalid_credentials` (401), `account_disabled` (401), `account_locked` (423),
`invalid_sms_code` (401), `sms_rate_limited` (429), and `sms_unavailable` (503).
Locked/rate-limited responses include retry seconds in `error.details`.

## Browser session lifecycle

After reload, call `GET /auth/csrf` with the refresh cookie and allowed Origin. It
returns a session-bound token with `Cache-Control: no-store`. Use `X-CSRF-Token`
and an allowed Origin for `POST /auth/refresh`, `/auth/logout`, and cookie-bearing
`/auth/change-password`. Refresh rotates the cookie and CSRF token and returns a new
access token; use the replacement CSRF token on subsequent requests. A rejected
Origin or CSRF check changes no session state.

`GET /auth/me` returns the current database role, branch/city, and account details.
Temporary-password accounts may only access me, change-password, and logout among
protected endpoints. Refresh/CSRF recovery remains available without granting access
to application functions.

Change-password takes `current_password` and `new_password` (8–128 characters, at
least one letter/digit, different from mobile), clears forced change, invalidates
pending challenges, and revokes other refresh sessions. It preserves the caller's
valid cookie session, or revokes all sessions if none is supplied. Logout requires
access authentication, revokes the owned cookie session, clears the cookie, and
returns 204 idempotently after applicable Origin/CSRF checks. Unexpired access tokens
survive ordinary logout/password change until their fifteen-minute expiry; disabled
and deleted accounts are rejected immediately on every protected request.

## SMS adapter and production gate

`SMS_MODE=http` sends an HTTPS POST to `SMS_URL` with bearer `SMS_API_KEY` and JSON
`{"to":"normalized-mobile","code":"six digits","sender":"configured sender"}`.
The provider or a bank-controlled gateway must return a successful HTTP status with
`{"accepted":true}`. Set `SMS_SENDER` if required. Network calls use the configured
bounded timeout; uncertain delivery fails closed without creating a session.

The adapter stores only a keyed code digest, never plaintext. Configure an independent
`SMS_DIGEST_SECRET`, along with independent JWT/CSRF secrets. Staging/production refuse
fixed mode, missing credentials, or a non-HTTPS provider URL. Settings and limits are
listed in `.env.example`; provider credentials and code values must never enter logs.

**Production release requires selecting the real provider/gateway, matching its
contract, and verifying actual handset delivery.** Automated tests use fake delivery
and never contact a real provider. Production SMS delivery has not been exercised here.
