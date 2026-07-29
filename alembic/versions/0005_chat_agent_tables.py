"""chat agent tables

ROADMAP.md Phase 3, Step 3.3: chat threads/messages + per-user agent notes
for the "Chef" conversational agent (see `app.data.models.ChatThread`/
`ChatMessage`/`AgentNote`). Distinct from LangGraph's own checkpoint tables,
which are created by `SqliteSaver`/`PostgresSaver.setup()` and deliberately
kept OUTSIDE this app's Alembic migrations -- see
`app.graph.builder._select_checkpointer`'s docstring. `ChatThread.id`
doubles as that checkpointer's `thread_id` (namespaced via
`checkpoint_ns="chef"`), but the ownership mapping itself is this app's own
data, same as `graph_runs` (0004).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_threads',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('owner_user_id', sa.String(length=128), nullable=False),
        sa.Column('user_profile', sa.Text(), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_threads_id'), 'chat_threads', ['id'], unique=False)
    op.create_index(
        op.f('ix_chat_threads_owner_user_id'), 'chat_threads', ['owner_user_id'], unique=False
    )
    op.create_index(op.f('ix_chat_threads_is_active'), 'chat_threads', ['is_active'], unique=False)

    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tool_calls_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    op.create_index(
        op.f('ix_chat_messages_thread_id'), 'chat_messages', ['thread_id'], unique=False
    )
    op.create_index(
        op.f('ix_chat_messages_created_at'), 'chat_messages', ['created_at'], unique=False
    )

    op.create_table(
        'agent_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_notes_id'), 'agent_notes', ['id'], unique=False)
    op.create_index(op.f('ix_agent_notes_user_id'), 'agent_notes', ['user_id'], unique=False)
    op.create_index(op.f('ix_agent_notes_is_active'), 'agent_notes', ['is_active'], unique=False)
    op.create_index(
        op.f('ix_agent_notes_created_at'), 'agent_notes', ['created_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_notes_created_at'), table_name='agent_notes')
    op.drop_index(op.f('ix_agent_notes_is_active'), table_name='agent_notes')
    op.drop_index(op.f('ix_agent_notes_user_id'), table_name='agent_notes')
    op.drop_index(op.f('ix_agent_notes_id'), table_name='agent_notes')
    op.drop_table('agent_notes')

    op.drop_index(op.f('ix_chat_messages_created_at'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_thread_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_table('chat_messages')

    op.drop_index(op.f('ix_chat_threads_is_active'), table_name='chat_threads')
    op.drop_index(op.f('ix_chat_threads_owner_user_id'), table_name='chat_threads')
    op.drop_index(op.f('ix_chat_threads_id'), table_name='chat_threads')
    op.drop_table('chat_threads')
