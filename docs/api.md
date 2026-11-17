# Core API contracts

All application routes use `/api/v1`. Errors have the shape
`{"error":{"code":"not_found","message":"Not found","details":[],"request_id":"UUID"}}`.
Messages are English; frontend translations use stable error codes. Validation errors
include field, code, and message details, without echoing input secrets. Invalid JSON
returns 400; field errors 422; disallowed roles 403; out-of-scope IDs 404; conflicts 409.
`X-Request-ID` accepts a UUID or is generated, then echoed in responses and JSON logs.

Lists accept `page=1`, `page_size=20` (1–100), and endpoint-specific `sort` fields,
with `-` for descending. Responses contain `items`, scoped `total`, `page`, and
`page_size`. Invalid sort fields return 422; tied rows use an ID tie-breaker.

## Persian calendar and normalization

All business dates use Jalali `YYYY/MM/DD`, for example `1405/08/25`.
Date-times use `YYYY/MM/DDTHH:mm:ss[.ffffff]±HH:MM`, for example
`1405/08/25T09:30:00+03:30`. These are custom Jalali strings, not ISO 8601.
Persian/Arabic input digits normalize to ASCII. Responses use ASCII digits and
the configured `APP_TIMEZONE`, default `Asia/Tehran`. Invalid Jalali dates,
non-leap Esfand 30, or date-times lacking offsets return 422.

Database timestamps remain UTC/native PostgreSQL values. JWT expiry claims,
duration seconds, HTTP Date/cookie Expires, and operational logs retain standard
protocol formats. Filters and audit values follow the same Jalali business contract.
Date-only range filters include entire business days, using an exclusive upper
bound at midnight after the final day. Sorts compare native dates, not formatted text.

Mobile inputs normalize `+98`, `0098`, and `98` to `0`, strip spaces/dashes, and
require `09XXXXXXXXX`. National codes require ten digits and the Iranian checksum;
repeated identical digits are invalid. Names normalize Arabic ي/ك, digit variants,
zero-width characters, and repeated whitespace.

## Runtime

`GET /health` reports process liveness. `GET /health/ready` queries PostgreSQL;
database failure returns 503 without connection details. Production disables
`/docs`, `/redoc`, and `/openapi.json`. CORS accepts only exact configured frontend
origins with credentials and the documented CSRF/request-ID headers.

See `.env.example` for configuration. Required signing, CSRF, and SMS-digest secrets
must be independent and at least 32 characters. Fixed SMS mode is development-only.
# POS API contracts

POS uses the same `/api/v1` prefix, role scope, error envelope, pagination, and
Jalali date types. See [POS management](pos.md) for the schema and configuration.
