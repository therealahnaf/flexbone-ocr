from typing import Literal

from pydantic import BaseModel


class ErrorDetailSchema(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorDetailSchema
    request_id: str


class BatchItemErrorResponse(ErrorResponse):
    filename: str
