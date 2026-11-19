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
from app.models import ImportLog, LoginChallenge, RefreshToken, User
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


async def fail_stale_pos_imports(
    database, settings, older_than_minutes, *, apply=False, confirm_no_active_imports=False
):
    if older_than_minutes < 1:
        raise ValueError("older-than-minutes must be positive")
    if apply and not confirm_no_active_imports:
        raise ValueError("Confirm no active imports with --confirm-no-active-imports")
    async with transaction(database) as session:
        # A live importer holds its log row lock; never change its status here.
        logs = list(
            await session.scalars(
                select(ImportLog)
                .where(
                    ImportLog.status == "processing",
                    ImportLog.started_at < dates.now() - timedelta(minutes=older_than_minutes),
                )
                .with_for_update(skip_locked=True)
            )
        )
        keys = set(await session.scalars(select(ImportLog.storage_key)))
        root = settings.import_storage_dir.resolve()
        orphans = sorted(p.name for p in root.glob("*.xlsx") if p.is_file() and p.name not in keys)
        ids = [str(log.id) for log in logs]
        if apply:
            for log in logs:
                log.status, log.finished_at = "failed", dates.now()
                log.success_count = log.created_count = log.updated_count = log.unchanged_count = (
                    log.skipped_count
                ) = 0
                log.failure_count = log.total_rows
                log.component_counts = {}
                log.warnings = [{"code": "interrupted_processing"}]
                record(
                    session,
                    None,
                    "recover_import",
                    "import_logs",
                    log.id,
                    after={"status": "failed"},
                )
        return {"apply": apply, "stale_import_ids": ids, "orphan_files": orphans}


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
        elif args.command == "purge-tokens":
            tokens, challenges = await purge_tokens(database)
            print(f"Purged {tokens} old refresh tokens and {challenges} old challenges.")
        elif args.command == "process-lead-imports":
            from app.features.crm_imports import worker

            await worker.run(database, settings, once=args.once)
        else:
            import json

            print(
                json.dumps(
                    await fail_stale_pos_imports(
                        database,
                        settings,
                        args.older_than_minutes,
                        apply=args.apply,
                        confirm_no_active_imports=args.confirm_no_active_imports,
                    )
                )
            )
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
    lead_worker = commands.add_parser("process-lead-imports")
    lead_worker.add_argument("--once", action="store_true")
    recover = commands.add_parser("fail-stale-pos-imports")
    recover.add_argument("--older-than-minutes", type=int, required=True)
    recover.add_argument("--apply", action="store_true")
    recover.add_argument("--confirm-no-active-imports", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (DomainError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
