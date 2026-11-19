import asyncio
import hashlib
from collections import Counter
from itertools import batched
from types import SimpleNamespace

from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.core import dates
from app.core.db import transaction
from app.core.errors import DomainError
from app.features.crm_imports import history, leads, workbooks
from app.models import CrmImport, CrmImportRow

CHUNK_SIZE = 500
WORKER_LOCK = 72851902


def read_source(settings, job):
    with history.workbook_path(settings, job.id).open("rb") as source:
        content = source.read(workbooks.max_bytes(settings, "leads") + 1)
    if hashlib.sha256(content).hexdigest() != job.file_sha256:
        raise DomainError(422, "source_checksum_mismatch")
    return workbooks.prepare(settings, "leads", job.file_name, content)


async def next_job(database):
    async with transaction(database) as session:
        job = await session.scalar(
            select(CrmImport)
            .where(CrmImport.kind == "leads", CrmImport.status.in_(("queued", "processing")))
            .order_by(CrmImport.created_at, CrmImport.id)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "processing"
        if job.started_at is None:
            job.started_at = dates.now()
        return job


async def process_chunk(database, job_id, rows):
    async with transaction(database) as session:
        job = await history.get_log(session, job_id)
        actor = SimpleNamespace(id=job.created_by, role="supervisor")
        counts = Counter()
        for number, values, error in rows:
            warnings = []
            if error is None:
                try:
                    outcome, warnings = await leads.import_lead(session, actor, job.id, values)
                except DomainError as rejection:
                    error = rejection
            if error is not None:
                outcome = "failed"
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
            current.error_code = (
                error.code if isinstance(error, DomainError) else "source_unavailable"
            )
            current.status = "failed"
            current.finished_at = dates.now()
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


async def run_one(database, settings):
    # Hold this transaction on its own connection. Chunk transactions can commit
    # independently, and a disconnect automatically releases the worker lock.
    async with database.engine.begin() as lock:
        if not await lock.scalar(select(func.pg_try_advisory_xact_lock(WORKER_LOCK))):
            return False
        job = await next_job(database)
        if job is None:
            return False
        await process_job(database, settings, job)
        return True


async def run(database, settings, *, once=False):
    while True:
        processed = await run_one(database, settings)
        if once:
            return
        if not processed:
            await asyncio.sleep(2)
