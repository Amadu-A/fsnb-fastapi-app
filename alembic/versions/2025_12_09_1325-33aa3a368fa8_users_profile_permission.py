# /alembic/versions/2025_12_09_1325-33aa3a368fa8_users_profile_permission.py
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "33aa3a368fa8"
down_revision = "cff667a73384"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return insp.has_table(name)

    def has_column(table: str, column: str) -> bool:
        try:
            return column in {c["name"] for c in insp.get_columns(table)}
        except Exception:
            return False

    # --- USERS ---
    if not has_table("users"):
        # создаём таблицу users с актуальной структурой
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("username", sa.String(length=64), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("activation_key", sa.String(length=64), nullable=True),
            sa.Column("activation_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("foo", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bar", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("email", name="uq_users_email"),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
    else:
        # добавляем недостающие колонки по одной
        if not has_column("users", "email"):
            op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
            # бэкофилл email -> NOT NULL -> UNIQUE
            bind.execute(
                sa.text(
                    """
                    UPDATE users
                    SET email = COALESCE(
                        email,
                        CASE
                            WHEN username IS NOT NULL AND username <> '' THEN username || '@local.invalid'
                            ELSE 'user_' || id::text || '@local.invalid'
                        END
                    )
                    """
                )
            )
            op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=False)
            # создаём уникальный констрейнт, если его нет
            uqs = insp.get_unique_constraints("users")
            if "uq_users_email" not in {uq["name"] for uq in uqs}:
                op.create_unique_constraint("uq_users_email", "users", ["email"])

        if not has_column("users", "username"):
            op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
            uqs = insp.get_unique_constraints("users")
            if "uq_users_username" not in {uq["name"] for uq in uqs}:
                op.create_unique_constraint("uq_users_username", "users", ["username"])

        if not has_column("users", "hashed_password"):
            op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=True))
        if not has_column("users", "is_active"):
            op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if not has_column("users", "activation_key"):
            op.add_column("users", sa.Column("activation_key", sa.String(length=64), nullable=True))
        if not has_column("users", "activation_sent_at"):
            op.add_column("users", sa.Column("activation_sent_at", sa.DateTime(timezone=True), nullable=True))
        if not has_column("users", "foo"):
            op.add_column("users", sa.Column("foo", sa.Integer(), nullable=False, server_default="0"))
        if not has_column("users", "bar"):
            op.add_column("users", sa.Column("bar", sa.Integer(), nullable=False, server_default="0"))

    # --- PROFILES ---
    if not has_table("profiles"):
        op.create_table(
            "profiles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("nickname", sa.String(length=64), nullable=True),
            sa.Column("avatar", sa.String(length=255), nullable=True),
            sa.Column("first_name", sa.String(length=48), nullable=True),
            sa.Column("second_name", sa.String(length=48), nullable=True),
            sa.Column("phone", sa.String(length=32), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("tg_id", sa.BigInteger(), nullable=True),
            sa.Column("tg_nickname", sa.String(length=64), nullable=True),
            sa.Column("verification", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("session", sa.String(length=255), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_profiles_user_id"),
        )

    # --- PERMISSIONS ---
    if not has_table("permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_updater", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_reader", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_user", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return insp.has_table(name)

    def has_uc(table: str, name: str) -> bool:
        return name in {uc["name"] for uc in insp.get_unique_constraints(table)}

    # порядок важен: сначала зависимые
    if has_table("permissions"):
        op.drop_table("permissions")
    if has_table("profiles"):
        op.drop_table("profiles")

    if has_table("users"):
        # мягкий откат: уберем констрейнты и колонки, которые добавляли
        if has_uc("users", "uq_users_email"):
            op.drop_constraint("uq_users_email", "users", type_="unique")
        if has_uc("users", "uq_users_username"):
            op.drop_constraint("uq_users_username", "users", type_="unique")

        cols = {c["name"] for c in insp.get_columns("users")}
        for col in ("activation_sent_at", "activation_key", "is_active", "hashed_password", "email", "username", "foo", "bar"):
            if col in cols:
                op.drop_column("users", col)
