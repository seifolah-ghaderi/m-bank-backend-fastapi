## MODIFIED Requirements

### Requirement: Normalized identifiers and text
The service SHALL normalize Persian and Arabic digits to ASCII, Arabic variants of Persian letters, zero-width characters, and whitespace before validation and search. Iranian mobiles SHALL normalize to `09XXXXXXXXX`; national codes SHALL have ten digits and a valid checksum, rejecting repeated identical digits.

#### Scenario: Equivalent mobile inputs
- **WHEN** the same Iranian mobile is submitted with Persian digits or an international prefix `+98`, `0098`, or `98`, spaces, or dashes
- **THEN** validation and lookup use the same eleven-digit local identifier.

#### Scenario: Invalid national code
- **WHEN** a supplied national code has an invalid checksum or all identical digits
- **THEN** the service returns 422 with code `invalid_national_code`.

#### Scenario: Local zero and international prefix variants
- **WHEN** the mobile is `+9809173094912`, `09173094912`, or `9173094912`, including Persian/Arabic digit equivalents
- **THEN** normalization yields `09173094912` before validation and lookup; standard `+98`, `0098`, and `98` forms remain supported.
