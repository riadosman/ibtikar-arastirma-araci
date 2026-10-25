"""Deterministic exports. Same candidates in, same file out; retries never duplicate rows."""

import csv
import io
import json
import time
from typing import Protocol

import httpx
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from app.core.config import get_settings

FIELDS = {
    "full_name": "Name",
    "job_title": "Role",
    "organization": "Organization",
    "field": "Field",
    "location": "Location",
    "website": "Website",
    "linkedin_url": "LinkedIn",
    "public_email": "Public Email",
    "public_phone": "Public Phone",
    "relevance_score": "Relevance Score",
    "confidence_score": "Confidence Score",
    "status": "Status",
    "notes": "Notes",
    "is_demo": "Demo Data",
}
HEADERS = list(FIELDS.values()) + ["Source"]
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class ExportError(RuntimeError):
    """User-safe export failure; `retryable` tells the caller whether to try again."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def rows_for(candidates):
    return [
        {
            **{label: getattr(c, field) for field, label in FIELDS.items()},
            "Source": " | ".join(f"{s.name}: {s.url}" for s in c.sources),
        }
        for c in candidates
    ]


def clean_text(value):
    # Scraped text can contain control characters that XLSX (XML) cannot store.
    return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value


def safe_cell(value):
    # Spreadsheet formula injection protection, including leading whitespace/control chars.
    value = clean_text(value)
    if isinstance(value, str) and (
        value.startswith(FORMULA_PREFIXES) or value.lstrip().startswith(FORMULA_PREFIXES[:4])
    ):
        return "'" + value
    return value


def render_export(candidates, format):
    rows = rows_for(candidates)
    if format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2).encode(), "application/json"
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows({k: safe_cell(v) for k, v in row.items()} for row in rows)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Candidates"
    sheet.append(HEADERS)
    for row in rows:
        sheet.append([clean_text(row[h]) for h in HEADERS])
    for line in sheet.iter_rows(min_row=2):
        for cell in line:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # text cell: "=..." is stored literally, never as a formula
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 24
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sheet_values(candidates):
    """Plain cell values. RAW input mode stores text literally, so formulas never run."""
    values = [HEADERS]
    for row in rows_for(candidates):
        values.append(["" if row[h] is None else clean_text(str(row[h])) for h in HEADERS])
    return values


class GoogleSheetsService(Protocol):
    provider: str

    def create_sheet(self, title: str) -> dict: ...
    def append_candidates(self, sheet: dict, candidates: list) -> dict: ...
    def share_sheet(self, sheet: dict, email: str) -> dict: ...


class MockGoogleSheetsService:
    provider = "mock"

    def create_sheet(self, title):
        return {
            "provider": "mock",
            "id": None,
            "title": title,
            "url": None,
            "message": "Preview only. No Google Sheet was created.",
        }

    def append_candidates(self, sheet, candidates):
        return {**sheet, "row_count": len(candidates), "rows": rows_for(candidates)}

    def share_sheet(self, sheet, email):
        return {**sheet, "shared": False, "message": "Mock mode: no sharing invitation was sent."}


class GoogleSheetsProvider:
    """Google Sheets/Drive REST with an OAuth refresh token from the environment.

    Writing replaces the whole "Candidates" range (clear + update), so repeating a
    write after a timeout produces the same sheet instead of appending duplicate rows.
    """

    provider = "google"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets"
    DRIVE_URL = "https://www.googleapis.com/drive/v3/files"

    def __init__(self, client=None, retries=2):
        self.client = client or httpx.Client(timeout=20)
        self.retries = retries
        self._access_token = None

    def _request(self, method, url, **kwargs):
        for attempt in range(self.retries + 1):
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt == self.retries:
                    raise ExportError("Google Sheets is unreachable. Try again.", True) from exc
            else:
                if response.status_code < 400:
                    return response
                if response.status_code in (401, 403):
                    raise ExportError(
                        "Google credentials were rejected. An administrator must update them."
                    )
                if response.status_code not in (429, 500, 502, 503, 504):
                    raise ExportError(f"Google Sheets rejected the export (HTTP {response.status_code}).")
                if attempt == self.retries:
                    raise ExportError("Google Sheets is busy. Try again in a minute.", True)
            time.sleep(min(8, 0.5 * 2**attempt))
        raise AssertionError("unreachable")

    def _headers(self):
        if not self._access_token:
            settings = get_settings()
            response = self._request(
                "POST",
                self.TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": settings.google_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            token = response.json().get("access_token")
            if not isinstance(token, str):
                raise ExportError("Google did not return an access token.")
            self._access_token = token
        return {"Authorization": f"Bearer {self._access_token}"}

    def create_sheet(self, title):
        response = self._request(
            "POST",
            self.SHEETS_URL,
            headers=self._headers(),
            json={
                "properties": {"title": title[:200]},
                "sheets": [{"properties": {"title": "Candidates"}}],
            },
        )
        data = response.json()
        return {
            "provider": "google",
            "id": data["spreadsheetId"],
            "title": title,
            "url": data.get("spreadsheetUrl"),
        }

    def append_candidates(self, sheet, candidates):
        base = f"{self.SHEETS_URL}/{sheet['id']}/values/Candidates"
        self._request("POST", base + ":clear", headers=self._headers(), json={})
        values = sheet_values(candidates)
        self._request(
            "PUT",
            base + "!A1",
            params={"valueInputOption": "RAW"},
            headers=self._headers(),
            json={"range": "Candidates!A1", "majorDimension": "ROWS", "values": values},
        )
        return {**sheet, "row_count": len(values) - 1}

    def share_sheet(self, sheet, email):
        # Drive returns the existing permission when the same user is added again.
        self._request(
            "POST",
            f"{self.DRIVE_URL}/{sheet['id']}/permissions",
            params={"sendNotificationEmail": "false"},
            headers=self._headers(),
            json={"role": "writer", "type": "user", "emailAddress": email},
        )
        return {**sheet, "shared": True}


def get_sheets_service():
    if get_settings().google_sheets_configured:
        return GoogleSheetsProvider()
    return MockGoogleSheetsService()
