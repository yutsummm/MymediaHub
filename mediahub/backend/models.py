from pydantic import BaseModel
from typing import Optional, List


class MediaItem(BaseModel):
    url: str
    type: str
    filename: str


class PostCreate(BaseModel):
    title: str
    content: str
    status: str = "draft"
    platforms: List[str] = ["vk"]
    tags: List[str] = []
    scheduled_at: Optional[str] = None
    template_type: Optional[str] = None
    author_id: int = 1
    media: List[MediaItem] = []
    location_address: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None


class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    platforms: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    scheduled_at: Optional[str] = None
    media: Optional[List[MediaItem]] = None
    location_address: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None


class GenerateRequest(BaseModel):
    template_type: str
    fields: dict


class UserUpdate(BaseModel):
    role: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AIEnhanceRequest(BaseModel):
    text: str
    mode: str


class VkSettingsSave(BaseModel):
    group_id: str
    access_token: str


class TgSettingsSave(BaseModel):
    bot_token: str
    chat_id: str


class VkOAuthExchange(BaseModel):
    app_id: str
    app_secret: str
    code: str
    group_id: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class UserCreate(BaseModel):
    name: str
    email: str
    role: str = "editor"
    password: str


class GroupCreate(BaseModel):
    name: str
    description: str = ""


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar: Optional[str] = None


class GroupMemberRoleUpdate(BaseModel):
    role: str


class InviteLinkCreate(BaseModel):
    role: str = "editor"
    expires_hours: int = 24
    max_uses: Optional[int] = None
