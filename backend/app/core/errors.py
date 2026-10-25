"""One error shape for API callers: user-safe detail, machine code, retry hint, request ID."""

from enum import StrEnum

from app.core.logging import request_id_var


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_REQUIRED = "authentication_required"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    RATE_LIMITED = "rate_limited"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    INTERNAL_ERROR = "internal_error"
    BAD_REQUEST = "bad_request"


CODES = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.AUTHENTICATION_REQUIRED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.BAD_REQUEST,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
    502: ErrorCode.EXTERNAL_SERVICE_ERROR,
    503: ErrorCode.EXTERNAL_SERVICE_ERROR,
    504: ErrorCode.EXTERNAL_SERVICE_ERROR,
}
# Safe to repeat unchanged later. 409 conflicts resolve when the running work finishes.
RETRYABLE = {409, 429, 502, 503, 504}


def error_body(status_code, detail, code=None):
    return {
        "detail": detail,
        "code": str(code or CODES.get(status_code, ErrorCode.BAD_REQUEST)),
        "retryable": status_code in RETRYABLE,
        "request_id": request_id_var.get(),
    }
