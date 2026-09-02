"""Initial jobs / events / meta schema (matches pre-Alembic SqlAlchemyStateStore).

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-08-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=True),
        sa.Column("running_started_at", sa.String(), nullable=True),
        sa.Column("run_seconds", sa.Float(), nullable=True),
        sa.Column("folder_label", sa.Text(), nullable=True),
        sa.Column("preview_json", sa.Text(), nullable=True),
        sa.Column("source_job_id", sa.String(), nullable=True),
        sa.Column("parent_job_id", sa.String(), nullable=True),
        sa.Column("scrape_url", sa.Text(), nullable=True),
        sa.Column("scrape_headers_json", sa.Text(), nullable=True),
        sa.Column("job_number", sa.Integer(), nullable=True),
        sa.Column(
            "auto_publish",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("import_origin", sa.String(), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column(
            "user_edited",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "meta",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column(
            "message",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "current",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("audience", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_events_job_id", "events", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_events_job_id", table_name="events")
    op.drop_table("events")
    op.drop_table("meta")
    op.drop_table("jobs")
