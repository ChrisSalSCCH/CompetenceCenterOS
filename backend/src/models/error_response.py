"""RFC 7807 Problem Details error response models."""

from pydantic import BaseModel

# RFC 7807 default problem type used when no specific type URI applies.
DEFAULT_PROBLEM_TYPE = "about:blank"


class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details response."""

    type: str = DEFAULT_PROBLEM_TYPE
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "type": DEFAULT_PROBLEM_TYPE,
                "title": "Not Found",
                "status": 404,
                "detail": "The requested resource was not found.",
                "instance": "/api/v1/users/123",
            }
        }


class FieldValidationError(BaseModel):
    """Validation error detail. Renamed from ValidationError to avoid shadowing
    pydantic.ValidationError in user code."""

    loc: list[str]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    type: str = DEFAULT_PROBLEM_TYPE
    title: str = "Validation Error"
    status: int = 422
    detail: str = "Request validation failed"
    errors: list[FieldValidationError]
