"""Persist the chosen source language on briefs and collection jobs."""
import sqlalchemy as sa
from alembic import op

revision = '20260930_search_language'
down_revision = '20260927_collection'
branch_labels = None
depends_on = None

def upgrade():
    for table in ('research_requests', 'collection_jobs'):
        op.add_column(table, sa.Column('search_language', sa.String(10), nullable=False, server_default='auto'))

def downgrade():
    for table in ('collection_jobs', 'research_requests'):
        op.drop_column(table, 'search_language')
