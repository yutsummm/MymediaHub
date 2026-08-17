
from pydantic import BaseModel


class MediaItem(BaseModel):
    url: str
    type: str
    filename: str


class PostCreate(BaseModel):
    title: str
    content: str
    status: str = "draft"
    platforms: list[str] = ["vk"]
    tags: list[str] = []
    scheduled_at: str | None = None
    template_type: str | None = None
    author_id: int = 1
    media: list[MediaItem] = []
    location_address: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    # Когда убрать запись из соцсети. Анонс прошедшего мероприятия
    # висит в ленте и путает людей.
    auto_delete_at: str | None = None


class PostUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None
    platforms: list[str] | None = None
    tags: list[str] | None = None
    scheduled_at: str | None = None
    media: list[MediaItem] | None = None
    location_address: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    # Когда убрать запись из соцсети. Анонс прошедшего мероприятия
    # висит в ленте и путает людей.
    auto_delete_at: str | None = None


class PostQueue(BaseModel):
    """Постановка поста в очередь по расписанию группы."""
    auto_delete_at: str | None = None


class ReviewReject(BaseModel):
    # Возврат без причины бесполезен: автор увидит «доработайте» и не узнает,
    # что именно не так.
    comment: str


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
    # Регистрация по ссылке-приглашению: сразу вводит в нужную группу с нужной
    # ролью. Без токена пользователь не попадает ни в одну чужую группу.
    invite_token: str | None = None


class VerifyEmailRequest(BaseModel):
    email: str
    code: str


class ResendCodeRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class UserCreate(BaseModel):
    name: str
    email: str
    # Глобальная роль: admin | member. Права на контент задаются внутри группы.
    role: str = "member"
    password: str


class GroupCreate(BaseModel):
    name: str
    description: str = ""


class SlotItem(BaseModel):
    # 0 — понедельник, как у datetime.weekday()
    weekday: int
    at: str


class SlotsUpdate(BaseModel):
    """
    Расписание заменяется целиком: человек воспринимает его как одну вещь —
    сетку недели — и правит тоже целиком.
    """
    slots: list[SlotItem] = []


class HashtagSet(BaseModel):
    name: str
    tags: str


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    avatar: str | None = None
    # Выходят ли посты только после визы администратора группы.
    require_approval: bool | None = None
    # Размечать ли ссылки UTM-метками на выпуске.
    utm_enabled: bool | None = None
    # Подстановки {{ключ}} в тексте поста и именованные наборы хештегов.
    variables: dict[str, str] | None = None
    hashtag_sets: list[HashtagSet] | None = None


class GroupMemberRoleUpdate(BaseModel):
    role: str


class InviteLinkCreate(BaseModel):
    role: str = "editor"
    expires_hours: int = 24
    max_uses: int | None = None
