import argparse
import asyncio
import getpass
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, text

from app.core import dates
from app.core.audit import record
from app.core.config import Settings
from app.core.db import Database, transaction
from app.core.errors import DomainError
from app.core.security import hasher, password_policy
from app.models import LoginChallenge, RefreshToken, User
from app.schemas.users import UserCreate


async def create_supervisor(database, details: UserCreate, password: str, force=False):
    password_policy(password, details.mobile)
    async with transaction(database) as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(72851901)"))
        if not force and await session.scalar(
            select(func.count()).select_from(User).where(User.role == "supervisor")
        ):
            raise DomainError(409, "supervisor_exists")
        user = User(**details.model_dump(), password_hash=hasher.hash(password))
        session.add(user)
        await session.flush()
        record(session, user, "bootstrap", "users", user.id)
        return user.id


async def purge_tokens(database):
    threshold = dates.now() - timedelta(days=30)
    async with transaction(database) as session:
        tokens = await session.execute(
            delete(RefreshToken).where(
                or_(RefreshToken.expires_at < threshold, RefreshToken.revoked_at < threshold)
            )
        )
        challenges = await session.execute(
            delete(LoginChallenge).where(
                or_(
                    LoginChallenge.expires_at < threshold,
                    LoginChallenge.consumed_at < threshold,
                    LoginChallenge.invalidated_at < threshold,
                )
            )
        )
        return tokens.rowcount, challenges.rowcount


async def run(args):
    settings = Settings()
    database = Database(settings.database_url.get_secret_value())
    try:
        if args.command == "create-supervisor":
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Confirm password: "):
                raise ValueError("Passwords do not match")
            details = UserCreate(
                first_name=args.first_name,
                last_name=args.last_name,
                mobile=args.mobile,
                role="supervisor",
            )
            user_id = await create_supervisor(database, details, password, args.force)
            print(f"Created Supervisor {user_id}; password change required on first login.")
        else:
            tokens, challenges = await purge_tokens(database)
            print(f"Purged {tokens} old refresh tokens and {challenges} old challenges.")
    finally:
        await database.close()


def main():
    parser = argparse.ArgumentParser(description="Bank CRM operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-supervisor")
    create.add_argument("--mobile", required=True)
    create.add_argument("--first-name", required=True)
    create.add_argument("--last-name", required=True)
    create.add_argument("--force", action="store_true")
    commands.add_parser("purge-tokens")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (DomainError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
