"""Tests for KingBrezz Port Engine v0.2 — real behavior, not smoke-only stubs."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.detection.analyzer import InventoryFile, analyze_entries, analyze_files
from app.jobs.runner import run_job
from app.main import app
from app.pe.parser import MACHINE, parse_pe, synthesize_pe
from app.security.archive import UnsafeArchiveError, validate_zip_names


def test_unity_source_is_not_an_apk():
    result = analyze_files(
        [
            InventoryFile("Assets/a.asset", text="yaml"),
            InventoryFile(
                "ProjectSettings/ProjectVersion.txt",
                text="m_EditorVersion: 2022.3.21f1\n",
            ),
            InventoryFile("Packages/manifest.json", text='{"dependencies": {}}'),
            InventoryFile(
                "ProjectSettings/ProjectSettings.asset",
                text="scriptingBackend:\n  Android: 1\n",
            ),
            InventoryFile("Assets/Plugins/Steamworks.dll"),
        ]
    )
    assert result["engine"] == "Unity"
    assert result["engine_version"] == "2022.3.21f1"
    assert result["runtime"] == "il2cpp"
    assert result["classification"] == "source_project"
    assert result["strategy"] == "native_engine_export"
    assert result["recommended_route"] == "native_android_export"
    assert result["native_apk_buildable_from_upload_alone"] is False
    assert result["confidence"] > 0.7
    assert any(f["id"] == "unity-native-plugins" for f in result["findings"])


def test_unity_il2cpp_windows_player():
    blob = synthesize_pe(
        MACHINE["AMD64"],
        ["UnityPlayer.dll", "d3d11.dll"],
        extra_ascii="2021.3.16f1",
    )
    result = analyze_files(
        [
            InventoryFile("Granny.exe", head=blob),
            InventoryFile("Granny_Data/globalgamemanagers"),
            InventoryFile("UnityPlayer.dll", head=blob),
            InventoryFile("GameAssembly.dll", head=blob),
        ]
    )
    assert result["engine"] == "Unity"
    assert result["project_type"] == "windows_build"
    assert result["classification"] == "windows_player"
    assert result["runtime"] == "il2cpp"
    assert result["strategy"] == "compatibility_layer"
    assert result["native_apk_buildable_from_upload_alone"] is False
    assert any(f["id"] == "il2cpp-irreversible" for f in result["findings"])
    assert any(f["id"] == "directx" for f in result["findings"])


def test_unreal_godot_and_others():
    unreal = analyze_files(
        [
            InventoryFile(
                "Game.uproject",
                text='{"FileVersion":3,"EngineAssociation":"5.4","Modules":[{"Name":"Game"}]}',
            ),
            InventoryFile("Config/DefaultEngine.ini", text="[/Script/Engine.Engine]\n"),
            InventoryFile("Source/Game/Game.Build.cs", text="public class Game {}\n"),
        ]
    )
    assert unreal["engine"] == "Unreal Engine"
    assert unreal["engine_version"] == "5.4"
    assert unreal["strategy"] == "native_engine_export"

    godot = analyze_files(
        [
            InventoryFile(
                "project.godot",
                text='config_version=5\nconfig/features=PackedStringArray("4.3")\n',
            )
        ]
    )
    assert godot["engine"] == "Godot"
    assert godot["engine_version"] == "4.3"

    gm = analyze_files(
        [
            InventoryFile(
                "game.yyp",
                text='{"resourceType":"GMProject","IDEVersion":"2024.8.1.171","resources":[]}',
            )
        ]
    )
    assert gm["engine"] == "GameMaker"
    assert gm["engine_version"] == "2024.8.1.171"

    renpy = analyze_files(
        [
            InventoryFile("game/script.rpy", text='label start:\n    "hi"\n'),
            InventoryFile("renpy/__init__.py", text="vc_version = (8, 3, 4)\n"),
        ]
    )
    assert renpy["engine"] == "Ren'Py"
    assert renpy["engine_version"] == "8.3.4"

    rpg = analyze_files(
        [
            InventoryFile("js/rmmz_core.js", text="/* rmmz */\n"),
            InventoryFile("data/System.json", text='{"gameTitle":"Harbor"}'),
        ]
    )
    assert rpg["engine"] == "RPG Maker"
    assert rpg["strategy"] == "project_migration"

    gdx = analyze_files(
        [
            InventoryFile("settings.gradle", text="include ':core', ':android'\n"),
            InventoryFile("build.gradle", text="ext.gdxVersion = '1.12.1'\n"),
            InventoryFile(
                "android/build.gradle",
                text="implementation \"com.badlogicgames.gdx:gdx-backend-android:$gdxVersion\"\n",
            ),
        ]
    )
    assert gdx["engine"] == "LibGDX"
    assert gdx["engine_version"] == "1.12.1"

    love = analyze_files(
        [
            InventoryFile("main.lua", text="function love.draw() end\n"),
            InventoryFile("conf.lua", text="function love.conf(t) end\n"),
        ]
    )
    assert love["engine"] == "LÖVE"

    electron = analyze_files(
        [
            InventoryFile(
                "package.json",
                text='{"name":"desk","dependencies":{"electron":"31.0.0"}}',
            )
        ]
    )
    assert electron["engine"] == "Electron"

    html5 = analyze_files(
        [
            InventoryFile(
                "index.html",
                text="<!doctype html><script src='phaser.min.js'></script><canvas></canvas>",
            )
        ]
    )
    assert html5["engine"] == "HTML5"

    cmake = analyze_files(
        [
            InventoryFile(
                "CMakeLists.txt",
                text="cmake_minimum_required(VERSION 3.20)\nproject(Harbor)\n",
            )
        ]
    )
    assert cmake["engine"] == "Custom C/C++"

    java = analyze_entries(["game.jar", "META-INF/MANIFEST.MF"])
    assert java["engine"] == "Java"

    unknown = analyze_entries(["notes/readme.txt"])
    assert unknown["engine"] == "Unknown"
    assert unknown["recommended_route"] == "manual_inspection"
    assert unknown["confidence"] == 0


def test_android_package_validation():
    result = analyze_files(
        [
            InventoryFile("AndroidManifest.xml", text="<manifest package='ex'/>"),
            InventoryFile("classes.dex"),
            InventoryFile("lib/arm64-v8a/libgame.so"),
            InventoryFile("META-INF/MANIFEST.MF", text="Manifest-Version: 1.0\n"),
        ]
    )
    assert result["engine"] == "Android"
    assert result["strategy"] == "already_android"
    assert result["android_validation"]["structurally_valid"] is True
    assert "arm64-v8a" in result["android_validation"]["abis"]


def test_zip_slip_rejected():
    with pytest.raises(UnsafeArchiveError) as exc:
        validate_zip_names(["../../evil.txt"])
    assert exc.value.code == "zip_slip"


def test_pe_imports_and_clr():
    info = parse_pe(synthesize_pe(MACHINE["AMD64"], ["d3d11.dll", "KERNEL32.dll"]))
    assert info.valid is True
    assert info.machine_name == "x64"
    assert any(n.lower() == "d3d11.dll" for n in info.imports)
    arm = parse_pe(synthesize_pe(MACHINE["ARM64"], ["kernel32.dll"]))
    assert arm.machine_name == "arm64"
    managed = parse_pe(synthesize_pe(MACHINE["AMD64"], dotnet=True))
    assert managed.is_dotnet is True
    assert parse_pe(b"nope").valid is False


def test_android_job_fails_without_toolchain(monkeypatch):
    for key in (
        "UNITY_EDITOR",
        "ANDROID_HOME",
        "ANDROID_SDK_ROOT",
        "ANDROID_NDK_HOME",
        "JAVA_HOME",
        "GODOT_BIN",
        "UE_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)
    report = analyze_entries(
        ["ProjectSettings/ProjectVersion.txt", "Assets/a.asset"]
    )
    job = run_job(report, "android_package")
    assert job["status"] == "failed"
    assert job["error"]["code"] == "missing_toolchain"
    assert all(not item["name"].endswith((".apk", ".aab")) for item in job["artifacts"])


def test_analysis_job_completes():
    report = analyze_entries(["project.godot"])
    job = run_job(report, "analysis_report")
    assert job["status"] == "completed"
    assert job["progress"] == 100


def test_cancel_job():
    report = analyze_entries(["notes/readme.txt"])
    job = run_job(report, "android_package", cancel=True)
    assert job["status"] == "cancelled"


def test_api_analyze_and_slip():
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["version"] == "0.2.0"
    assert health.json()["native_apk_from_upload_alone"] is False

    engines = client.get("/api/engines")
    assert engines.status_code == 200
    assert any(e["engine"] == "Unity" for e in engines.json()["engines"])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "project.godot",
            'config_version=5\nconfig/features=PackedStringArray("4.3")\n',
        )
    buf.seek(0)
    response = client.post(
        "/api/analyze",
        files={"file": ("game.zip", buf.getvalue(), "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "Godot"
    assert body["native_apk_buildable_from_upload_alone"] is False

    slip = io.BytesIO()
    with zipfile.ZipFile(slip, "w") as zf:
        zf.writestr("../evil.txt", "nope")
    denied = client.post(
        "/api/analyze",
        files={"file": ("bad.zip", slip.getvalue(), "application/zip")},
    )
    assert denied.status_code == 400
