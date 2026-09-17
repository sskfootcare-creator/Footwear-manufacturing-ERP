"""Authentication & User Pydantic Models."""

from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator
from pydantic_core import PydanticCustomError


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "production"
    role_title: Optional[str] = None
    department: Optional[str] = "general"
    allowed_modules: Optional[List[str]] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if v is not None and len(v) < 8:
            raise PydanticCustomError(
                "string_too_short",
                "Password must be at least 8 characters long."
            )
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    role_title: Optional[str] = None
    department: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None
    allowed_modules: Optional[List[str]] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 8:
            raise PydanticCustomError(
                "string_too_short",
                "Password must be at least 8 characters long."
            )
        return v


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    new_password: str
