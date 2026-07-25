from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import CurrentUser, get_current_user
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
    normalize_phone,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authenticate(
    password: str,
    db: Session,
    *,
    email: str | None = None,
    phone: str | None = None,
) -> TokenResponse:
    """Validate credentials and issue the token shared by JSON and OAuth2 login."""
    if email is not None:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
    elif phone is not None:
        user = db.query(User).filter(User.phone == phone).first()
    else:  # Defensive: LoginRequest already rejects this state.
        raise _invalid_credentials()

    if not user or not verify_password(password, user.hashed_password):
        raise _invalid_credentials()
    return TokenResponse(
        access_token=create_access_token(user.email),
        role=user.role,
        full_name=user.full_name,
        email=user.email,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    if payload.phone and db.query(User).filter(User.phone == payload.phone).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        is_verified=True,  # auto-verify in the demo
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        access_token=create_access_token(user.email),
        role=user.role,
        full_name=user.full_name,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """JSON login by email or phone, used by the mobile client."""
    return _authenticate(
        payload.password,
        db,
        email=str(payload.email) if payload.email is not None else None,
        phone=payload.phone,
    )


@router.post("/token", response_model=TokenResponse)
def oauth2_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 password-form login used by Swagger UI.

    Enter the account email or phone in Swagger's ``username`` field. Swagger
    stores the returned JWT and sends it to every protected endpoint.
    """
    identifier = form.username.strip()
    if "@" in identifier:
        return _authenticate(form.password, db, email=identifier)
    try:
        phone = normalize_phone(identifier)
    except ValueError:
        raise _invalid_credentials()
    return _authenticate(form.password, db, phone=phone)


@router.get("/me", response_model=UserResponse)
def me(current: User = Depends(get_current_user)):
    return current


@router.put("/me", response_model=UserResponse)
def update_profile(
    payload: UpdateProfileRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.full_name is not None:
        current.full_name = payload.full_name
    if payload.phone is not None:
        current.phone = payload.phone
    db.commit()
    db.refresh(current)
    return current
