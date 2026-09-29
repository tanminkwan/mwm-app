"""add ag_agent MQTT status columns (HOWTO_019)

Revision ID: c4e8a2f19d3b
Revises: b7c1d9e4f2a8
Create Date: 2026-09-29 15:30:00.000000

운영은 flask db upgrade 를 쓰지 않는다 — docs/sql/20260929_add_agent_mqtt_status.sql 로 같은 변경을 한다.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4e8a2f19d3b'
down_revision = 'b7c1d9e4f2a8'
branch_labels = None
depends_on = None

COLUMNS = [
    ('mqtt_state', sa.String(length=20)),
    ('mqtt_since', sa.DateTime()),
    ('mqtt_events', sa.Integer()),
    ('mqtt_last_msg', sa.DateTime()),
    ('mqtt_reason', sa.String(length=120)),
    ('mqtt_raw', sa.String(length=300)),
]


def upgrade():
    with op.batch_alter_table('ag_agent') as batch_op:
        for name, type_ in COLUMNS:
            comment = 'MQTT 수신 상태 (X-Mqtt-Status). NULL = MQTT 비대상' if name == 'mqtt_state' else None
            batch_op.add_column(sa.Column(name, type_, nullable=True, comment=comment))


def downgrade():
    with op.batch_alter_table('ag_agent') as batch_op:
        for name, _ in reversed(COLUMNS):
            batch_op.drop_column(name)
