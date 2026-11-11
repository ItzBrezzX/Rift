# Installation

## Analysis only

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Docker

```bash
docker compose up --build
```

The container does **not** contain Unity, Unreal, Godot, or the Android SDK.

## Toolchain for real exports (separate install)

Install on a machine you control:

- Unity Hub + editor version from `ProjectVersion.txt` + Android Build Support  
- Unreal Engine matching `EngineAssociation` + Android Turnkey  
- Godot matching `config/features` + export templates + JDK 17 + Android SDK  
- Android CLI tools if building Gradle projects  

Export the env vars listed in the README. The worker only **checks** that paths exist; it does not launch a full cook in v0.2.

## Termux

`pkg install python` + `pip install -r requirements.txt` is enough to analyze small ZIPs. Unity/Unreal cooks need a desktop or CI runner.
