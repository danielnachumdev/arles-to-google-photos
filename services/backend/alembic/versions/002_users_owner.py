"""Add users table and owner_id on jobs/events for RBAC.

Hard reset only: no legacy seed user and no backfill of existing rows.
Deploy starts from an empty DB (prod migrator.sqlite wiped).

Revision ID: 002_users_owner
Revises: 001_initial_schema
Create Date: 2026-08-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_users_owner"
down_revision: Union[str, Sequence[str], None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("owner_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_jobs_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
        )
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("owner_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_events_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.drop_constraint("fk_events_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("fk_jobs_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
    op.drop_table("users")
