from typing import Optional
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    reset_required: bool = False
    reset_token: Optional[str] = None

class PasswordResetRequest(BaseModel):
    reset_token: str
    password: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None
