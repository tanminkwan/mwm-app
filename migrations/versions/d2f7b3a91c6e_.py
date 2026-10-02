"""add mw_ssl_cert_file (HOWTO_021)

Revision ID: d2f7b3a91c6e
Revises: c4e8a2f19d3b
Create Date: 2026-10-01 15:00:00.000000

운영은 flask db upgrade 를 쓰지 않는다 — docs/sql/20261001_add_mw_ssl_cert_file.sql 로 같은 변경을 한다.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd2f7b3a91c6e'
down_revision = 'c4e8a2f19d3b'
branch_labels = None
depends_on = None

CERT_TYPE = sa.Enum('LEAF', 'CA', name='sslcerttypeenum')


def upgrade():
    op.create_table(
        'mw_ssl_cert_file',
        sa.Column('id', sa.Integer(), nullable=False, comment='Primary Key'),
        sa.Column('cert_name', sa.String(length=30), nullable=False, comment='이름 (UTF-8 30byte 이내)'),
        sa.Column('ag_file_id', sa.Integer(), nullable=True, comment='원본 파일'),
        sa.Column('file_name', sa.String(length=50), nullable=False, comment='등록 시점의 파일 이름'),
        sa.Column('received_date', sa.Date(), nullable=False, comment='접수일'),
        sa.Column('receiver_name', sa.String(length=50), nullable=False, comment='접수자 이름'),
        sa.Column('cert_type', CERT_TYPE, nullable=False, comment='Leaf/중간 CA'),
        sa.Column('subject', sa.String(length=300), nullable=True, comment='주제'),
        sa.Column('cn', sa.String(length=200), nullable=True, comment='CN'),
        sa.Column('serial', sa.String(length=100), nullable=True, comment='일련번호'),
        sa.Column('issuer', sa.String(length=300), nullable=True, comment='발급자'),
        sa.Column('notbefore', sa.DateTime(), nullable=True, comment='유효기간시작'),
        sa.Column('notafter', sa.DateTime(), nullable=True, comment='유효기간만료'),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('create_on', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ag_file_id'], ['ag_file.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cert_name'),
        comment='SSL 인증서 파일 (HOWTO_021)',
    )


def downgrade():
    op.drop_table('mw_ssl_cert_file')
    CERT_TYPE.drop(op.get_bind(), checkfirst=True)
