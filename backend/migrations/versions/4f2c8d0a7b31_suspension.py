"""停權：users.suspended_at / users.suspended_reason

站務處置違規帳號用。以「時間欄位是否為 NULL」判斷是否停權，而不是另開布林旗標——
時間本身就是審計紀錄，一欄兩用不必對齊兩個欄位。既有帳號補欄位時帶 server_default。

Revision ID: 4f2c8d0a7b31
Revises: 1a95b7066213
Create Date: 2026-09-29 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f2c8d0a7b31'
down_revision: Union[str, Sequence[str], None] = '1a95b7066213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns() -> set[str]:
    """已經在 users 表上的欄位。

    舊庫走 `app.db.ensure_schema()` 補欄位時，會先把結構追平再標記版本，
    這時欄位已經存在、遷移卻還沒跑過。不先探測就 ADD COLUMN 會撞
    `duplicate column name`，整個服務起不來，所以這裡必須可重入。
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' not in set(insp.get_table_names()):
        return set()
    return {col['name'] for col in insp.get_columns('users')}


def upgrade() -> None:
    """Upgrade schema."""
    present = _existing_columns()
    missing = [
        name for name in ('suspended_at', 'suspended_reason') if name not in present
    ]
    if not missing:
        return
    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'suspended_at' in missing:
            batch_op.add_column(sa.Column('suspended_at', sa.DateTime(), nullable=True))
        if 'suspended_reason' in missing:
            batch_op.add_column(
                sa.Column('suspended_reason', sa.String(length=200), nullable=False, server_default='')
            )


def downgrade() -> None:
    """Downgrade schema."""
    present = _existing_columns()
    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'suspended_reason' in present:
            batch_op.drop_column('suspended_reason')
        if 'suspended_at' in present:
            batch_op.drop_column('suspended_at')
