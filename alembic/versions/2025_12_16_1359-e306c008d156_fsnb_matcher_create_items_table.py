"""fsnb_matcher: create items table

Revision ID: e306c008d156
Revises: 940ec7a6bbce
Create Date: 2025-12-16 13:59:24.374547

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e306c008d156"
down_revision: Union[str, Sequence[str], None] = "940ec7a6bbce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.UniqueConstraint("code", name="uq_items_code"),
        sa.CheckConstraint("type IN ('work','resource')", name="chk_items_type"),
    )
    op.create_index(op.f("ix_items_name"), "items", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_items_name"), table_name="items")
    op.drop_table("items")