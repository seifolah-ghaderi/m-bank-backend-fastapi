from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import CommitRejection, DomainError


class Database:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self):
        await self.engine.dispose()


def integrity_error(error: IntegrityError) -> DomainError:
    known = {
        "uq_users_one_manager_per_branch": "branch_already_has_manager",
        "uq_users_mobile": "mobile_in_use",
        "uq_users_national_code": "national_code_in_use",
        "uq_cities_name": "city_name_in_use",
        "uq_branches_code": "branch_code_in_use",
        "uq_branches_city_name": "branch_name_in_use",
        "uq_pos_devices_number": "device_number_in_use",
        "uq_pos_visits_open": "device_has_open_visit",
        "ex_pos_transactions_period": "overlapping_period",
        "ex_pos_device_branch_history_period": "overlapping_period",
        "ex_pos_device_owner_history_period": "overlapping_period",
        "uq_pos_tags_code": "tag_code_in_use",
    }
    # Inspect only internally; database messages and parameters never reach the client.
    for constraint, code in known.items():
        if constraint in str(error.orig):
            return DomainError(409, code)
    return DomainError(409, "data_conflict")


@asynccontextmanager
async def transaction(database):
    async with database.sessions() as session:
        try:
            yield session
            await session.commit()
        except CommitRejection as rejection:
            await session.commit()
            raise rejection.error from None
        except IntegrityError as error:
            await session.rollback()
            raise integrity_error(error) from None
        except BaseException:
            await session.rollback()
            raise


async def get_session(request: Request):
    async with transaction(request.app.state.database) as session:
        yield session
