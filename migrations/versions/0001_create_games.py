"""create games table

Revision ID: 0001_create_games
Revises:
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_create_games"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("ships", sa.JSON(), nullable=False),
        sa.Column("received_shots", sa.JSON(), nullable=False),
        sa.Column("own_shots", sa.JSON(), nullable=False),
        sa.Column("pending_shot", sa.String(length=3), nullable=True),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )


def downgrade() -> None:
    op.drop_table("games")
