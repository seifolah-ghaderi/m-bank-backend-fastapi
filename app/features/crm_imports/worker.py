import asyncio
import hashlib
import logging
from collections import Counter
from datetime import timedelta
from itertools import batched
from types import SimpleNamespace

from sqlalchemy import func, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as DatabaseTimeout
from starlette.concurrency import run_in_threadpool

from app.core import dates
from app.core.db import transaction
from app.core.errors import DomainError
from app.features.crm_imports import history, leads, workbooks
from app.models import CrmImport, CrmImportRow

CHUNK_SIZE = 500
WORKER_LOCK = 72851902
POLL_SECONDS = 2
RETRY_DELAYS = (timedelta(seconds=5), timedelta(seconds=30))
logger = logging.getLogger(__name__)


def read_source(settings, job):
    with history.workbook_path(settings, job.id).open("rb") as source:
        content = source.read(workbooks.max_bytes(settings, "leads") + 1)
    if hashlib.sha256(content).hexdigest() != job.file_sha256:
        raise DomainError(422, "source_checksum_mismatch")
    return workbooks.prepare(settings, "leads", job.file_name, content)


async def next_job(database):
    now = dates.now()
    async with transaction(database) as session:
        job = await session.scalar(
            select(CrmImport)
            .where(
                CrmImport.kind == "leads",
                CrmImport.status.in_(("queued", "processing")),
                or_(CrmImport.next_attempt_at.is_(None), CrmImport.next_attempt_at <= now),
            )
            .order_by(CrmImport.created_at, CrmImport.id)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "processing"
        job.next_attempt_at = None
        if job.started_at is None:
            job.started_at = now
        return job


async def process_chunk(database, job_id, rows):
    async with transaction(database) as session:
        job = await history.get_log(session, job_id)
        actor = SimpleNamespace(id=job.created_by, role="supervisor")
        counts = Counter()
        for number, outcome, error, warnings in await leads.import_leads(
            session, actor, job.id, rows
        ):
            history.add_outcome(session, job, number, outcome, error, warnings=warnings)
            counts[outcome] += 1
            if warnings:
                counts["warning_rows"] += 1
            counts.update(warnings)
        history.update_counts(job, counts)


async def process_job(database, settings, job):
    try:
        sheet = await run_in_threadpool(read_source, settings, job)
    except (DomainError, OSError) as error:
        async with transaction(database) as session:
            current = await history.get_log(session, job.id)
            history.fail(
                current, error.code if isinstance(error, DomainError) else "source_unavailable"
            )
        return

    async with database.sessions() as session:
        checkpoint = await session.scalar(
            select(func.max(CrmImportRow.row_number)).where(CrmImportRow.import_id == job.id)
        )
    # Replaying identity validation up to the checkpoint preserves the workbook's
    # duplicate detection. Only later rows are written.
    remaining = (row for row in leads.lead_rows(sheet) if checkpoint is None or row[0] > checkpoint)
    for chunk in batched(remaining, CHUNK_SIZE):
        await process_chunk(database, job.id, chunk)
    async with transaction(database) as session:
        history.finish(await history.get_log(session, job.id))


async def record_processing_error(database, job_id, error):
    async with transaction(database) as session:
        job = await history.get_log(session, job_id)
        failures = job.retry_count + 1
        job.retry_count = failures
        if failures <= len(RETRY_DELAYS):
            job.next_attempt_at = dates.now() + RETRY_DELAYS[failures - 1]
        else:
            history.fail(job, "processing_error")
    # SQL exceptions can contain workbook values. Log the error type and import ID.
    logger.warning(
        "Lead import %s attempt %s errored (%s), next attempt at %s, status %s",
        job_id,
        failures,
        type(error).__name__,
        job.next_attempt_at,
        job.status,
    )


async def run_one(database, settings):
    # Hold this transaction on its own connection. Chunk transactions can commit
    # independently, and a disconnect automatically releases the worker lock.
    async with database.engine.begin() as lock:
        if not await lock.scalar(select(func.pg_try_advisory_xact_lock(WORKER_LOCK))):
            return False
        job = await next_job(database)
        if job is None:
            return False
        try:
            await process_job(database, settings, job)
        except (OSError, DatabaseTimeout):
            raise
        except Exception as error:
            if isinstance(error, DBAPIError) and error.connection_invalidated:
                raise
            await record_processing_error(database, job.id, error)
        return True


async def run(database, settings, *, once=False):
    while True:
        try:
            processed = await run_one(database, settings)
        except (DBAPIError, DatabaseTimeout, OSError) as error:
            if once:
                raise
            logger.warning("Lead import queue unavailable (%s)", type(error).__name__)
            processed = False
        if once:
            return
        if not processed:
            await asyncio.sleep(POLL_SECONDS)
