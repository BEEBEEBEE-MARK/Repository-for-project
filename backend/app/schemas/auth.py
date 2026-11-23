"""认证相关请求/响应模型。"""

from pydantic import BaseModel, ConfigDict


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    account: str
    password: str
    remember_me: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str


class LoginUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
