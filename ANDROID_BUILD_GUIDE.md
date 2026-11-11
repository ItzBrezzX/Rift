# Android build guide

This worker does **not** ship an SDK.

## What a real package needs

- `AndroidManifest.xml`
- `classes.dex` (or numbered dex) unless pure-native and intentional
- `lib/arm64-v8a/*.so` when the game has native code
- Signing keys you control
- A target SDK that Play currently accepts

Structure validation in the analyzer checks the first three when a manifest is present. It does not sign, align, or install.

## Pin tool versions to the engine

- Unity: the editor’s own Android SDK/NDK/JDK modules  
- Unreal: SDK/NDK listed for that engine’s Turnkey setup  
- Godot 4: JDK 17 and the SDK/NDK the export docs name; templates must match exactly  

## What this repository will not automate

- Accepting SDK licenses on your behalf  
- Embedding a debug keystore  
- Downloading NDK archives during analysis  
- Rewrapping a Windows EXE as `lib/arm64-v8a`  
