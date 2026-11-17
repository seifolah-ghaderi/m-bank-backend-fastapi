import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell

from app.core import dates
from app.core.errors import DomainError

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def safe_value(value):
    if isinstance(value, datetime):
        return dates.format_datetime(value)
    if isinstance(value, date):
        return dates.format_date(value)
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def workbook_bytes(headers, rows):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Data")
    sheet.append(headers)
    for row in rows:
        cells = []
        for value in row:
            value = safe_value(value)
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
                cell.number_format = "@"
            cells.append(cell)
        sheet.append(cells)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def xlsx_response(content, filename):
    return StreamingResponse(
        (content[i : i + 65536] for i in range(0, len(content), 65536)),
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def identifier_cell(cell):
    value = cell.value
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid_format")
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value() or abs(number) >= 10**15:
            raise ValueError("invalid_format")
        value = str(int(number))
        if re.fullmatch(r"0+", cell.number_format or ""):
            value = value.zfill(len(cell.number_format))
    elif not isinstance(value, str):
        raise ValueError("invalid_format")
    return value.strip()


def read_xlsx(content, max_rows):
    """Bound ZIP expansion before openpyxl; return detached cell values/formats."""
    try:
        if not content.startswith(b"PK\x03\x04"):
            raise ValueError("invalid_file")
        with ZipFile(BytesIO(content)) as archive:
            info = archive.infolist()
            if len(info) > 1000 or sum(i.file_size for i in info) > 100 * 1024 * 1024:
                raise ValueError("invalid_file")
            for member in info:
                if member.filename.endswith(".xml"):
                    data = archive.read(member)
                    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                        raise ValueError("invalid_file")
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            sheet = next((s for s in workbook if s.sheet_state == "visible"), None)
            if sheet is None or (sheet.max_column or 0) > 256 or (sheet.max_row or 0) > 1048576:
                raise ValueError("invalid_file")
            # Read the original numeric lexemes: openpyxl's numeric values may
            # already be floats. Keep date cells decoded by its date styles,
            # but use exact XML decimals for money/count/identifier cells.
            numeric = {}
            with ZipFile(BytesIO(content)) as archive:
                with archive.open(sheet._worksheet_path) as part:
                    for _, node in ET.iterparse(part, events=("end",)):
                        if node.tag.endswith("}c") and node.get("t", "n") == "n":
                            value = node.find("{*}v")
                            if value is not None and value.text is not None:
                                numeric[node.get("r")] = value.text
                            node.clear()
            rows = sheet.iter_rows()
            headers = next(rows, ())
            names = [str(c.value or "").strip() for c in headers]
            result = []
            for row_number, row in enumerate(rows, start=2):
                if all(
                    c.value is None or (isinstance(c.value, str) and not c.value.strip())
                    for c in row
                ):
                    continue
                if len(result) >= max_rows:
                    raise DomainError(422, "too_many_rows")
                values = [
                    (
                        Decimal(numeric[c.coordinate])
                        if c.data_type == "n" and getattr(c, "coordinate", None) in numeric
                        else c.value,
                        c.number_format,
                        c.data_type,
                    )
                    for c in row
                ]
                result.append((row_number, values))
            return names, result
        finally:
            workbook.close()
    except DomainError:
        raise
    except Exception:
        raise DomainError(422, "invalid_file") from None
