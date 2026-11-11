# Porting guide

## Source project (Unity / Unreal / Godot)

Use that engine’s Android exporter. Match the editor version the project was saved with.

**Unity** (after adding a `BuildPipeline.BuildPlayer` method):

```bash
Unity -batchmode -quit -projectPath "$PWD" -buildTarget Android -executeMethod AndroidBatch.Build -logFile -
```

**Unreal:**

```bash
RunUAT BuildCookRun -project="$PWD/Game.uproject" -platform=Android -clientconfig=Development -cook -stage -pak -archive
```

**Godot** (Android preset + templates required):

```bash
godot --headless --export-release "Android" build/game.apk
```

A non-zero exit means there is no package. Do not zip the project and rename it.

## Windows build only

Stop. Identification is the result. Compatibility apps (Wine / Winlator / Box64) are separate tests and are **not** Play-native builds. This project will not download them for you.

## Web-based (HTML5 / RPG Maker)

Export HTML5 from the original tool. A WebView shell is an Android app **you** maintain.

## C++ or desktop Java

Replace DirectX, desktop OpenGL, Win32 input, and LWJGL. Rebuild as ELF for `arm64-v8a`.

## After any APK exists

Confirm `AndroidManifest.xml`, `classes.dex` or native libraries, and `arm64-v8a` if native. Then install it. Structure is not gameplay.
