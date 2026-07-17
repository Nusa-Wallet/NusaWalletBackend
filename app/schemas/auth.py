import re

from pydantic import BaseModel, EmailStr, field_validator, model_validator


def normalize_phone(value: str) -> str:
    """Normalize common Indonesian mobile formats to the canonical ``08...`` form."""
    raw = value.strip()
    if not raw or not re.fullmatch(r"[+\d\s().-]+", raw):
        raise ValueError("Invalid phone number")

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("62"):
        digits = f"0{digits[2:]}"
    elif digits.startswith("8"):
        digits = f"0{digits}"

    if not digits.startswith("08") or not 10 <= len(digits) <= 15:
        raise ValueError("Phone number must be an Indonesian mobile number")
    return digits


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    phone: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None


class LoginRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @model_validator(mode="after")
    def require_exactly_one_identifier(self):
        if (self.email is None) == (self.phone is None):
            raise ValueError("Provide exactly one of email or phone")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    is_verified: bool

    model_config = {"from_attributes": True}
