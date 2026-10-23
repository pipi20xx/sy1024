from typing import Optional
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str
    otp_code: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    status: str = "success"

class TwoFactorSetupResponse(BaseModel):
    secret: str
    qr_code: str

class UserInfoResponse(BaseModel):
    username: str
    is_otp_enabled: bool
    last_login: Optional[str] = None
