## ADDED Requirements

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
