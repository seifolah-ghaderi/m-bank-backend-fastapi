# lead-management Specification

## Purpose

Maintain the branch-owned source records used to select and contact leads in marketing campaigns.

## ADDED Requirements

### Requirement: Manual lead entry
Only Supervisors SHALL create leads. A lead SHALL have first name, last name, normalized Iranian mobile, an active branch and an active city. National code, occupation, address, referrer and additional information are optional. A supplied national code SHALL pass checksum validation and a supplied occupation SHALL be active. The lead's branch SHALL stay fixed.

#### Scenario: Manual creation without a spreadsheet
- **WHEN** a Supervisor supplies the required fields and a valid active branch and city
- **THEN** the system creates a lead that can be selected for a draft campaign.

#### Scenario: Duplicate identity
- **WHEN** a supplied mobile or national code already identifies another lead, including an archived lead
- **THEN** the request returns 409 and no duplicate lead is created.

### Requirement: Supervisor lead discovery and archive
Supervisors SHALL list and search leads by normalized name and filter by branch, city, occupation and archived state. Default lists and campaign selection SHALL omit archived leads. Supervisors SHALL be able to archive and restore eligible leads, preserving historical relationships and auditing the action.

#### Scenario: Archive an eligible lead
- **WHEN** a Supervisor archives a lead with no active campaign membership, nonfinal sale or verified customer
- **THEN** it is hidden from default selection and remains visible in archived searches.

#### Scenario: Archive a lead with current work
- **WHEN** a Supervisor tries to archive a lead in an active campaign, with a draft, submitted or rejected sale, or with a verified customer
- **THEN** the request returns 409 and the lead stays available to authorized workflows.
