# Research notes (v0.2)

## Unity

- Source: `ProjectSettings/ProjectVersion.txt`, `Assets/`, `Packages/manifest.json`.  
- Player: `UnityPlayer.dll`, `*_Data/`, optional `GameAssembly.dll` (IL2CPP).  
- CLI: `Unity -batchmode -quit -projectPath … -buildTarget Android -executeMethod …`  
- Windows IL2CPP output is **not** convertible to Android.  
- Docs: https://docs.unity3d.com/Manual/build-command-line.html

## Unreal

- Source: `.uproject` + `EngineAssociation`, `*.Build.cs`, `Config/`.  
- Packaging: `RunUAT BuildCookRun -platform=Android`.  
- Windows Shipping builds are not Android cooks.

## Godot

- `project.godot` with `config_version` / `config/features`.  
- CLI: `godot --headless --export-release "Android" out.apk` requires preset + templates.

## Algorithms used

- Weighted multi-signal evidence (not ML).  
- Confidence saturation formula.  
- Static PE COFF/optional-header walk for machine and import table.  
- ZIP safety via path validation before any extract.  
- Job state machine with stage-tied progress.
