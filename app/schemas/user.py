from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,50}$"
PASSWORD_PATTERN = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,30}$"

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=USERNAME_PATTERN)
    email: EmailStr
    full_name: str | None = Field(None, max_length=100)
    service_name: str = Field("default", max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=30)
    code: str = Field(..., min_length=4, max_length=8, pattern=r"^\d{4,8}$", description="邮箱验证码（注册必填）")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        import re

        if not re.match(PASSWORD_PATTERN, v):
            raise ValueError("密码必须包含字母、数字和特殊字符，长度 8-30 位")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=100)
    service_name: str | None = Field(None, max_length=50)


class UserChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=30)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        import re

        if not re.match(PASSWORD_PATTERN, v):
            raise ValueError("新密码必须包含字母、数字和特殊字符，长度 8-30 位")
        return v


class UserResponse(BaseModel):
    """基础用户响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    full_name: str | None
    service_name: str
    role: str
    created_at: datetime
    updated_at: datetime | None
