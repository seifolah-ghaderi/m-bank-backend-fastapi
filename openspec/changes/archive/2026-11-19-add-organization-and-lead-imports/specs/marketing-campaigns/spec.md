# Marketing Campaigns Spec Delta

## MODIFIED Requirements

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
