from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.audit import record
from app.core.deps import Session, Supervisor
from app.core.errors import DomainError
from app.core.excel import XLSX_TYPE, xlsx_response
from app.core.lifecycle import lifecycle_actor
from app.core.pagination import PageParams, paginate
from app.features.crm_imports import history, organization, workbooks
from app.models import CrmImport, CrmImportRow

router = APIRouter(prefix="/imports", tags=["CRM imports"])
Page = Annotated[PageParams, Depends()]
Kind = Literal["organization", "leads"]


@router.get("")
async def list_imports(
    session: Session,
    user: Supervisor,
    params: Page,
    import_type: Kind | None = None,
    status: str | None = None,
):
    statement = select(CrmImport)
    if import_type:
        statement = statement.where(CrmImport.kind == import_type)
    if status:
        statement = statement.where(CrmImport.status == status)
    page = await paginate(
        session,
        statement,
        params,
        {"created_at": CrmImport.created_at},
        "-created_at",
        CrmImport.id,
    )
    page["items"] = [history.log_out(job) for job in page["items"]]
    return page


@router.get("/{import_id}")
async def detail(import_id: UUID, session: Session, user: Supervisor):
    return history.log_out(await history.get_log(session, import_id))


@router.get("/{import_id}/errors")
async def errors(
    import_id: UUID,
    session: Session,
    user: Supervisor,
    params: Page,
    format: Literal["json", "xlsx"] = "json",
):
    await history.get_log(session, import_id)
    if format == "xlsx":
        return xlsx_response(
            await history.error_report(session, import_id), "crm-import-errors.xlsx"
        )
    page = await paginate(
        session,
        history.failed_rows(import_id),
        params,
        {"row_number": CrmImportRow.row_number},
        "row_number",
        CrmImportRow.row_number,
    )
    page["items"] = [history.row_out(row) for row in page["items"]]
    return page


@router.get("/{import_id}/file")
async def original(import_id: UUID, request: Request, session: Session, user: Supervisor):
    job = await history.get_log(session, import_id)
    path = history.workbook_path(request.app.state.settings, job.id)
    if not path.is_file():
        raise DomainError(404, "not_found")
    record(session, user, "download", "crm_imports", job.id, request=request)
    return FileResponse(path, media_type=XLSX_TYPE, filename="crm-import-original.xlsx")


@router.get("/templates/{kind}")
async def template(kind: Kind, user: Supervisor):
    return xlsx_response(workbooks.template(kind), f"crm-{kind}-template.xlsx")


@router.post("/organization")
async def upload_organization(
    request: Request, session: Session, user: Supervisor, file: Annotated[UploadFile, File()]
):
    settings = request.app.state.settings
    content, sheet = await workbooks.read_upload(file, settings, "organization")
    job = await history.create_log(
        session,
        settings,
        user,
        request,
        "organization",
        file.filename,
        content,
        sheet.total_rows,
        sheet.warnings,
    )
    await organization.process(session, user, request, job, sheet)
    return history.log_out(job)


@router.post("/leads", status_code=202)
async def upload_leads(
    request: Request, session: Session, user: Supervisor, file: Annotated[UploadFile, File()]
):
    settings = request.app.state.settings
    content, sheet = await workbooks.read_upload(file, settings, "leads")
    actor = await lifecycle_actor(session, user, "supervisor")
    job = await history.create_log(
        session,
        settings,
        actor,
        request,
        "leads",
        file.filename,
        content,
        sheet.total_rows,
        sheet.warnings,
    )
    return history.log_out(job)
