# marketing-campaigns Specification

## Purpose

Run branch-scoped acquisition and cross-sell campaigns with employee pickup and durable visit history.

## Requirements

### Requirement: Campaign draft and lead selection
Only Supervisors SHALL create campaigns and manage their draft lead selections. A campaign SHALL have a title, start date, end date on or after the start date, and an explicit cross-sell option defaulting to false. Selection SHALL support branch, city, occupation and normalized name filters and SHALL record each lead's existing branch and assignment time. Only leads assigned to an active branch SHALL be eligible for preview, selection, and activation.

#### Scenario: Select eligible leads
- **WHEN** a Supervisor selects matching leads for an acquisition campaign
- **THEN** each eligible lead is added at most once under its own branch and archived leads and verified customers are excluded.

#### Scenario: Opt into cross-sell
- **WHEN** a Supervisor enables customer inclusion for a draft campaign
- **THEN** eligible leads with verified customers can be selected and their customer status is visible to authorized staff.

#### Scenario: Unassigned imported lead
- **WHEN** a Supervisor previews a draft selection that matches an imported lead without a branch, or explicitly requests that lead
- **THEN** the lead is excluded from the preview and does not enter the campaign.

#### Scenario: Imported lead receives a branch
- **WHEN** a Supervisor assigns an active branch to an imported lead that otherwise meets the campaign rules
- **THEN** the lead becomes eligible and campaign membership records the assigned branch.

### Requirement: Campaign activation and closure
Only Supervisors SHALL activate or close campaigns. Activation SHALL reserve every eligible selected lead until the campaign closes, including leads whose work is completed. Activation with any lead reserved by another campaign SHALL fail atomically with 409 and identify the conflicts. Activation SHALL identify branches with selected leads and no eligible employees.

#### Scenario: Completed lead remains reserved
- **WHEN** a Supervisor activates a second campaign containing a lead whose work finished in a still-active campaign
- **THEN** activation fails and the second campaign remains a draft.

#### Scenario: Closure releases leads
- **WHEN** a Supervisor closes the active campaign
- **THEN** the lead reservations are released, new pickups stop and the campaign's historical records remain available within role scope.

#### Scenario: Draft selection became ineligible
- **WHEN** a selected lead was archived, its branch became inactive, or it became a customer and the campaign excludes customers before activation
- **THEN** activation fails atomically with 409 and identifies the ineligible selections for correction.

### Requirement: Employee campaign visibility
Employees SHALL see active campaign leads in their branch that are unpicked or assigned to them. Branch Managers SHALL see campaign work only for their branch. Cross-sell rows SHALL identify the customer and show held product names to eligible staff. Employee mutation of leads and visits SHALL require current assignment.

#### Scenario: A coworker takes a lead
- **WHEN** an employee opens the branch queue after another employee has picked a lead
- **THEN** that lead is omitted and another branch's leads are never disclosed.

### Requirement: Pickup, capacity and reassignment
The system SHALL permit a pick only by an eligible employee in the lead's branch and below their effective quota. The base quota SHALL be the ceiling of campaign leads in that branch divided by eligible employees. Completed leads SHALL count toward their current owners' picked totals. Managers SHALL be able to override individual quotas with a reason and reassign locked leads to eligible employees in their own branch, including above quota.

#### Scenario: Concurrent picks against one slot
- **WHEN** an employee with one slot remaining concurrently tries to pick two different leads
- **THEN** at most one succeeds and the other returns 409 `quota_reached`.

#### Scenario: Two employees pick the same lead
- **WHEN** two eligible employees concurrently pick the same available lead
- **THEN** only one acquires it and the other receives 409 `lead_unavailable`.

#### Scenario: Manager reassigns above quota
- **WHEN** a manager reassigns a locked lead to an eligible employee of their branch who is already at quota
- **THEN** the destination owns the lead, capacity counts follow the new assignment, and the initial pickup time and prior visit authorship remain recorded.

### Requirement: Scoped capacity view
The capacity view SHALL expose computed and effective quotas, picked and completed counts, remaining capacity and override status. Supervisors SHALL see any campaign branch, Branch Managers only their own branch, and employees only their own capacity. A zero-staff branch SHALL have no pickable capacity.

#### Scenario: Staffing changes during a campaign
- **WHEN** an employee becomes eligible for a branch with a running campaign
- **THEN** computed quotas reflect the new employee count on the next capacity read or pick and past assignments remain recorded.

### Requirement: Visit attempts and completion
The current assignee SHALL be able to record repeat attempts on picked lead work in an active campaign. Each attempt SHALL preserve actor, server time, reported non-future visit date, result and notes, with the visit summary reflecting the latest attempt. After recording an attempt, the assignee SHALL be able to complete the work explicitly. Completion SHALL preserve the assignment and attempts.

#### Scenario: Repeat visit
- **WHEN** an assignee records another attempt with a new result
- **THEN** prior attempts stay available within scope, the summary reflects the new attempt and the first-visit timestamp is preserved.

#### Scenario: Complete a visit with a sale pending
- **WHEN** the assignee completes work after recording a visit with a submitted sale
- **THEN** the lead is no longer actionable for visits, remains reserved until closure and the submitted sale stays in the verification queue.
