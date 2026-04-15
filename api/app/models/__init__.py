# api/app/models/__init__.py — Importación centralizada de todos los modelos
# Importar aquí todos los modelos para que Alembic y SQLAlchemy los detecten

from api.app.models.base import Base, BaseModel
from api.app.models.channel import Channel, ChannelStatus
from api.app.models.message import Message, MessageStatus, MessageType
from api.app.models.chat import Chat
from api.app.models.contact import Contact
from api.app.models.group import Group
from api.app.models.webhook import Webhook
from api.app.models.webhook_log import WebhookLog
from api.app.models.media import Media
from api.app.models.api_key import ApiKey

__all__ = [
    "Base",
    "BaseModel",
    "Channel",
    "ChannelStatus",
    "Message",
    "MessageStatus",
    "MessageType",
    "Chat",
    "Contact",
    "Group",
    "Webhook",
    "WebhookLog",
    "Media",
    "ApiKey",
]
