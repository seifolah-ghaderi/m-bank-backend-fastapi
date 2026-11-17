from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select

from app.core.audit import record
from app.core.dates import JalaliDate
from app.core.deps import Session, Supervisor
from app.core.errors import DomainError
from app.core.excel import xlsx_response
from app.core.pagination import PageParams, paginate
from app.features.pos import service_imports as service
from app.models import ImportRowError
from app.schemas.pos import ImportRowErrorOut

router = APIRouter(prefix="/pos/imports", tags=["POS imports"])
Kind = Literal["devices", "transactions", "combined"]


@router.get("/templates/{kind}")
async def template(kind: Kind, user: Supervisor):
    return xlsx_response(service.template(kind), "pos-" + kind + "-template.xlsx")


@router.post("/{kind}")
async def upload(
    kind: Kind,
    request: Request,
    session: Session,
    user: Supervisor,
    file: Annotated[UploadFile, File()],
    jalali_year: Annotated[int | None, Form()] = None,
    jalali_month: Annotated[int | None, Form()] = None,
    mode: Annotated[str | None, Form()] = None,
):
    settings = request.app.state.settings
    try:
        content = await file.read(settings.import_max_mb * 1024 * 1024 + 1)
    finally:
        await file.close()
    import_id, duplicate = await service.import_file(
        request.app.state.database,
        settings,
        user,
        kind,
        content,
        file.filename,
        request,
        jalali_year=jalali_year,
        jalali_month=jalali_month,
        mode=mode,
    )
    return await service.log_out(session, await service.get_log(session, import_id), duplicate)


@router.get("")
async def logs(
    session: Session,
    user: Supervisor,
    params: Annotated[PageParams, Depends()],
    import_type: str | None = None,
    status: str | None = None,
    user_id: UUID | None = None,
    from_date: JalaliDate | None = None,
    to_date: JalaliDate | None = None,
):
    return await service.list_logs(
        session, params, import_type, status, user_id, from_date, to_date
    )


@router.get("/{import_id}")
async def log(import_id: UUID, session: Session, user: Supervisor):
    return await service.log_out(session, await service.get_log(session, import_id))


@router.get("/{import_id}/errors")
async def errors(
    import_id: UUID,
    session: Session,
    user: Supervisor,
    params: Annotated[PageParams, Depends()],
    format: Literal["json", "xlsx"] = "json",
):
    if format == "xlsx":
        return xlsx_response(
            await service.error_report(session, import_id), "pos-import-errors.xlsx"
        )
    await service.get_log(session, import_id)
    page = await paginate(
        session,
        select(ImportRowError).where(ImportRowError.import_id == import_id),
        params,
        {"row_number": ImportRowError.row_number},
        "row_number",
        ImportRowError.id,
    )
    page["items"] = [ImportRowErrorOut.model_validate(e) for e in page["items"]]
    return page


@router.get("/{import_id}/file")
async def original(import_id: UUID, request: Request, session: Session, user: Supervisor):
    log = await service.get_log(session, import_id)
    path = service.stored_path(request.app.state.settings, log.storage_key)
    if not path.is_file():
        raise DomainError(404, "not_found")
    content = path.read_bytes()
    record(
        session,
        user,
        "download",
        "import_logs",
        log.id,
        after={"file_sha256": log.file_sha256},
        request=request,
    )
    return xlsx_response(content, "pos-original.xlsx")
