from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None, details=None):
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()
        self.details = details or []
        super().__init__(code)


@dataclass
class Rejected:
    """An explicit security-state change that must persist before a rejection."""

    error: DomainError


class CommitRejection(Exception):
    def __init__(self, outcome: Rejected):
        self.error = outcome.error


def finish(outcome):
    if isinstance(outcome, Rejected):
        raise CommitRejection(outcome)
    return outcome


def error_response(request: Request, error: DomainError):
    return JSONResponse(
        status_code=error.status,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "request_id": request.state.request_id,
            }
        },
    )


def install_handlers(app):
    @app.exception_handler(DomainError)
    async def domain(request, error):
        return error_response(request, error)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        codes = {
            401: "invalid_credentials",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
        }
        return error_response(
            request, DomainError(error.status_code, codes.get(error.status_code, "request_error"))
        )

    @app.exception_handler(RequestValidationError)
    async def validation(request, error):
        errors = error.errors()
        if any(item["type"] == "json_invalid" for item in errors):
            return error_response(request, DomainError(400, "invalid_json"))
        details = []
        for item in errors:
            reason = str(item.get("ctx", {}).get("error", ""))
            code = (
                reason if reason in {"invalid_mobile", "invalid_national_code"} else "invalid_field"
            )
            details.append(
                {
                    "field": ".".join(map(str, item["loc"])),
                    "code": code,
                    "message": "Invalid field value",
                }
            )
        return error_response(request, DomainError(422, "validation_error", details=details))
