from __future__ import annotations

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.passwords import hash_password
from app.db.models import User, UserRole
from app.db.session import get_engine, get_sessionmaker


async def create_user(email: str, role: UserRole, password: str) -> None:
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            existing = await session.scalar(select(User.id).where(User.email == email))
            if existing is not None:
                raise ValueError("A user with that email already exists.")
            display_name = email.partition("@")[0].replace(".", " ").title()
            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    display_name=display_name,
                    role=role,
                )
            )
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise ValueError("A user with that email already exists.") from error
    finally:
        await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create_user_command = commands.add_parser("create-user")
    create_user_command.add_argument("--email", required=True)
    create_user_command.add_argument("--role", choices=[role.value for role in UserRole], required=True)
    arguments = parser.parse_args()

    password = getpass("Password (minimum 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12:
        parser.error("Password must be at least 12 characters.")
    if password != confirmation:
        parser.error("Passwords do not match.")

    try:
        asyncio.run(
            create_user(
                arguments.email.strip(),
                UserRole(arguments.role),
                password,
            )
        )
    except ValueError as error:
        parser.error(str(error))
    print(f"Created {arguments.role} account for {arguments.email}.")


if __name__ == "__main__":
    main()
