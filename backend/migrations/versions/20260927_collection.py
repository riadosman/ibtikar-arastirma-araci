"""Persistent collection jobs and source evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260927_collection"
down_revision = "72adee572c55"
branch_labels = None
depends_on = None


def identity():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
    ]


def upgrade():
    op.create_table(
        "collection_jobs",
        *identity(),
        sa.Column(
            "research_request_id",
            sa.String(36),
            sa.ForeignKey("research_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("discovered", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("merged_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
    )
    op.create_index(
        "ix_collection_jobs_research_request_id", "collection_jobs", ["research_request_id"]
    )
    op.create_index("ix_collection_jobs_status", "collection_jobs", ["status"])
    op.create_table(
        "source_documents",
        *identity(),
        sa.Column(
            "collection_job_id",
            sa.String(36),
            sa.ForeignKey("collection_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error", sa.String(200)),
        sa.Column("content_hash", sa.String(64)),
    )
    op.create_index(
        "ix_source_documents_collection_job_id", "source_documents", ["collection_job_id"]
    )


def downgrade():
    op.drop_table("source_documents")
    op.drop_table("collection_jobs")
