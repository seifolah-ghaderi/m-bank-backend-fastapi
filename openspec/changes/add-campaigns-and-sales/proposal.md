# Proposal

## Why

Branch staff need a workflow for turning campaign visits into verified sales and CRM customer records. The current backend supports organization, authentication, and POS follow-up, and this change adds the marketing workflow on that foundation.

## What Changes

- Give Supervisors manual lead entry, lead search and archival, and management of occupations and scored banking products.
- Let Supervisors select leads, activate and close campaigns, and opt in to customers for cross-sell. Give branch employees a pickable queue and their own assignments, with live quotas and same-branch manager reassignment.
- Record repeat visit attempts and let an employee open a prefilled customer and product-sale form from a visit.
- Give Supervisors a verification queue with one-sale and all-pending-sales approval, rejection reasons, and in-app decision notifications. Create the verified CRM customer on first approval and record a held product and employee score for each approved sale.
- Generate initial retention tasks from active schedules on first conversion.
- Defer lead imports, branch-code changes, direct and retention-originated sales, retention task execution, departed-employee recovery, sale reversals, league ranking, and Core Banking integration.

## Capabilities

### New Capabilities

- `lead-management`: Manual lead entry, deduplication, search, and archival.
- `sales-master-data`: Occupations and banking products with effective scoring values.
- `marketing-campaigns`: Lead selection, campaign lifecycle, employee pickup and branch reassignment, and visit history.
- `sales-verification`: Visit-based sale entry, conversion form, Supervisor decisions, and approved-sale scoring.
- `customer-management`: Verified CRM profiles, held products, and scoped customer history.
- `retention-generation`: Retention schedule configuration and one-time task generation on first conversion.

### Modified Capabilities

- `notifications`: Add in-app sale verification decisions for the submitting employee.

## Impact

Adds backend APIs under `/api/v1`, PostgreSQL migrations, and role-scoped records. Reuses the existing session, audit, notifications, normalization, and Jalali API conventions. The conversion form is specified as a backend API contract for its consuming client.
