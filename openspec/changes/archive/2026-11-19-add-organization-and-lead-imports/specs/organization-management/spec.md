# Organization Management Spec Delta

## ADDED Requirements

### Requirement: City-first organization spreadsheet import
The organization import SHALL resolve distinct normalized city names first, creating missing cities. It SHALL then create each valid branch under its resolved city ID and store the normalized workbook branch code as the existing branch code. Existing matching records SHALL be reused without overwriting their settings.

#### Scenario: Multiple branches share a new city
- **WHEN** a workbook lists several branches for the same new city using equivalent normalized city names
- **THEN** the import creates one city first and links all valid branches to that city's ID.

#### Scenario: Branch is already registered
- **WHEN** the imported branch code, normalized branch name and city match an existing active branch
- **THEN** the branch is recorded as unchanged and its ID and settings are preserved.

#### Scenario: Conflicting branch or inactive organization
- **WHEN** an imported code belongs to a different branch, the name in the city belongs to a different code, or the matching city or branch is inactive
- **THEN** the affected row reports an error without moving, renaming or reactivating the existing record.

### Requirement: Imported branch codes in POS
The organization import SHALL preserve branch codes as identifiers under the current branch code contract. A new active branch created by import SHALL be resolvable by the existing POS import using the same code.

#### Scenario: Numeric workbook cell
- **WHEN** a whole-number Excel branch code is imported and the same code is later supplied to a POS registry upload
- **THEN** the POS row resolves to the imported branch ID.

#### Scenario: Explicit leading zeroes
- **WHEN** a branch code is supplied as text or with an explicit zero-padding format
- **THEN** the imported code preserves those leading zeroes for subsequent lookup.
