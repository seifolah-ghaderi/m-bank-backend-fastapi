# Tasks

## 1. Catalog and lead registry

- [x] 1.1 Add occupation and banking product models, migrations and APIs. Document lookup and write contracts and test role enforcement, normalized uniqueness, deactivation and score validation.
- [x] 1.2 Add the manual lead model, creation and filtered search. Document request fields and test normalization, duplicate mobile and national code, branch eligibility and Supervisor-only access.
- [x] 1.3 Add lead archive and restore with audit and historical visibility. Document search behavior and test that active campaign memberships, nonfinal sales and verified customers block archival when those relationships exist.

## 2. Campaigns and visit work

- [x] 2.1 Implement draft campaign CRUD, selection preview and application, activation and closure. Document filters and transitions and verify in PostgreSQL that conflicts roll back activation and completed work remains reserved until closure.
- [x] 2.2 Implement branch-scoped work lists, pickup, capacity and manager overrides and reassignment. Document role scope and verify concurrent picks, quota races, count updates, zero-staff reporting and cross-branch denial.
- [x] 2.3 Add the visit summary, repeat attempts and explicit work completion. Document date and result fields and test that attempts preserve actor and first timestamp, completion stops new attempts, and inaccessible assignments return 404.

## 3. Sale form and verification

- [x] 3.1 Add drafts and the visit sales-form API, with customer profile prefilling and existing-customer handling. Document form fields and test draft validation, ownership and duplicate claims.
- [x] 3.2 Add immutable submissions, employee correction and withdrawal, and the Supervisor queue and rejection action with transactional notification. Document the lifecycle and test atomic batch submission, stale submission revisions, reassignment, closure and recipient privacy.
- [x] 3.3 Implement verified customer and held product records, the score ledger, retention schedule settings and initial task generation. Document schedule settings and test schedule validation, approval-required state, business-date due dates and stable historical scores.
- [x] 3.4 Implement Supervisor single approval and the reviewed batch action. Require the reviewed submission revision for every decision so an intervening resubmission returns 409. Document atomicity and test selected-sale conflicts, concurrent first conversion, duplicate customer code, exact-once scoring and notification, and full rollback on failure.
- [x] 3.5 Add scoped customer search, details and audited contact corrections. Document allowed fields per role and test foreign-branch requests, employee visibility, and sensitive data filtering.

## 4. Integration verification

- [x] 4.1 Exercise manual lead entry through campaign pickup, repeat visits, partial approval, first task generation, and later cross-sell in a PostgreSQL API integration test. Verify later approvals do not duplicate tasks.
- [x] 4.2 Apply migrations to clean and Phase 1 head databases and verify runtime privileges on new history tables. Run `uv run alembic check`, `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` against the documented development setup.
