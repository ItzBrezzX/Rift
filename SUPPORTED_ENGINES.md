# Supported engines

Detection is **not** a promise of a build. “Native export exists” means the vendor documents one.

| Engine | Recognition | Android path | This worker |
|--------|-------------|--------------|-------------|
| Unity source | `ProjectVersion.txt`, `Assets/`, `Packages/` | Editor + Android Build Support | Plan + gate |
| Unity Windows player | `UnityPlayer.dll`, `*_Data`, `GameAssembly.dll` | Not convertible | Compatibility report |
| Unreal source | `.uproject`, `Build.cs`, `DefaultEngine.ini` | RunUAT `-platform=Android` | Plan + gate |
| Unreal player | `*-Win64-Shipping.exe` | Not convertible | Compatibility report |
| Godot | `project.godot` | CLI export + templates | Plan + gate |
| GameMaker | `.yyp` / GMProject | IDE Android export | Plan only |
| Ren'Py | `.rpy`, `renpy/common` | RAPT | Plan only |
| RPG Maker MV/MZ | `rpg_core.js` / `rmmz_core.js` | No official APK | Migration notes |
| Cocos | `project.json` naming Cocos | Creator / CMake Android | Plan only |
| Defold | `game.project` | Editor / bob.jar | Plan only |
| libGDX | `gdx` Gradle coordinate | `:android:assembleDebug` | Plan only |
| MonoGame | `.mgcb` / MonoGame csproj | Retarget | Migration notes |
| LÖVE | `main.lua` + `conf.lua` | No first-party exporter | Migration notes |
| Electron | `package.json` `"electron"` | None | Unsupported |
| HTML5 | `index.html` + Phaser/Pixi/Three/… | WebView shell | Migration notes |
| Java | `.java` / `.jar` / `pom.xml` | Only if already Android | Review |
| .NET | CLR data directory | No IL-to-APK | Unsupported |
| Custom C/C++ | CMake / vcxproj / PE | NDK you write | Review |
| Android package | Manifest + DEX / `lib/<abi>` | Already packaged | Structure check |
| Unknown | Below evidence threshold | Manual | Inventory |

### Official references

- Unity CLI: https://docs.unity3d.com/Manual/build-command-line.html  
- Unity Android: https://docs.unity3d.com/Manual/android.html  
- Unity IL2CPP: https://docs.unity3d.com/Manual/IL2CPP.html  
- Unreal Android: https://dev.epicgames.com/documentation/en-us/unreal-engine/android-development-requirements-for-unreal-engine  
- Godot Android: https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html  
- Ren'Py Android: https://www.renpy.org/doc/html/android.html  
- Defold: https://defold.com/manuals/android/  
- libGDX: https://libgdx.com/wiki/app/android  
- PE format: https://learn.microsoft.com/en-us/windows/win32/debug/pe-format  
- Android ABIs: https://developer.android.com/ndk/guides/abis  
