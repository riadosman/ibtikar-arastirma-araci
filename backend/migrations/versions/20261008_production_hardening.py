"""Job lifecycle (heartbeat, attempts, cancel, stats), evidence, idempotency, export resume.

Additive only: existing rows keep their data; new columns get safe defaults.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261008_hardening"
down_revision = "20260930_search_language"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("collection_jobs") as batch:
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("stats", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
    with op.batch_alter_table("collection_jobs") as batch:
        batch.alter_column("stats", server_default=None)
    # Finished jobs from earlier versions: their last update is when they finished.
    op.execute(
        "UPDATE collection_jobs SET finished_at = updated_at, started_at = created_at, attempts = 1 "
        "WHERE status NOT IN ('QUEUED', 'RUNNING')"
    )

    op.add_column("candidate_sources", sa.Column("evidence", sa.Text()))

    with op.batch_alter_table("export_jobs") as batch:
        batch.add_column(sa.Column("external_id", sa.String(200)))
        batch.add_column(sa.Column("external_url", sa.Text()))
        batch.add_column(sa.Column("idempotency_key", sa.String(200)))
        batch.create_unique_constraint("uq_export_jobs_idempotency_key", ["idempotency_key"])
    op.create_index(
        op.f("ix_export_jobs_research_request_id"), "export_jobs", ["research_request_id"]
    )

    op.create_index(op.f("ix_login_sessions_user_id"), "login_sessions", ["user_id"])
    op.create_index(op.f("ix_login_sessions_expires_at"), "login_sessions", ["expires_at"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("response", sa.JSON()),
        sa.UniqueConstraint("scope", "key"),
    )
    op.create_index(
        op.f("ix_idempotency_records_created_at"), "idempotency_records", ["created_at"]
    )


def downgrade():
    op.drop_index(op.f("ix_idempotency_records_created_at"), table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_login_sessions_expires_at"), table_name="login_sessions")
    op.drop_index(op.f("ix_login_sessions_user_id"), table_name="login_sessions")
    op.drop_index(op.f("ix_export_jobs_research_request_id"), table_name="export_jobs")
    with op.batch_alter_table("export_jobs") as batch:
        batch.drop_constraint("uq_export_jobs_idempotency_key", type_="unique")
        for column in ("idempotency_key", "external_url", "external_id"):
            batch.drop_column(column)
    op.drop_column("candidate_sources", "evidence")
    with op.batch_alter_table("collection_jobs") as batch:
        for column in (
            "stats", "finished_at", "heartbeat_at", "started_at", "cancel_requested", "attempts"
        ):
            batch.drop_column(column)
