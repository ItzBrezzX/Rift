"""KingBrezz Port Engine API. Analysis and toolchain checks only."""

from __future__ import annotations

import json
import os
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.adapters.registry import ADAPTERS, adapter_for
from app.detection.analyzer import InventoryFile, analyze_files
from app.jobs.runner import probe_toolchain, run_job
from app.security.archive import UnsafeArchiveError, assert_zip_limits

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PORT_ENGINE_DATA_DIR", "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
MAX_BYTES = int(os.getenv("PORT_ENGINE_MAX_UPLOAD_BYTES", str(1024**3)))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="KingBrezz Port Engine",
    version=__version__,
    description=(
        "Analyze PC game projects and report honest Android porting feasibility. "
        "Does not convert Windows players into APKs."
    ),
)
JOBS: dict[str, dict] = {}

STATIC_DIR = APP_DIR / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _read_interesting(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> InventoryFile:
    path = info.filename.replace("\\", "/")
    text = None
    head = None
    lower = path.lower()
    interesting = lower.endswith(
        (
            ".txt",
            ".json",
            ".godot",
            ".gradle",
            ".kts",
            ".ini",
            ".html",
            ".htm",
            ".lua",
            ".py",
            ".xml",
            ".yyp",
            ".cs",
            ".java",
            ".uproject",
            ".uplugin",
            ".asset",
            ".csproj",
            ".md",
            ".cfg",
            ".properties",
        )
    ) or lower.endswith(
        ("projectversion.txt", "cmakelists.txt", "makefile", "package.json", "export_presets.cfg")
    )
    binary = lower.endswith((".exe", ".dll", ".so"))
    if info.file_size and info.file_size <= 2_000_000 and (interesting or binary):
        data = zf.read(info)
        if binary:
            head = data[:1_500_000]
        else:
            if b"\0" not in data[:2048]:
                text = data.decode("utf-8", "replace")
            head = data[:4096]
    return InventoryFile(path=path, size=info.file_size, text=text, head=head)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return index.read_text(encoding="utf-8")
    return (
        f"<html><body><h1>KingBrezz Port Engine {__version__}</h1>"
        "<p>API is running. POST a ZIP to <code>/api/analyze</code>.</p></body></html>"
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "KingBrezz Port Engine",
        "version": __version__,
        "native_apk_from_upload_alone": False,
    }


@app.get("/api/toolchain")
def toolchain() -> dict:
    return {"tools": probe_toolchain(), "executes_uploads": False}


@app.get("/api/engines")
def engines() -> dict:
    return {
        "engines": [
            {
                "engine": key,
                "native_export": item.native_export,
                "notes": item.notes,
                "command": item.plan_command(),
            }
            for key, item in ADAPTERS.items()
        ]
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Upload a .zip project archive.")
    report_id = uuid.uuid4().hex
    archive_path = UPLOAD_DIR / f"{report_id}.zip"
    total = 0
    try:
        with archive_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(413, "Archive exceeds configured upload limit.")
                out.write(chunk)
        try:
            with zipfile.ZipFile(archive_path) as zf:
                assert_zip_limits(zf)
                files = [_read_interesting(zf, info) for info in zf.infolist()]
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "Invalid ZIP archive.") from exc
        except UnsafeArchiveError as exc:
            raise HTTPException(400, str(exc)) from exc
        report = analyze_files(files, Path(file.filename).name)
        report["report_id"] = report_id
        report["archive_size_bytes"] = total
        report["adapter"] = adapter_for(report["engine"]).build_android()
        (REPORT_DIR / f"{report_id}.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return JSONResponse(report)
    finally:
        await file.close()


@app.get("/api/reports/{report_id}")
def get_report(report_id: str) -> dict:
    if not report_id.isalnum():
        raise HTTPException(400, "Invalid report ID.")
    path = REPORT_DIR / f"{report_id}.json"
    if not path.exists():
        raise HTTPException(404, "Report not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/jobs")
async def create_job(payload: dict) -> dict:
    report_id = str(payload.get("report_id", ""))
    target = str(payload.get("target", "analysis_report"))
    if target not in {"analysis_report", "android_package", "validate_android_package"}:
        raise HTTPException(400, "Unknown job target.")
    path = REPORT_DIR / f"{report_id}.json"
    if not report_id.isalnum() or not path.exists():
        raise HTTPException(404, "Report not found.")
    report = json.loads(path.read_text(encoding="utf-8"))
    job = run_job(report, target, project_id=report_id)
    JOBS[job["id"]] = job
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job
