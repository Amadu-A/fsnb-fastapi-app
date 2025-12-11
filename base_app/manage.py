# /base_app/manage.py
from __future__ import annotations

import argparse
import asyncio
from getpass import getpass

from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models import db_helper
from base_app.scripts.superuser import create_superuser

log = get_logger("manage")


async def _cmd_create_superuser() -> None:
    print("Create superuser")
    username = input("Username: ").strip()
    password = getpass("Password: ")
    email = input("E-mail (optional): ").strip()

    async with db_helper.session_factory() as session:  # type: AsyncSession
        uid = await create_superuser(session, username=username, password=password, email=email or None)
        await session.commit()
        log.info({"event": "create_superuser_ok", "user_id": uid, "username": username})
        print(f"✔ Superuser created: id={uid}, username={username}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="base_app.manage", description="Management commands")
    parser.add_argument("--create_superuser", action="store_true", help="Create a superuser")
    args = parser.parse_args(argv)

    if args.create_superuser:
        asyncio.run(_cmd_create_superuser())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
