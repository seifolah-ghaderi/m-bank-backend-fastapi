import hashlib
import os
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core import dates
from app.core.audit import record
from app.core.errors import DomainError
from app.core.excel import workbook_bytes
from app.models import CrmImport, CrmImportRow
from app.models.base import new_id


def workbook_path(settings, import_id):
    root = settings.import_storage_dir.resolve()
    path = (root / "crm" / f"{import_id}.xlsx").resolve()
    if not path.is_relative_to(root):
        raise DomainError(404, "not_found")
    return path


def save_workbook(settings, import_id, content):
    path = workbook_path(settings, import_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stage:
        temporary = Path(stage.name)
        try:
            stage.write(content)
            stage.flush()
            os.fsync(stage.fileno())
            stage.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


async def create_log(session, settings, actor, request, kind, filename, content, rows, warnings):
    job = CrmImport(
        id=new_id(),
        kind=kind,
        status="queued" if kind == "leads" else "processing",
        file_name=Path(filename.replace("\\", "/")).name[:255],
        file_sha256=hashlib.sha256(content).hexdigest(),
        total_rows=len(rows),
        warnings=warnings,
        counts={},
        started_at=dates.now() if kind == "organization" else None,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(job)
    await session.flush()
    record(session, actor, "upload", "crm_imports", job.id, after={"kind": kind}, request=request)
    await run_in_threadpool(save_workbook, settings, job.id, content)
    return job


async def get_log(session, job_id):
    job = await session.get(CrmImport, job_id)
    if job is None:
        raise DomainError(404, "not_found")
    return job


def log_out(job):
    created, unchanged, failed = (
        job.counts.get(key, 0) for key in ("created", "unchanged", "failed")
    )
    return {
        "id": job.id,
        "import_type": job.kind,
        "status": job.status,
        "file_name": job.file_name,
        "created_by": job.created_by,
        "created_at": dates.format_datetime(job.created_at),
        "started_at": dates.format_datetime(job.started_at) if job.started_at else None,
        "finished_at": dates.format_datetime(job.finished_at) if job.finished_at else None,
        "total_rows": job.total_rows,
        "processed_rows": created + unchanged + failed,
        "success_count": created + unchanged,
        "failure_count": failed,
        "created": created,
        "unchanged": unchanged,
        "failed": failed,
        "component_counts": {k: v for k, v in job.counts.items() if k.startswith("city_")},
        "warnings": job.warnings,
        "warning_rows": job.counts.get("warning_rows", 0),
        "warning_counts": {
            key: job.counts[key] for key in ("unknown_occupation",) if key in job.counts
        },
        "error_code": job.error_code,
        "errors_url": f"/api/v1/imports/{job.id}/errors",
        "file_url": f"/api/v1/imports/{job.id}/file",
    }


def failed_rows(job_id):
    return select(CrmImportRow).where(
        CrmImportRow.import_id == job_id, CrmImportRow.outcome == "failed"
    )


def row_out(row):
    return {
        "row_number": row.row_number,
        "error_code": row.error_code,
        "column": row.column,
    }


async def error_report(session, job_id):
    rows = await session.stream_scalars(failed_rows(job_id).order_by(CrmImportRow.row_number))
    # XLSX generation uses the shared writer to preserve literal cell values.
    values = [(row.row_number, row.error_code, row.column) async for row in rows]
    return workbook_bytes(["row_number", "error_code", "column"], values)


def add_outcome(session, job, row_number, outcome, error=None, *, warnings=()):
    column = error.details.get("column") if error and isinstance(error.details, dict) else None
    session.add(
        CrmImportRow(
            import_id=job.id,
            row_number=row_number,
            outcome=outcome,
            error_code=error.code if error else None,
            column=column,
            warnings=list(warnings),
        )
    )


def update_counts(job, counts):
    job.counts = dict(Counter(job.counts) + counts)


def finish(job):
    failed = job.counts.get("failed", 0)
    accepted = job.counts.get("created", 0) + job.counts.get("unchanged", 0)
    job.status = ("completed_with_errors" if accepted else "failed") if failed else "completed"
    job.finished_at = dates.now()
