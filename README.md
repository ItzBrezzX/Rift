# KingBrezz Port Engine

**Version 0.2.0**

Self-hosted platform that inspects PC game projects and reports an **honest** Android porting path.

It is an analyzer, a compatibility checker, and a toolchain gate.  
It is **not** a universal EXE-to-APK converter.

---

## What it does

1. Accepts a ZIP and rejects path traversal, symlinks, encryption, and compression bombs.
2. Classifies the input as a source project, Windows player, Android package, web project, Java project, or unknown.
3. Scores evidence for Unity, Unreal, Godot, GameMaker, Ren'Py, RPG Maker, Cocos, Defold, libGDX, MonoGame, LÖVE, Electron, HTML5, Java, .NET, and custom C/C++.
4. Reads PE machine type, import names, and the CLR directory from a binary prefix. **Never executes the file.**
5. Writes a porting plan whose commands are **not** run unless you later point a real toolchain at them.
6. Fails an `android_package` job when Unity, Unreal, Godot, the Android SDK, NDK, or JDK is missing. **Does not create an APK.**

---

## What it cannot do

- Turn `GameAssembly.dll`, `UnityPlayer.dll`, or `*-Win64-Shipping.exe` into a native Android package.
- Download Unity, Unreal, the NDK, Wine, or Winlator.
- Prove that a structurally valid APK launches.
- Call a compatibility runtime a native port.
- Report `native_apk_buildable_from_upload_alone: true` (always false).

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

```bash
pytest -q
```

### Docker

```bash
docker compose up --build
```

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Service health |
| GET | `/api/toolchain` | SDK/editor probe |
| GET | `/api/engines` | Engine adapter matrix |
| POST | `/api/analyze` | Multipart field `file` (ZIP) |
| GET | `/api/reports/{id}` | Saved report |
| POST | `/api/jobs` | `{"report_id","target"}` |
| GET | `/api/jobs/{id}` | Job status |

**Job targets:** `analysis_report` · `android_package` · `validate_android_package`

**Environment**

| Variable | Default |
|----------|---------|
| `PORT_ENGINE_DATA_DIR` | `data` |
| `PORT_ENGINE_MAX_UPLOAD_BYTES` | 1 GiB |

**Toolchain probe (not auto-executed)**

| Variable | Tool |
|----------|------|
| `UNITY_EDITOR` | Unity editor binary |
| `UE_ROOT` | Unreal engine root (RunUAT) |
| `GODOT_BIN` | Godot binary |
| `ANDROID_HOME` / `ANDROID_SDK_ROOT` | Android SDK |
| `ANDROID_NDK_HOME` | NDK |
| `JAVA_HOME` | JDK |

---

## Detection method

Evidence is scored by layer (signature, structure, metadata, binary, dependency):

```
confidence = sum(weights) / (sum(weights) + 36)
           + 0.03 if 2 layers, +0.06 if ≥3 layers
           capped at 0.97
```

Candidates under total weight 24 are dropped. One filename is never enough.

**Strategies**

| Strategy | Meaning |
|----------|---------|
| `native_engine_export` | Source project; vendor has an Android exporter |
| `project_migration` | Possible only after code/packaging changes |
| `compatibility_layer` | Windows player — Wine/Winlator/Box64 are experiments, not ports |
| `generic_preparation` | Inventory + manual checklist |
| `already_android` | Validate existing package structure |

---

## Layout

```
app/
  main.py              FastAPI surface
  analyzer.py          v0.1 compatibility imports
  detection/analyzer.py  Multi-signal classifier
  pe/parser.py         Static PE inspection
  security/archive.py  ZIP-slip, bombs, symlinks
  adapters/registry.py Engine adapters (no fake builds)
  jobs/runner.py       Job state machine
  static/index.html    Minimal web UI
tests/test_engine.py
docs/
```

---

## Termux / mobile hosts

You can run **analysis** on small archives. You cannot cook Unity or Unreal on a phone. Use a Linux or Windows build machine with the editor installed.

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [INSTALLATION.md](INSTALLATION.md)
- [SUPPORTED_ENGINES.md](SUPPORTED_ENGINES.md)
- [PORTING_GUIDE.md](PORTING_GUIDE.md)
- [ANDROID_BUILD_GUIDE.md](ANDROID_BUILD_GUIDE.md)
- [SECURITY.md](SECURITY.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [CHANGELOG.md](CHANGELOG.md)

---

## License

MIT — see [LICENSE](LICENSE).
