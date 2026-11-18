# notifications Spec Delta

## ADDED Requirements

### Requirement: Private sale verification notifications
The system SHALL create an in-app `verification_approved` or `verification_rejected` notification for each decided sale in the decision transaction. The original sale author SHALL receive the notification with a sale reference. Notifications SHALL omit customer details, account references and proof, and links SHALL use current access rules.

#### Scenario: Approval batch commits
- **WHEN** a Supervisor approves multiple sales for a visit in a single transaction
- **THEN** each approval produces exactly one private notification for its sale author.

#### Scenario: Verification rolls back
- **WHEN** sale verification fails or its transaction rolls back
- **THEN** no notification for the failed decision persists.
