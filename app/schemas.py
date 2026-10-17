"""Pydantic request/response schemas."""
from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# Trims whitespace first, so "   " is rejected as empty.
Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SignupRequest(BaseModel):
    name: Text100
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class ClassCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: Text100
    dateTime: datetime = Field(description="ISO 8601. Naive values are treated as IST.")
    instructor: Text100
    availableSlots: int = Field(ge=0, le=10_000)


class ClassOut(BaseModel):
    id: int
    name: str
    dateTime: datetime
    instructor: str
    availableSlots: int


class BookRequest(BaseModel):
    class_id: int
    client_name: Text100
    client_email: EmailStr


class BookingOut(BaseModel):
    id: int
    class_id: int
    class_name: str
    instructor: str
    dateTime: datetime
    client_name: str
    client_email: EmailStr
    booked_at: datetime

