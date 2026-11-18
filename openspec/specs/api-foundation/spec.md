# api-foundation Specification

## Purpose

Provide predictable API behavior, operational health signals, and shared input conventions for the bank CRM backend.

## Requirements

### Requirement: Runtime configuration
The service SHALL read configuration from environment variables, require database and signing credentials, restrict CORS to configured origins, and disable OpenAPI documentation in production.

#### Scenario: Missing mandatory configuration
- **WHEN** the service starts without a database URL or signing secret
- **THEN** startup fails with a configuration error without exposing secrets.

#### Scenario: Production documentation
- **WHEN** a client requests interactive documentation or the OpenAPI schema in production
- **THEN** those routes are unavailable.

### Requirement: Health endpoints
The service SHALL expose public `/api/v1/health` liveness and `/api/v1/health/ready` database readiness endpoints.

#### Scenario: Database unavailable
- **WHEN** the process is running but cannot query the database
- **THEN** liveness returns 200 and readiness returns 503 without connection details.

#### Scenario: Ready service
- **WHEN** the database is reachable and a readiness query succeeds
- **THEN** readiness returns 200.

### Requirement: Error and tracing contract
Every API error SHALL return an `error` object with `code`, English `message`, `details`, and `request_id`. Responses SHALL echo a valid UUID `X-Request-ID` or a generated UUID when the supplied ID is absent or invalid.

#### Scenario: Validation error
- **WHEN** a request contains an invalid field
- **THEN** the response is 422 with field, code, and message entries in `details`, and a matching response request ID.

#### Scenario: Malformed JSON
- **WHEN** an endpoint expecting JSON receives malformed JSON
- **THEN** it returns 400 with code `invalid_json` and the shared error shape.

#### Scenario: Unexpected failure
- **WHEN** an unhandled application error occurs
- **THEN** the response is 500 with a generic message and request ID, without a stack trace or secrets.

### Requirement: List contract
List endpoints SHALL accept `page` defaulting to 1 and `page_size` defaulting to 20 with maximum 100, return `items`, `total`, `page`, and `page_size`, and support only documented sort fields with a leading minus for descending order.

#### Scenario: Default list request
- **WHEN** an authorized client lists resources without pagination parameters
- **THEN** at most 20 scoped items and the total matching scoped count are returned for page 1.

#### Scenario: Invalid list parameters
- **WHEN** page is below 1, page size is outside 1–100, or sort names an unsupported field
- **THEN** the service returns 422.

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

### Requirement: Time conventions
The service SHALL persist timestamps in UTC and dates in native database date types, calculate business dates in `APP_TIMEZONE` defaulting to `Asia/Tehran`, and expose all business dates and date-times using the Persian Jalali calendar. Standard protocol dates and numeric token expiry claims SHALL retain their protocol formats.

#### Scenario: Business day differs from UTC
- **WHEN** an operation derives today's date while Tehran and UTC are on different dates
- **THEN** the derived business date follows the configured timezone.

### Requirement: Persian date API contract
Business date inputs and outputs SHALL use Jalali `YYYY/MM/DD`; date-times SHALL use `YYYY/MM/DDTHH:mm:ss[.ffffff]±HH:MM`. Inputs SHALL normalize Persian/Arabic digits; outputs SHALL use ASCII digits. Responses SHALL use the configured business timezone. Request bodies, query filters, entity metadata, and audit before/after values SHALL share this contract.

#### Scenario: Persian date filter
- **WHEN** an audit date filter contains Persian digits in a valid Jalali date
- **THEN** it selects the corresponding business day and returns Jalali occurrence date-times with explicit offsets.

#### Scenario: Date-time round trip
- **WHEN** a valid offset-bearing Jalali date-time is accepted and later returned
- **THEN** it represents the same instant after UTC persistence and business-timezone serialization.

#### Scenario: Invalid Jalali date
- **WHEN** a date has an impossible Jalali month/day, an invalid leap day, or a date-time lacks an offset
- **THEN** the service returns 422 with field-level details rather than guessing a Gregorian interpretation.

### Requirement: Web frontend integration
This phase SHALL serve a web frontend through the API without delivering frontend code or a mobile integration. Configured web origins SHALL support credentialed browser requests and required CSRF headers; unconfigured origins SHALL not receive credentialed CORS permission.

#### Scenario: Allowed frontend origin
- **WHEN** the configured frontend makes a credentialed preflight for the documented authentication headers
- **THEN** CORS permits that exact origin and the documented methods and headers without a wildcard credentialed origin.

#### Scenario: Unconfigured frontend origin
- **WHEN** an unconfigured origin requests credentialed API access
- **THEN** the service grants no CORS permission to that origin.

### Requirement: HTTP security and logs
The deployed service SHALL limit requests to 12 MB, limit login to ten requests per minute per client IP, and emit structured logs with request IDs while excluding passwords and tokens and masking mobiles. Proxy-generated API errors SHALL follow the shared error contract.

#### Scenario: Login rate exceeded
- **WHEN** an IP exceeds the configured login limit
- **THEN** the proxy returns 429 with code `too_many_requests` and a request ID.

#### Scenario: Oversized request
- **WHEN** a request exceeds 12 MB
- **THEN** the deployed service returns 413 with code `file_too_large`.
