# organization-management Specification

## Purpose

Maintain the city and branch hierarchy used to organize staff and constrain access throughout the CRM.

## Requirements

### Requirement: City maintenance
Only Supervisors SHALL create, update, or soft-delete cities through `/api/v1/cities` and `/api/v1/cities/{id}`. City names SHALL be normalized, trimmed, 2–100 characters, and unique ignoring case among non-deleted cities. Every authenticated role SHALL list and view cities.

#### Scenario: Normalized duplicate city
- **WHEN** a Supervisor creates a city equivalent to an existing non-deleted city's normalized name
- **THEN** the request returns 409 and creates no duplicate.

#### Scenario: Unauthorized maintenance
- **WHEN** a Branch Manager or Employee attempts a city write
- **THEN** it returns 403 `forbidden`.

### Requirement: Branch maintenance
Only Supervisors SHALL create, update, or soft-delete branches through `/api/v1/branches` and `/api/v1/branches/{id}`. Each branch SHALL belong to a non-deleted city, have a globally unique non-deleted uppercase code of 2–20 letters, digits, or hyphens, and a name unique within its city.

#### Scenario: Branch normalization
- **WHEN** a Supervisor creates a branch with a lowercase valid code
- **THEN** the stored and returned code is uppercase and uniqueness uses that code.

#### Scenario: Move branch to another city
- **WHEN** a Supervisor changes a branch's city to another valid city
- **THEN** the branch changes city while its users remain attached to the same branch.

### Requirement: Derived branch manager
Branch responses SHALL derive an optional manager from the branch's non-deleted user with role `branch_manager`, include city identity and active employee count, and accept a branch without a manager. There SHALL be at most one non-deleted manager per branch, including inactive managers.

#### Scenario: Branch without manager
- **WHEN** an authorized client views a branch with no manager
- **THEN** manager is null, and the branch remains valid.

#### Scenario: Manager reassigned
- **WHEN** a manager moves between branches
- **THEN** branch responses reflect the new relationship without a separately maintained manager field.

### Requirement: Organization visibility and filtering
The Supervisor SHALL see all branches; Branch Managers and Employees SHALL see only their own branch. Lists SHALL support name search, active/inactive filtering, and name sorting. Explicit `include_inactive=false` SHALL provide active lookups; omitted filtering SHALL include inactive records for Supervisors and exclude them for other roles.

#### Scenario: Cross-branch identifier
- **WHEN** a Branch Manager or Employee requests another branch by ID
- **THEN** the service returns 404 `not_found`.

#### Scenario: Cross-branch filter
- **WHEN** a Branch Manager supplies a `branch_id` filter different from their own
- **THEN** it returns 403 and reveals no other branch's data.

#### Scenario: Lookup filtering
- **WHEN** an authenticated client lists cities or branches with `include_inactive=false`
- **THEN** only active, non-deleted, in-scope records appear.

### Requirement: Organization lifecycle preservation
City and branch deletion SHALL set deletion metadata and return 204, preserving historical references. A city with non-deleted branches SHALL return 409 `city_has_branches`; a branch with non-deleted users SHALL return 409 `branch_in_use`. Deactivation SHALL preserve existing relationships.

#### Scenario: City still contains a branch
- **WHEN** a Supervisor deletes a city containing an inactive but non-deleted branch
- **THEN** deletion is rejected with `city_has_branches`.

#### Scenario: Branch still contains a user
- **WHEN** a Supervisor deletes a branch containing an inactive but non-deleted user
- **THEN** deletion is rejected with `branch_in_use`.

#### Scenario: Deactivated branch
- **WHEN** a branch is deactivated
- **THEN** current users and historical references remain and new user assignments into it are rejected.

#### Scenario: Deleted organization record
- **WHEN** a client lists or retrieves an organization record after successful soft deletion
- **THEN** ordinary queries exclude it, while stored historical references remain intact.

### Requirement: Terminal-dependent branch preservation
Branch deletion SHALL return 409 `branch_in_use` while any non-deleted POS terminal belongs to that branch, including inactive or retired terminals. Branch output SHALL include its count of non-deleted POS terminals. Inactive/deleted branches SHALL reject new terminals, transfers, dispatch, and employee assignment while historical references remain readable within scope.

#### Scenario: Branch with terminal and no users
- **WHEN** a Supervisor deletes a branch containing a non-deleted retired terminal but no users
- **THEN** deletion is rejected and the terminal's branch remains intact.

#### Scenario: Device count
- **WHEN** an authorized user views their permitted branch
- **THEN** its terminal count includes all non-deleted operational statuses and excludes deleted terminals.

#### Scenario: Inactive branch work
- **WHEN** a branch is deactivated with existing assigned work
- **THEN** historical work remains, the current assignee may complete it, and new dispatch/assignment into that branch is rejected.
