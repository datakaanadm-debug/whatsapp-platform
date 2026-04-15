"""initial_schema

Revision ID: 28ac095376f6
Revises:
Create Date: 2026-04-14

Esquema inicial de la plataforma WhatsApp API.
Crea todas las tablas del sistema: channels, messages, chats, contacts,
groups, webhooks, media, api_keys, webhook_logs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '28ac095376f6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Tabla: channels ──────────────────────────────────────────
    op.create_table(
        'channels',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone_number', sa.String(50), nullable=True),
        sa.Column('status', sa.String(12), nullable=False, server_default='disconnected'),
        sa.Column('api_key', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('webhook_url', sa.Text, nullable=True),
        sa.Column('webhook_events', sa.JSON, nullable=True),
        sa.Column('settings', sa.JSON, nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: api_keys ──────────────────────────────────────────
    op.create_table(
        'api_keys',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=True),
        sa.Column('key_hash', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('prefix', sa.String(8), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('scopes', sa.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: chats ─────────────────────────────────────────────
    op.create_table(
        'chats',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chat_id_wa', sa.String(255), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('is_group', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_archived', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_pinned', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_muted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('unread_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: contacts ──────────────────────────────────────────
    op.create_table(
        'contacts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('contact_id_wa', sa.String(255), nullable=False, index=True),
        sa.Column('phone_number', sa.String(50), nullable=True, index=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('push_name', sa.String(255), nullable=True),
        sa.Column('business_name', sa.String(255), nullable=True),
        sa.Column('profile_pic_url', sa.Text, nullable=True),
        sa.Column('is_business', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_blocked', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: groups ────────────────────────────────────────────
    op.create_table(
        'groups',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('group_id_wa', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('owner', sa.String(255), nullable=True),
        sa.Column('participants', sa.JSON, nullable=True),
        sa.Column('admins', sa.JSON, nullable=True),
        sa.Column('invite_link', sa.Text, nullable=True),
        sa.Column('profile_pic_url', sa.Text, nullable=True),
        sa.Column('settings', sa.JSON, nullable=True),
        sa.Column('created_at_wa', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: messages ──────────────────────────────────────────
    op.create_table(
        'messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chat_id', sa.String(255), nullable=False, index=True),
        sa.Column('message_id_wa', sa.String(255), nullable=True, unique=True, index=True),
        sa.Column('sender', sa.String(255), nullable=False),
        sa.Column('recipient', sa.String(255), nullable=False),
        sa.Column('type', sa.String(11), nullable=False, server_default='text'),
        sa.Column('content', sa.JSON, nullable=True),
        sa.Column('status', sa.String(9), nullable=False, server_default='pending'),
        sa.Column('is_from_me', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_forwarded', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('quoted_message_id', sa.String(255), nullable=True),
        sa.Column('media_url', sa.Text, nullable=True),
        sa.Column('media_mime_type', sa.String(127), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: webhooks ──────────────────────────────────────────
    op.create_table(
        'webhooks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('events', sa.JSON, nullable=False),
        sa.Column('secret', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: media ─────────────────────────────────────────────
    op.create_table(
        'media',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', UUID(as_uuid=True), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('media_key', sa.String(255), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('mime_type', sa.String(127), nullable=True),
        sa.Column('file_size', sa.BigInteger, nullable=True),
        sa.Column('storage_path', sa.Text, nullable=True),
        sa.Column('url', sa.Text, nullable=True),
        sa.Column('sha256', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Tabla: webhook_logs ──────────────────────────────────────
    op.create_table(
        'webhook_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('webhook_id', UUID(as_uuid=True), sa.ForeignKey('webhooks.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('event_type', sa.String(100), nullable=False, index=True),
        sa.Column('payload', sa.JSON, nullable=True),
        sa.Column('status_code', sa.Integer, nullable=True),
        sa.Column('response_body', sa.Text, nullable=True),
        sa.Column('attempt', sa.Integer, nullable=False, server_default='1'),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('webhook_logs')
    op.drop_table('media')
    op.drop_table('webhooks')
    op.drop_table('messages')
    op.drop_table('groups')
    op.drop_table('contacts')
    op.drop_table('chats')
    op.drop_table('api_keys')
    op.drop_table('channels')
