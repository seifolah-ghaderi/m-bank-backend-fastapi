## Purpose

Authenticate staff securely and enforce current account, role, and branch restrictions on every protected request.

## ADDED Requirements

### Requirement: Supervisor bootstrap
An operator SHALL create the first Supervisor through `python -m app.cli create-supervisor` with mobile and name arguments and an interactive password prompt. Subsequent bootstrap attempts SHALL require `--force`.

#### Scenario: Existing Supervisor
- **WHEN** bootstrap runs while a Supervisor exists without `--force`
- **THEN** it refuses to create another account.

### Requirement: Login and account lockout
`POST /api/v1/auth/login` SHALL verify normalized mobile and password as the first factor without issuing tokens. Unknown users and wrong passwords SHALL return equivalent 401 `invalid_credentials` responses with similar timing. Five consecutive password failures SHALL lock a known account for fifteen minutes; locked accounts SHALL return 423 `account_locked` with retry information.

#### Scenario: Lockout survives rejected requests
- **WHEN** a known account receives five consecutive incorrect passwords across separate requests
- **THEN** persisted failure state locks the account, and subsequent login attempts during the lock return 423 with `retry_after_seconds` in error details.

#### Scenario: Successful first factor
- **WHEN** an active, non-deleted, unlocked user submits a correct password
- **THEN** password failure state resets and a 202 response supplies `challenge_id`, a masked destination, `expires_in`, and `resend_after_seconds`, without user details, tokens, or an authenticated session; last-login time is not updated yet.

#### Scenario: Disabled account
- **WHEN** an inactive or soft-deleted account attempts authentication
- **THEN** authentication returns 401 `account_disabled`.

### Requirement: SMS verification
All roles SHALL complete SMS verification through `POST /api/v1/auth/verify-sms` with `challenge_id` and `code` before login succeeds. Challenges SHALL be single-use, expire after five minutes, and allow at most five incorrect attempts. Verification SHALL recheck current account state and mobile binding before issuing a session.

#### Scenario: Successful second factor
- **WHEN** an eligible user submits the correct code for an unexpired challenge
- **THEN** the challenge is consumed atomically, last login updates, a successful login is audited, and a 200 response returns user details, bearer access token, token type, and expiry while setting the refresh cookie.

#### Scenario: Invalid verification
- **WHEN** the challenge is expired, consumed, invalidated, unknown, or its code is incorrect
- **THEN** verification returns 401 `invalid_sms_code` without tokens, and a wrong-code attempt on a pending challenge persists its incremented attempt count.

#### Scenario: Attempts exhausted
- **WHEN** five incorrect codes have been submitted for one challenge
- **THEN** the challenge is invalidated and later submissions cannot authenticate, including a correct code.

#### Scenario: Concurrent verification
- **WHEN** two requests submit the correct code for the same challenge concurrently
- **THEN** at most one creates a session.

### Requirement: Challenge resend and delivery
`POST /api/v1/auth/resend-sms` SHALL require a pending challenge and enforce a 60-second per-user cooldown across resend and new login requests. Replacement SHALL invalidate the previous code without resetting the challenge's failed-attempt count or original five-minute deadline. Delivery failures SHALL issue no session and return 503 `sms_unavailable`.

#### Scenario: Resend too soon
- **WHEN** resend or repeated password login would send another code before the cooldown expires
- **THEN** it returns 429 `sms_rate_limited` with retry information and does not send another message.

#### Scenario: Replacement code
- **WHEN** a permitted resend succeeds
- **THEN** a new challenge ID replaces and invalidates the previous ID, only the replacement ID/code pair works, existing attempt/deadline limits remain, and another login challenge cannot bypass the per-user cooldown.

### Requirement: Development verification mode
Only `ENVIRONMENT=dev` SHALL permit a fixed code `123` and suppress real SMS delivery. Other environments SHALL require random six-digit codes and a configured SMS delivery adapter. Fixed-code configuration outside development SHALL fail startup. Development verification SHALL still require a password-validated, unexpired, single-use challenge.

#### Scenario: Development login
- **WHEN** a developer verifies a valid development challenge with code `123`
- **THEN** the normal session flow succeeds without any SMS provider call.

#### Scenario: Production mode enforcement
- **WHEN** production or staging starts with fixed-code mode enabled or with no SMS adapter configured
- **THEN** startup fails without exposing provider credentials.

### Requirement: Token lifecycle
Access tokens SHALL expire after fifteen minutes by default. Opaque refresh tokens SHALL expire after thirty days by default, have only hashes persisted, and be delivered only in refresh cookies. `POST /api/v1/auth/refresh` SHALL atomically revoke the cookie token and issue a replacement cookie plus access token; reuse of a revoked token SHALL revoke all refresh tokens of its user and return 401.

#### Scenario: Refresh rotation
- **WHEN** an active user presents a valid unused refresh token
- **THEN** exactly one replacement cookie and access token are issued and the previous refresh token is unusable.

#### Scenario: Reuse revocation persists
- **WHEN** a revoked refresh token is reused
- **THEN** the 401 response leaves every refresh token for that user revoked in persistent storage.

#### Scenario: Concurrent refresh
- **WHEN** two requests present the same refresh token concurrently
- **THEN** no more than one rotates it successfully and the other follows the reuse rule.

### Requirement: Browser session protection
Refresh cookies SHALL be HttpOnly, host-only, SameSite=Strict, scoped to `/api/v1/auth`, and Secure outside local development. Raw refresh tokens SHALL never appear in JSON or URLs. Cookie-based refresh, logout, and password-change requests SHALL require an allowed Origin and a session-bound `X-CSRF-Token`; access tokens SHALL be returned in JSON for in-memory frontend use.

#### Scenario: CSRF rejected
- **WHEN** a cookie-authenticated mutation lacks its valid CSRF token or allowed Origin
- **THEN** it returns 403 without rotating, revoking, or changing the session.

#### Scenario: CSRF token retrieval
- **WHEN** the configured web frontend calls `GET /api/v1/auth/csrf` with a valid refresh cookie
- **THEN** it receives a session-bound CSRF token without refresh-token disclosure; the endpoint does not rotate the session and disallows caching.

### Requirement: Password policy and forced change
Passwords SHALL contain 8–128 characters including a letter and digit and differ from the user's mobile. `POST /api/v1/auth/change-password` SHALL verify the current password, clear `must_change_password`, record the change time, and revoke other refresh sessions. Forced-change users SHALL access only change-password, me, and logout among protected endpoints.

#### Scenario: Temporary password restrictions
- **WHEN** a forced-change user accesses a protected city, branch, user, or audit endpoint
- **THEN** it returns 403 `password_change_required` until a successful password change.

#### Scenario: Change password
- **WHEN** the current password and policy-compliant new password are supplied
- **THEN** the change succeeds, pending SMS challenges and other refresh sessions are revoked, and the current valid refresh-cookie session is retained when owned by the caller; without it all refresh sessions are revoked.

### Requirement: Current account and authorization
Protected requests SHALL load the current user from persistent storage rather than trusting token role or branch claims. `GET /api/v1/auth/me` SHALL return the current user with branch and city when applicable. Disabled accounts SHALL receive 401; prohibited roles SHALL receive 403; out-of-scope resource identifiers SHALL return 404.

#### Scenario: Role changes during access-token validity
- **WHEN** a user's role or branch changes after access-token issuance
- **THEN** the next protected request uses the new stored role and branch.

#### Scenario: Immediate deactivation
- **WHEN** a deactivated user's unexpired access token is presented
- **THEN** the request returns 401 `account_disabled`.

### Requirement: Logout and token cleanup
`POST /api/v1/auth/logout` SHALL revoke the caller's refresh-cookie session, clear its cookie, and return 204 even when the token is absent or unknown after applicable security checks. A daily operator command `python -m app.cli purge-tokens` SHALL remove refresh-token records whose expiry or revocation is over thirty days old and expired, consumed, or invalidated challenge records older than thirty days.

#### Scenario: Repeated logout
- **WHEN** an authenticated user passes applicable Origin/CSRF checks and logs out with an absent, already revoked, or unknown refresh cookie
- **THEN** it returns 204, clears the cookie, and does not disclose token ownership.

#### Scenario: Cleanup retention
- **WHEN** token cleanup runs
- **THEN** live tokens and recently expired or revoked tokens remain while eligible old token records are purged.
