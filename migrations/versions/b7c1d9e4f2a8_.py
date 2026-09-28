"""add MQTT to targettosendenum and commandstatusenum

Revision ID: b7c1d9e4f2a8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-15 16:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b7c1d9e4f2a8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

def upgrade():
    # PostgreSQL specific enum alteration
    # PG 12+ 는 트랜잭션 안에서 ADD VALUE 가 허용된다.
    # (추가한 값을 같은 트랜잭션에서 사용하는 것만 금지된다)
    op.execute("ALTER TYPE targettosendenum ADD VALUE IF NOT EXISTS 'MQTT'")
    op.execute("ALTER TYPE commandstatusenum ADD VALUE IF NOT EXISTS 'MQTT'")
    op.execute("ALTER TYPE commandstatusenum ADD VALUE IF NOT EXISTS 'MQTT_FAILED'")

def downgrade():
    # PostgreSQL doesn't easily support dropping an enum value.
    pass
