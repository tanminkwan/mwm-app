"""add LogExtractor

Revision ID: a1b2c3d4e5f6
Revises: 8929a1afeddb
Create Date: 2026-08-26 14:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '8929a1afeddb'
branch_labels = None
depends_on = None

def upgrade():
    # PostgreSQL specific enum alteration
    op.execute("ALTER TYPE commandclassenum ADD VALUE IF NOT EXISTS 'ExtractLog'")

def downgrade():
    # PostgreSQL doesn't easily support dropping an enum value.
    pass
