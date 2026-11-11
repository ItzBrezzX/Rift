"""Multi-signal project classification.

Confidence = sum(weights) / (sum(weights) + 36), plus 0.03 or 0.06 when two or
three independent evidence layers agree, capped at 0.97. One weak filename is
not enough to claim certainty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.pe.parser import parse_pe

SATURATION = 36


@dataclass
class Evidence:
    id: str
    layer: str
    weight: int
    description: str
    path: str | None = None


@dataclass
class Finding:
    id: str
    severity: str
    title: str
    detail: str
    action: str


@dataclass
class InventoryFile:
    path: str
    size: int = 0
    text: str | None = None
    head: bytes | None = None


def confidence(evidence: list[Evidence]) -> float:
    if not evidence:
        return 0.0
    total = sum(max(0, item.weight) for item in evidence)
    layers = len({item.layer for item in evidence})
    raw = total / (total + SATURATION)
    bonus = 0.06 if layers >= 3 else 0.03 if layers == 2 else 0.0
    return round(min(0.97, raw + bonus), 3)


def _paths(files: list[InventoryFile]) -> list[str]:
    return [f.path.replace("\\", "/").lower() for f in files]


def _has_dir(paths: list[str], directory: str) -> bool:
    d = directory.lower()
    return any(p == d or p.startswith(d + "/") or f"/{d}/" in p for p in paths)


def _suffix(paths: list[str], suffix: str) -> str | None:
    s = suffix.lower()
    return next((p for p in paths if p == s or p.endswith("/" + s)), None)


def _text(files: list[InventoryFile], pred) -> str:
    return "\n".join(f.text or "" for f in files if f.text and pred(f.path.lower()))


def _heads(files: list[InventoryFile]) -> bytes:
    return b"\n".join(f.head or b"" for f in files if f.head)


def analyze_files(files: list[InventoryFile], archive_name: str = "inventory") -> dict:
    paths = _paths(files)
    evidence: list[Evidence] = []
    engine = "Unknown"
    version: str | None = None
    runtime: str | None = None
    classification = "unknown"
    strategy = "generic_preparation"
    alternatives: list[dict] = []

    # --- Unity ---
    version_file = _suffix(paths, "projectsettings/projectversion.txt")
    version_text = _text(files, lambda p: p.endswith("projectsettings/projectversion.txt"))
    settings = _text(files, lambda p: p.endswith("projectsettings/projectsettings.asset"))
    match = re.search(
        r"m_EditorVersion:\s*(\d{4}\.\d+\.\d+[a-z]\d+|6000\.\d+\.\d+[a-z]\d+)",
        version_text,
        re.I,
    )
    unity_version = match.group(1) if match else None
    player = _suffix(paths, "unityplayer.dll")
    game_assembly = _suffix(paths, "gameassembly.dll")
    data_dir = any(re.search(r"(^|/)[^/]+_data(/|$)", p) for p in paths)
    globalgm = any(p.endswith("/globalgamemanagers") or p.endswith("globalgamemanagers") for p in paths)
    managed = any("managed/assembly-csharp" in p or "monobleedingedge" in p for p in paths)

    if version_file:
        evidence.append(
            Evidence("unity-project-version", "structure", 36, "ProjectSettings/ProjectVersion.txt.", version_file)
        )
        if _has_dir(paths, "assets"):
            evidence.append(Evidence("unity-assets", "structure", 18, "Assets directory."))
        if _has_dir(paths, "projectsettings"):
            evidence.append(Evidence("unity-projectsettings", "structure", 12, "ProjectSettings directory."))
        if _suffix(paths, "packages/manifest.json"):
            evidence.append(Evidence("unity-manifest", "metadata", 22, "Package Manager manifest."))
        if unity_version:
            evidence.append(Evidence("unity-editor-version", "metadata", 14, unity_version, version_file))
            version = unity_version
        if re.search(r"scriptingBackend:\s*.*Android:\s*1", settings, re.S):
            runtime = "il2cpp"
        elif re.search(r"scriptingBackend:\s*.*Android:\s*0", settings, re.S):
            runtime = "mono"
        engine, classification, strategy = "Unity", "source_project", "native_engine_export"
        if any(re.search(r"(^|/)assets/plugins/.+\.dll$", p) for p in paths):
            pass  # finding added later
    elif player or (data_dir and (game_assembly or globalgm or managed)):
        if player:
            evidence.append(Evidence("unity-player-dll", "binary", 40, "UnityPlayer.dll player runtime.", player))
        if data_dir:
            evidence.append(Evidence("unity-data-dir", "structure", 24, "Unity *_Data directory."))
        if game_assembly:
            evidence.append(Evidence("unity-il2cpp", "binary", 18, "GameAssembly.dll IL2CPP player.", game_assembly))
            runtime = "il2cpp"
        elif managed:
            evidence.append(Evidence("unity-mono", "binary", 14, "Mono player assemblies."))
            runtime = "mono"
        if globalgm:
            evidence.append(Evidence("unity-globalgm", "structure", 12, "globalgamemanagers resource."))
        blob = _heads(files)
        ver = re.search(rb"((?:6000|\d{4})\.\d+\.\d+[abfcp]\d+)", blob)
        if ver:
            version = ver.group(1).decode()
            evidence.append(Evidence("unity-player-version-string", "binary", 10, version))
        engine, classification, strategy = "Unity", "windows_player", "compatibility_layer"

    # --- Unreal ---
    uproject = next((p for p in paths if p.endswith(".uproject")), None)
    if uproject and engine == "Unknown":
        evidence.append(Evidence("unreal-uproject", "structure", 46, ".uproject descriptor.", uproject))
        raw = _text(files, lambda p: p.endswith(".uproject"))
        try:
            parsed = json.loads(raw)
            assoc = str(parsed.get("EngineAssociation") or "")
            if assoc and not re.fullmatch(r"[0-9a-f-]{30,}", assoc, re.I):
                version = assoc
                evidence.append(Evidence("unreal-engine-association", "metadata", 16, assoc, uproject))
            elif assoc:
                evidence.append(Evidence("unreal-engine-guid", "metadata", 8, "EngineAssociation is a GUID.", uproject))
        except json.JSONDecodeError:
            pass
        if _suffix(paths, "config/defaultengine.ini"):
            evidence.append(Evidence("unreal-default-engine", "metadata", 14, "DefaultEngine.ini."))
        if any(p.endswith(".build.cs") for p in paths):
            evidence.append(Evidence("unreal-build-cs", "structure", 16, "Build.cs module rules."))
        if any(p.endswith(".target.cs") for p in paths):
            evidence.append(Evidence("unreal-target-cs", "structure", 10, "Target.cs."))
        if _has_dir(paths, "content"):
            evidence.append(Evidence("unreal-content", "structure", 8, "Content directory."))
        engine, classification, strategy = "Unreal Engine", "source_project", "native_engine_export"
    elif engine == "Unknown" and (
        any(re.search(r"win64-shipping\.exe$", p) for p in paths)
        or any(p.endswith("ue4game.exe") or p.endswith("unrealgame.exe") for p in paths)
    ):
        evidence.append(Evidence("unreal-shipping-exe", "binary", 28, "Unreal Shipping executable."))
        engine, classification, strategy = "Unreal Engine", "windows_player", "compatibility_layer"

    # --- Godot ---
    godot = _suffix(paths, "project.godot")
    if godot and engine in ("Unknown", "Android"):
        evidence.append(Evidence("godot-project", "structure", 52, "project.godot.", godot))
        text = _text(files, lambda p: p.endswith("project.godot"))
        feat = re.search(r'"(\d+\.\d+(?:\.\d+)?)"', text)
        if feat:
            version = feat.group(1)
            evidence.append(Evidence("godot-feature", "metadata", 14, version, godot))
        cfg = re.search(r"config_version\s*=\s*(\d+)", text)
        if cfg and not version:
            version = "4.x" if cfg.group(1) == "5" else "3.x" if cfg.group(1) == "4" else None
        if _suffix(paths, "export_presets.cfg"):
            evidence.append(Evidence("godot-export-presets", "metadata", 10, "export_presets.cfg present."))
        runtime = "csharp" if any(p.endswith(".csproj") for p in paths) else "gdscript"
        engine, classification, strategy = "Godot", "source_project", "native_engine_export"
    elif engine == "Unknown" and any(p.endswith(".pck") for p in paths):
        evidence.append(Evidence("godot-pck", "signature", 34, "Godot .pck pack."))
        engine, classification, strategy = "Godot", "windows_player", "compatibility_layer"

    # --- GameMaker ---
    yyp = next((p for p in paths if p.endswith(".yyp")), None)
    if yyp and engine == "Unknown":
        evidence.append(Evidence("gamemaker-yyp", "structure", 42, "GameMaker .yyp.", yyp))
        yyp_text = _text(files, lambda p: p.endswith(".yyp"))
        if '"resourceType"' in yyp_text and "GMProject" in yyp_text:
            evidence.append(Evidence("gamemaker-resource-type", "metadata", 18, "resourceType GMProject."))
        ide = re.search(r'"IDEVersion"\s*:\s*"([^"]+)"', yyp_text)
        version = ide.group(1) if ide else None
        engine, classification, strategy = "GameMaker", "source_project", "native_engine_export"

    # --- Ren'Py ---
    if engine == "Unknown" and (
        any(p.endswith(".rpy") for p in paths) or any("/renpy/common/" in p for p in paths)
    ):
        if any(p.endswith(".rpy") for p in paths):
            evidence.append(Evidence("renpy-script", "structure", 28, "Ren'Py .rpy script."))
        if any("/renpy/common/" in p or p.endswith("renpy/__init__.py") for p in paths):
            evidence.append(Evidence("renpy-runtime", "structure", 24, "Bundled Ren'Py runtime."))
        vc = re.search(
            r"vc_version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)",
            _text(files, lambda p: p.endswith("__init__.py")),
        )
        version = ".".join(vc.groups()) if vc else None
        runtime = "python"
        engine, classification, strategy = "Ren'Py", "source_project", "native_engine_export"

    # --- RPG Maker ---
    if engine == "Unknown" and (
        _suffix(paths, "rmmz_core.js")
        or _suffix(paths, "rmmz_managers.js")
        or _suffix(paths, "rpg_core.js")
        or _suffix(paths, "game.rpgproject")
    ):
        if _suffix(paths, "rmmz_core.js") or _suffix(paths, "rmmz_managers.js"):
            evidence.append(Evidence("rpg-mz", "signature", 40, "RPG Maker MZ core script."))
            version = "MZ"
        if _suffix(paths, "rpg_core.js"):
            evidence.append(Evidence("rpg-mv", "signature", 40, "RPG Maker MV rpg_core.js."))
            version = version or "MV"
        if _suffix(paths, "game.rpgproject"):
            evidence.append(Evidence("rpg-project", "structure", 18, "Game.rpgproject."))
        engine, classification, strategy = "RPG Maker", "web_project", "project_migration"
        runtime = "javascript"

    # --- Cocos ---
    if engine == "Unknown":
        body = _text(files, lambda p: p.endswith("project.json") or p.endswith("cocos-project.json"))
        if re.search(r"cocos-creator|cocos2d", body, re.I) or any("cocos2d" in p for p in paths):
            evidence.append(Evidence("cocos-project", "metadata", 36, "Cocos project fingerprint."))
            engine, classification, strategy = "Cocos", "source_project", "native_engine_export"

    # --- Defold ---
    if engine == "Unknown" and _suffix(paths, "game.project"):
        gp = _text(files, lambda p: p.endswith("game.project"))
        if not gp or re.search(r"\[(project|bootstrap|display|input)\]", gp):
            evidence.append(Evidence("defold-game-project", "structure", 46, "Defold game.project."))
            if "[bootstrap]" in gp:
                evidence.append(Evidence("defold-bootstrap", "metadata", 12, "Defold [bootstrap] section."))
            engine, classification, strategy = "Defold", "source_project", "native_engine_export"
            runtime = "lua"

    # --- LibGDX ---
    gradle = _text(
        files,
        lambda p: p.endswith("build.gradle")
        or p.endswith("build.gradle.kts")
        or p.endswith("gradle.properties"),
    )
    if engine == "Unknown" and ("com.badlogicgames.gdx" in gradle or "gdxVersion" in gradle):
        evidence.append(Evidence("libgdx-gradle", "dependency", 40, "libGDX Gradle coordinate."))
        gdx = re.search(r"gdxVersion\s*=\s*['\"]([^'\"]+)['\"]", gradle)
        version = gdx.group(1) if gdx else None
        if _has_dir(paths, "core") and _has_dir(paths, "android"):
            evidence.append(Evidence("libgdx-modules", "structure", 16, "core and android modules."))
            strategy = "native_engine_export"
        else:
            strategy = "project_migration"
        engine, classification, runtime = "LibGDX", "java_project", "java"

    # --- MonoGame ---
    if engine == "Unknown" and (
        any(p.endswith(".mgcb") for p in paths)
        or "MonoGame" in _text(files, lambda p: p.endswith(".csproj"))
    ):
        if any(p.endswith(".mgcb") for p in paths):
            evidence.append(Evidence("monogame-mgcb", "structure", 28, "MonoGame .mgcb content."))
        if "MonoGame" in _text(files, lambda p: p.endswith(".csproj")):
            evidence.append(Evidence("monogame-csproj", "dependency", 30, "MonoGame project reference."))
        engine, classification, strategy = "MonoGame", "source_project", "project_migration"
        runtime = "csharp"

    # --- LÖVE ---
    if engine == "Unknown" and _suffix(paths, "main.lua"):
        main_t = _text(files, lambda p: p.endswith("main.lua"))
        conf = _suffix(paths, "conf.lua")
        if conf or "love." in main_t:
            evidence.append(Evidence("love-main", "structure", 22, "main.lua entry."))
            if conf:
                evidence.append(Evidence("love-conf", "structure", 18, "conf.lua."))
            if "love." in main_t:
                evidence.append(Evidence("love-api", "metadata", 16, "love API calls."))
            engine, classification, strategy = "LÖVE", "source_project", "project_migration"
            runtime = "lua"

    # --- Electron ---
    pkg = _text(files, lambda p: p.endswith("package.json"))
    if engine == "Unknown" and re.search(r'"electron"\s*:', pkg):
        evidence.append(Evidence("electron-dep", "dependency", 36, "electron dependency."))
        em = re.search(r'"electron"\s*:\s*"([^"]+)"', pkg)
        version = em.group(1) if em else None
        engine, classification, strategy = "Electron", "source_project", "project_migration"
        runtime = "javascript"
    elif engine == "Unknown" and any(p.endswith(".asar") or "app.asar" in p for p in paths):
        evidence.append(Evidence("electron-asar", "signature", 30, "Electron app.asar."))
        engine, classification, strategy = "Electron", "windows_player", "project_migration"

    # --- HTML5 ---
    if engine == "Unknown":
        html = _text(files, lambda p: p.endswith("index.html"))
        if re.search(r"phaser|pixi\.js|pixi\.min|three\.js|three\.min|babylon|playcanvas|melonjs", html, re.I):
            evidence.append(Evidence("html5-lib", "dependency", 34, "HTML5 game library in index.html."))
            engine, classification, strategy = "HTML5", "web_project", "project_migration"
            runtime = "javascript"
        elif re.search(r"<canvas\b", html, re.I):
            evidence.append(Evidence("html5-canvas", "structure", 16, "index.html contains canvas."))
            # weak alone — need more weight
            if sum(e.weight for e in evidence) >= 24:
                engine, classification, strategy = "HTML5", "web_project", "project_migration"

    # --- Android package ---
    manifest = _suffix(paths, "androidmanifest.xml")
    dex = any(re.search(r"(^|/)classes\d*\.dex$", p) for p in paths)
    if manifest and (dex or any("/lib/arm" in p or "/lib/x86" in p for p in paths)) and engine == "Unknown":
        evidence.append(Evidence("android-manifest", "structure", 28, "AndroidManifest.xml.", manifest))
        if dex:
            evidence.append(Evidence("android-dex", "signature", 30, "classes.dex."))
        engine, classification, strategy = "Android", "android_package", "already_android"
        runtime = "dalvik"

    # --- Java ---
    if engine == "Unknown" and (
        any(p.endswith(".java") for p in paths)
        or any(p.endswith(".jar") for p in paths)
        or _suffix(paths, "pom.xml")
        or any(p.endswith(".class") for p in paths)
    ):
        if _suffix(paths, "pom.xml"):
            evidence.append(Evidence("java-pom", "metadata", 22, "Maven pom.xml."))
        if any(p.endswith(".java") for p in paths):
            evidence.append(Evidence("java-source", "structure", 16, "Java source."))
        if any(p.endswith(".jar") for p in paths):
            evidence.append(Evidence("java-jar", "signature", 18, "JAR archive."))
        if any("lwjgl" in p for p in paths):
            evidence.append(Evidence("java-lwjgl", "dependency", 14, "LWJGL present."))
            runtime = "lwjgl"
        else:
            runtime = "jvm"
        engine, classification, strategy = "Java", "java_project", "project_migration"

    # --- .NET ---
    pe_hits = []
    for f in files:
        if f.head and len(f.head) >= 2 and f.head[:2] == b"MZ":
            pe = parse_pe(f.head)
            pe_hits.append((f.path, pe))
            if pe.is_dotnet and engine == "Unknown":
                evidence.append(Evidence("dotnet-clr", "binary", 36, "PE CLR data directory.", f.path))
                engine, classification, strategy = ".NET", "windows_player", "project_migration"
                runtime = "clr"

    # --- Custom C/C++ ---
    if engine == "Unknown":
        if _suffix(paths, "cmakelists.txt"):
            evidence.append(Evidence("native-cmake", "structure", 28, "CMakeLists.txt."))
        if any(p.endswith(".vcxproj") for p in paths):
            evidence.append(Evidence("native-vcxproj", "structure", 18, "Visual C++ project."))
        if any(p.endswith(".sln") for p in paths):
            evidence.append(Evidence("native-sln", "structure", 10, "Visual Studio solution."))
        if _suffix(paths, "makefile"):
            evidence.append(Evidence("native-make", "structure", 14, "Makefile."))
        strong = sum(e.weight for e in evidence if e.id != "native-sln")
        if strong >= 24:
            engine, classification, strategy = "Custom C/C++", "source_project", "project_migration"
            runtime = "native"
        elif pe_hits and not evidence:
            path, pe = pe_hits[0]
            if pe.valid and not pe.is_dotnet:
                evidence.append(
                    Evidence("native-pe", "binary", 26, f"PE machine {pe.machine_name}.", path)
                )
                engine, classification, strategy = "Custom C/C++", "windows_player", "compatibility_layer"
                runtime = "native"

    score = confidence(evidence) if engine != "Unknown" else 0.0
    if engine != "Unknown" and (score < 0.3 or sum(e.weight for e in evidence) < 24):
        engine, classification, strategy, score = "Unknown", "unknown", "generic_preparation", 0.0
        evidence = []

    findings = _findings(engine, classification, runtime, strategy, paths, pe_hits)
    apk = _apk(paths) if manifest else None

    legacy_type = {
        "windows_player": "windows_build",
        "java_project": "java_archive",
        "unknown": "unknown",
    }.get(classification, classification)
    legacy_route = {
        "native_engine_export": "native_android_export",
        "compatibility_layer": "compatibility_or_rebuild",
        "project_migration": "source_review_required",
        "already_android": "existing_android_package",
        "generic_preparation": "manual_inspection",
    }.get(strategy, "manual_inspection")

    return {
        "version": "0.2.0",
        "archive_name": archive_name,
        "engine": engine,
        "engine_version": version,
        "runtime": runtime,
        "project_type": legacy_type,
        "classification": classification,
        "strategy": strategy,
        "recommended_route": legacy_route,
        "confidence": score,
        "native_apk_buildable_from_upload_alone": False,
        "file_count": len([f for f in files if not f.path.endswith("/")]),
        "evidence": [e.__dict__ for e in evidence],
        "alternatives": alternatives,
        "findings": [f.__dict__ for f in findings],
        "plan": _plan(engine, strategy, version),
        "android_validation": apk,
        "pe_summary": [
            {
                "path": path,
                "valid": pe.valid,
                "machine": pe.machine_name,
                "is_dotnet": pe.is_dotnet,
                "imports": pe.imports[:20],
            }
            for path, pe in pe_hits[:10]
        ],
        "warnings": [
            "Detection is multi-signal and still heuristic. It does not prove the project compiles.",
            "A Windows IL2CPP or packaged player cannot be converted into a native Android package.",
            "This report never claims a successful port. Export, compile, and device tests are separate stages.",
            "No proprietary engine, SDK, NDK, or compatibility runtime is downloaded.",
        ],
        "limitations": [
            "Binary inspection covers a prefix of executables and DLLs, not a full disassembly.",
            "Upload alone never produces an APK. Official toolchains must be installed separately.",
            "Compatibility-layer findings are not native ports.",
        ],
        "legacy": {
            "project_type": legacy_type,
            "recommended_route": legacy_route,
            "native_apk_buildable_from_upload_alone": False,
        },
    }


def analyze_entries(names: list[str]) -> dict:
    from app.security.archive import validate_zip_names

    clean = validate_zip_names(names)
    return analyze_files([InventoryFile(path=name) for name in clean])


def _findings(
    engine: str,
    classification: str,
    runtime: str | None,
    strategy: str,
    paths: list[str],
    pe_hits: list,
) -> list[Finding]:
    found: list[Finding] = []
    if classification == "windows_player":
        found.append(
            Finding(
                "player-not-source",
                "unsupported",
                "Compiled player is not a native Android project",
                f"{engine} Windows player files can be identified, but they are not an editable source project. "
                "Repacking an EXE or DLL into an APK does not produce a native port.",
                "Obtain the original source project and use that engine's Android exporter. "
                "A compatibility runtime is a separate, non-native option.",
            )
        )
        found.append(
            Finding(
                "compatibility-layer",
                "potentially_compatible",
                "Compatibility runtime is not a port",
                "Wine, Winlator, and Box64/FEX can sometimes run Windows binaries on Android. "
                "That is emulation or translation, not a Play-native build. This engine does not download those runtimes.",
                "Treat any compatibility test as a device experiment. Record GPU, ABI, and input failures separately.",
            )
        )
    if strategy == "native_engine_export" and classification == "source_project":
        found.append(
            Finding(
                "toolchain-required",
                "potentially_compatible",
                "Native export depends on an installed toolchain",
                f"{engine} can target Android from source when the matching editor, Android SDK, "
                "and required NDK or export templates are installed. This worker will not invent a package.",
                "Install the engine version reported, then run the official command from the porting plan.",
            )
        )
    if engine == "Unity" and runtime == "il2cpp" and classification == "windows_player":
        found.append(
            Finding(
                "il2cpp-irreversible",
                "unsupported",
                "IL2CPP player output is not convertible back to a project",
                "GameAssembly.dll is generated C++ compiled for Windows. It is not a Unity project and not an Android library.",
                "Do not decompile as a porting plan. Recover the Unity project that produced this player.",
            )
        )
    if engine == "Unity" and classification == "source_project":
        plugins = [p for p in paths if re.search(r"(^|/)assets/plugins/.+\.dll$", p)]
        if plugins:
            found.append(
                Finding(
                    "unity-native-plugins",
                    "requires_modification",
                    "Windows native plugins",
                    f"{len(plugins)} DLL plugin path(s) under Assets/Plugins. Android needs .so or .aar for arm64-v8a.",
                    "Replace each Windows-only plugin before the IL2CPP Android build.",
                )
            )
        found.append(
            Finding(
                "unity-il2cpp-arm64",
                "potentially_compatible",
                "Google Play requires 64-bit",
                "Unity Android shipping builds use IL2CPP for ARM64. Mono Android is not a Play-ready 64-bit strategy.",
                "Install Android Build Support. Set scripting backend to IL2CPP and enable ARM64.",
            )
        )
    if engine == "Unreal Engine":
        found.append(
            Finding(
                "unreal-sdk",
                "potentially_compatible" if classification == "source_project" else "unsupported",
                "Unreal Android packaging needs the engine toolchain",
                "RunUAT BuildCookRun -platform=Android needs a full engine install and matching Android SDK/NDK.",
                "Install the engine named by EngineAssociation and the Android Turnkey prerequisites.",
            )
        )
    if engine == "Godot":
        presets = any(p.endswith("export_presets.cfg") for p in paths)
        found.append(
            Finding(
                "godot-templates",
                "potentially_compatible" if presets else "requires_modification",
                "Godot CLI export needs a preset and templates" if not presets else "Godot export preset found",
                "godot --headless --export-release uses an export preset by name and matching Android export templates.",
                "Create an Android export preset and install templates for this version."
                if not presets
                else "Confirm the preset platform is Android and templates match the editor version.",
            )
        )
    if engine == "Electron":
        found.append(
            Finding(
                "electron-no-android",
                "unsupported",
                "Electron does not target Android",
                "The Electron shell is a desktop Chromium + Node runtime with no official Android exporter.",
                "If the game is plain HTML5 underneath, port that web build with a WebView wrapper.",
            )
        )
    if engine in ("HTML5", "RPG Maker"):
        found.append(
            Finding(
                "webview-wrapper",
                "requires_modification",
                "Web content can be wrapped, not magically rebuilt",
                "A WebView or Trusted Web Activity shell can load an HTML5 build. That is not a native engine port.",
                "Export HTML5 from the original tool, then decide if a WebView shell is acceptable.",
            )
        )
    if engine == "LÖVE":
        found.append(
            Finding(
                "love-android",
                "requires_modification",
                "LÖVE has no first-party Android exporter in this pipeline",
                "Desktop LÖVE games need a community love-android port that is version-sensitive.",
                "Pin the LÖVE version and evaluate a maintained Android port manually.",
            )
        )
    if engine == "LibGDX":
        has_android = any("android/" in p or p.startswith("android/") for p in paths)
        found.append(
            Finding(
                "libgdx-backend",
                "potentially_compatible" if has_android else "requires_modification",
                "Android Gradle module is present" if has_android else "Desktop libGDX module is not an APK",
                "libGDX ships an Android backend, but LWJGL desktop natives are not that backend.",
                "Build the android module with the Android SDK."
                if has_android
                else "Add an android module and move desktop-only LWJGL calls behind the core API.",
            )
        )
    if engine == "Java" and runtime == "lwjgl":
        found.append(
            Finding(
                "lwjgl-desktop",
                "unsupported",
                "LWJGL desktop natives are not Android",
                "LWJGL's OpenGL and GLFW stack targets desktop.",
                "Identify whether this is libGDX or a desktop-only LWJGL game before choosing a backend.",
            )
        )
    if engine == ".NET":
        found.append(
            Finding(
                "dotnet-framework",
                "requires_modification",
                ".NET Windows binaries are not converted by this engine",
                "A CLR header means managed Windows code. There is no general IL-to-APK compiler here.",
                "A mobile rewrite would be a separate product and still needs a UI and graphics port.",
            )
        )
    # PE / DirectX findings
    for path, pe in pe_hits:
        if not pe.valid:
            continue
        imports_lower = [i.lower() for i in pe.imports]
        if any(x in " ".join(imports_lower) for x in ("d3d11", "d3d12", "d3d9", "dxgi")):
            if not any(f.id == "directx" for f in found):
                found.append(
                    Finding(
                        "directx",
                        "unsupported",
                        "DirectX is not available on Android",
                        "The binary references a DirectX DLL. Android graphics are OpenGL ES or Vulkan.",
                        "Use the engine's mobile renderer. A DirectX backend cannot be linked on Android.",
                    )
                )
        if pe.machine_name in ("x86", "x64"):
            if not any(f.id == "pe-abi" for f in found):
                found.append(
                    Finding(
                        "pe-abi",
                        "unsupported",
                        "Windows PE architecture is not an Android ABI",
                        f"Inspected PE machine: {pe.machine_name}. Android expects ELF for arm64-v8a.",
                        "Rebuild from source for arm64-v8a. Do not rename the PE and call it an APK.",
                    )
                )
    if engine == "Unknown":
        found.append(
            Finding(
                "unknown-engine",
                "unknown",
                "No supported engine identified",
                "Evidence stayed under the threshold for a known engine.",
                "Inspect the inventory, identify the build system, and add an adapter only after the fingerprint is confirmed.",
            )
        )
    return found


def _plan(engine: str, strategy: str, version: str | None) -> dict:
    version_bit = f" {version}" if version else ""
    command = None
    steps: list[dict] = []
    docs: list[dict] = []

    if strategy == "native_engine_export" and engine == "Unity":
        command = (
            "Unity -batchmode -quit -projectPath <project> "
            "-buildTarget Android -executeMethod AndroidBatch.Build -logFile -"
        )
        steps = [
            {
                "id": "install",
                "title": "Install the matching editor",
                "detail": f"Install Unity{version_bit} plus Android Build Support, SDK, NDK, and JDK modules.",
                "executed": False,
            },
            {
                "id": "method",
                "title": "Add a batch build method",
                "detail": "A project method must call BuildPipeline.BuildPlayer for BuildTarget.Android.",
                "command": command,
                "executed": False,
            },
            {
                "id": "il2cpp",
                "title": "Target ARM64 with IL2CPP",
                "detail": "Enable ARM64. Mono Android players are not the Play 64-bit path.",
                "executed": False,
            },
        ]
        docs = [
            {"title": "Unity command-line builds", "url": "https://docs.unity3d.com/Manual/build-command-line.html"},
            {"title": "Unity Android", "url": "https://docs.unity3d.com/Manual/android.html"},
            {"title": "Unity IL2CPP", "url": "https://docs.unity3d.com/Manual/IL2CPP.html"},
        ]
    elif strategy == "native_engine_export" and engine == "Unreal Engine":
        command = (
            "RunUAT BuildCookRun -project=<Game>.uproject -platform=Android "
            "-clientconfig=Development -cook -stage -pak -archive"
        )
        steps = [
            {
                "id": "engine",
                "title": "Install that engine version",
                "detail": f"EngineAssociation{version_bit or ' must resolve to an installed engine'}.",
                "executed": False,
            },
            {
                "id": "uat",
                "title": "Package with Automation Tool",
                "detail": "Cook and stage for Android. This command is a plan, not a process this worker launched.",
                "command": command,
                "executed": False,
            },
        ]
        docs = [
            {
                "title": "Unreal Android requirements",
                "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/android-development-requirements-for-unreal-engine",
            },
            {
                "title": "Unreal Android packaging",
                "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/packaging-android-projects-in-unreal-engine",
            },
        ]
    elif strategy == "native_engine_export" and engine == "Godot":
        command = 'godot --headless --export-release "Android" build/game.apk'
        steps = [
            {
                "id": "templates",
                "title": "Install export templates",
                "detail": "Templates must match the editor version exactly.",
                "executed": False,
            },
            {
                "id": "export",
                "title": "Export from the command line",
                "detail": "Requires a named Android export preset.",
                "command": command,
                "executed": False,
            },
        ]
        docs = [
            {
                "title": "Godot Android export",
                "url": "https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html",
            },
            {
                "title": "Godot command-line export",
                "url": "https://docs.godotengine.org/en/stable/tutorials/export/exporting_projects.html",
            },
        ]
    elif engine == "LibGDX":
        command = "./gradlew :android:assembleDebug"
        steps = [
            {
                "id": "module",
                "title": "Build the android module",
                "detail": "Use Gradle once ANDROID_HOME is set.",
                "command": command,
                "executed": False,
            }
        ]
        docs = [{"title": "libGDX Android", "url": "https://libgdx.com/wiki/app/android"}]
    elif strategy == "compatibility_layer":
        steps = [
            {
                "id": "source",
                "title": "Recover source",
                "detail": f"A native {engine} Android build starts from the source project, not from the Windows player.",
                "executed": False,
            },
            {
                "id": "compat",
                "title": "Optional compatibility experiment",
                "detail": "Wine, Winlator, or Box64 may be evaluated on a device you control. This is not a native port.",
                "executed": False,
            },
        ]
        docs = [
            {"title": "PE format", "url": "https://learn.microsoft.com/en-us/windows/win32/debug/pe-format"},
            {"title": "Android ABIs", "url": "https://developer.android.com/ndk/guides/abis"},
        ]
    elif strategy == "already_android":
        steps = [
            {
                "id": "validate",
                "title": "Validate package structure",
                "detail": "Confirm AndroidManifest.xml, classes.dex or native lib/<abi>, and META-INF.",
                "executed": False,
            }
        ]
        docs = [
            {
                "title": "Android manifest",
                "url": "https://developer.android.com/guide/topics/manifest/manifest-intro",
            }
        ]
    else:
        steps = [
            {
                "id": "deps",
                "title": "Replace platform dependencies",
                "detail": "Graphics, input, audio, and native libraries called out in findings must be ported or dropped.",
                "executed": False,
            },
            {
                "id": "build",
                "title": "Introduce a real Android build",
                "detail": "CMake with the NDK, Gradle, or the engine's exporter. Do not invent an APK.",
                "executed": False,
            },
        ]
        docs = [{"title": "Android ABIs", "url": "https://developer.android.com/ndk/guides/abis"}]

    return {
        "strategy": strategy,
        "summary": f"{engine}{version_bit}: {strategy.replace('_', ' ')}. Commands are plans, not running processes.",
        "command": command,
        "steps": steps,
        "official_docs": docs,
        "executed": False,
    }


def _apk(paths: list[str]) -> dict:
    abis = [
        abi
        for abi in ("arm64-v8a", "armeabi-v7a", "x86_64", "x86")
        if any(f"/lib/{abi}/" in p or p.startswith(f"lib/{abi}/") for p in paths)
    ]
    has_manifest = any(p.endswith("androidmanifest.xml") for p in paths)
    has_dex = any(re.search(r"(^|/)classes\d*\.dex$", p) for p in paths)
    has_resources = any(p.endswith("resources.arsc") for p in paths)
    has_meta = any("meta-inf/" in p for p in paths)
    notes = ["Structure checks do not prove the process starts, signs, or passes Play policy."]
    if not has_manifest:
        notes.insert(0, "AndroidManifest.xml is missing.")
    if not has_dex and not abis:
        notes.insert(0, "Neither classes.dex nor a native lib/<abi> payload is present.")
    if abis and "arm64-v8a" not in abis:
        notes.append("arm64-v8a is absent. Google Play requires 64-bit for native code.")
    return {
        "structurally_valid": has_manifest and (has_dex or bool(abis)),
        "has_manifest": has_manifest,
        "has_dex": has_dex,
        "has_resources": has_resources,
        "has_meta_inf": has_meta,
        "abis": abis,
        "notes": notes,
    }
