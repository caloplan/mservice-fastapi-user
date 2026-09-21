from pydantic import BaseModel, EmailStr, Field


class EmailCodeRequest(BaseModel):
    """发送邮箱验证码请求。"""

    email: EmailStr
    scene: str = Field("register", max_length=50)


class EmailCodeVerifyRequest(BaseModel):
    """校验邮箱验证码请求。"""

    email: EmailStr
    scene: str = Field("register", max_length=50)
    code: str = Field(..., min_length=4, max_length=8, pattern=r"^\d{4,8}$")
