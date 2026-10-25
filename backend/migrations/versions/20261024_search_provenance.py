"""Search provenance on sources and requirement decisions on candidates.

Additive only: existing rows keep their data; new columns are nullable or get safe defaults.
Plain ADD COLUMN (no table rebuild), so SQLite keeps the candidates' unnamed CHECK constraints.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261024_search_provenance"
down_revision = "20261008_hardening"
branch_labels = None
depends_on = None

SOURCE_COLUMNS = ("query", "engine", "rank", "page_kind", "priority")


def upgrade():
    op.add_column("source_documents", sa.Column("query", sa.Text()))
    op.add_column("source_documents", sa.Column("engine", sa.String(30)))
    op.add_column("source_documents", sa.Column("rank", sa.Integer()))
    op.add_column("source_documents", sa.Column("page_kind", sa.String(30)))
    op.add_column("source_documents", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("candidates", sa.Column("match_details", sa.JSON(), nullable=False,
                                          server_default=sa.text("'{}'")))
    if op.get_bind().dialect.name != "sqlite":
        # The application always writes the column; SQLite cannot drop a default in place.
        op.alter_column("candidates", "match_details", server_default=None)


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 3.35+ drops columns in place; a batch rebuild would lose CHECK constraints.
        op.execute("ALTER TABLE candidates DROP COLUMN match_details")
        for column in reversed(SOURCE_COLUMNS):
            op.execute(f"ALTER TABLE source_documents DROP COLUMN {column}")
        return
    op.drop_column("candidates", "match_details")
    for column in reversed(SOURCE_COLUMNS):
        op.drop_column("source_documents", column)
