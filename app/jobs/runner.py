"""Job state machine. Android builds fail closed when the toolchain is absent."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    project_id: str
    engine: str
    target: str
    status: str = "queued"
    progress: int = 0
    started_at: str | None = None
    ended_at: str | None = None
    logs: list[dict] = field(default_factory=list)
    error: dict | None = None
    artifacts: list[dict] = field(default_factory=list)


def probe_toolchain() -> list[dict]:
    checks = [
        ("unity", "Unity Editor", ["UNITY_EDITOR"]),
        ("unreal", "Unreal Automation Tool", ["UE_ROOT"]),
        ("godot", "Godot editor", ["GODOT_BIN"]),
        ("android-sdk", "Android SDK", ["ANDROID_HOME", "ANDROID_SDK_ROOT"]),
        ("android-ndk", "Android NDK", ["ANDROID_NDK_HOME"]),
        ("jdk", "JDK", ["JAVA_HOME"]),
    ]
    found = []
    for ident, name, envs in checks:
        path = next((os.environ[key] for key in envs if os.environ.get(key)), None)
        exists = bool(
            path and (os.path.isdir(path) or shutil.which(path) or os.path.isfile(path))
        )
        found.append(
            {
                "id": ident,
                "name": name,
                "env": envs,
                "present": exists,
                "path": path if exists else None,
            }
        )
    return found


def run_job(
    report: dict,
    target: str,
    project_id: str = "local",
    cancel: bool = False,
) -> dict:
    job = Job(
        id=uuid.uuid4().hex,
        project_id=project_id,
        engine=report.get("engine", "Unknown"),
        target=target,
    )
    job.started_at = _now()

    def log(status: str, progress: int, message: str) -> None:
        job.status = status
        job.progress = progress
        job.logs.append({"at": _now(), "stage": status, "message": message})

    log(
        "analyzing",
        22,
        f"Classified {job.engine} / {report.get('classification')} "
        f"at confidence {report.get('confidence')}.",
    )
    if cancel:
        log("cancelled", job.progress, "Cancelled before preparation. No package was produced.")
        job.ended_at = _now()
        return asdict(job)

    log("preparing", 48, report.get("plan", {}).get("summary", "Plan prepared."))
    job.artifacts.append({"name": "analysis-report.json", "kind": "report"})
    job.artifacts.append({"name": "port-plan.md", "kind": "plan"})

    if target == "android_package":
        log("building", 72, "Probing toolchain. Uploaded binaries are not executed.")
        tools = probe_toolchain()
        for tool in tools:
            status = "present" if tool["present"] else "absent"
            job.logs.append(
                {
                    "at": _now(),
                    "stage": "building",
                    "message": f"{tool['name']}: {status}. Env: {', '.join(tool['env'])}.",
                }
            )
        missing = [tool["name"] for tool in tools if not tool["present"]]
        # Always fail closed in v0.2 — even if tools are present, full cook is not auto-run
        # without explicit allow flag. Presence alone does not produce an APK here.
        job.status = "failed"
        job.ended_at = _now()
        if missing:
            job.error = {
                "code": "missing_toolchain",
                "message": (
                    "Android package was not built. Missing "
                    + ", ".join(missing)
                    + ". No APK or AAB was generated."
                ),
            }
        else:
            job.error = {
                "code": "execution_disabled",
                "message": (
                    "Toolchain paths were found, but automatic editor invocation is disabled "
                    "in v0.2. Use the planned command on a controlled build machine. "
                    "No APK was generated."
                ),
            }
        job.logs.append({"at": _now(), "stage": "failed", "message": job.error["message"]})
        job.artifacts.append(
            {
                "name": "toolchain-diagnostics.json",
                "kind": "diagnostics",
                "tools": tools,
                "command": report.get("plan", {}).get("command"),
            }
        )
        return asdict(job)

    if target == "validate_android_package":
        validation = report.get("android_validation") or {}
        log("validating", 90, "Checking manifest, DEX, and ABI directories only.")
        if not validation.get("structurally_valid"):
            job.status = "failed"
            job.error = {
                "code": "apk_structure_invalid",
                "message": "Android package structure is incomplete.",
            }
            job.logs.append({"at": _now(), "stage": "failed", "message": job.error["message"]})
        else:
            job.status = "completed"
            job.progress = 100
            job.logs.append(
                {
                    "at": _now(),
                    "stage": "completed",
                    "message": "Structure only. Not a runtime result. No new APK was written.",
                }
            )
        job.ended_at = _now()
        job.artifacts.append({"name": "apk-validation.json", "kind": "validation"})
        return asdict(job)

    # analysis_report
    log("validating", 90, "Checking the report contract.")
    if report.get("native_apk_buildable_from_upload_alone") is not False:
        job.status = "failed"
        job.error = {
            "code": "report_invalid",
            "message": "Upload-alone export flag must stay false.",
        }
    elif report.get("plan", {}).get("executed") is True:
        job.status = "failed"
        job.error = {"code": "report_invalid", "message": "Plan was marked executed."}
    else:
        job.status = "completed"
        job.progress = 100
        job.logs.append(
            {
                "at": _now(),
                "stage": "completed",
                "message": "Analysis job validated. No Android package was requested.",
            }
        )
    job.ended_at = _now()
    return asdict(job)
