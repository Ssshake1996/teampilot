from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
