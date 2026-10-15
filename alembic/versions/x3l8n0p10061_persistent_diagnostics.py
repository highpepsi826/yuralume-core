"""Add diagnostic-owned event retention and serialized quota accounting."""
from alembic import op
import sqlalchemy as sa

revision = 'x3l8n0p10061'
down_revision = 'w2k7m9n10060'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('diagnostic_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('level', sa.String(16), nullable=False),
        sa.Column('character_id', sa.String(64)),
        sa.Column('conversation_id', sa.String(64)),
        sa.Column('request_id', sa.String(128)),
        sa.Column('details_json', sa.Text(), nullable=False),
        sa.Column('logical_bytes', sa.Integer(), nullable=False),
    )
    for column in ('created_at', 'expires_at', 'character_id'):
        op.create_index(f'ix_diagnostic_events_{column}', 'diagnostic_events', [column])
    op.create_table('diagnostic_quota',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('logical_bytes', sa.BigInteger(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('dropped_count', sa.BigInteger(), nullable=False),
        sa.Column('persist_failed_count', sa.BigInteger(), nullable=False),
        sa.Column('last_persisted_at', sa.DateTime(timezone=True)),
        sa.Column('housekeeping_json', sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table('diagnostic_quota')
    op.drop_table('diagnostic_events')
