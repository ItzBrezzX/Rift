# Architecture

## Languages

| Language | Role |
|----------|------|
| **Python 3.10+** | Worker: ZIP IO, detection, PE parsing, jobs, FastAPI |
| **Shell / Docker** | Deployment only |
| **Kotlin / Gradle** | Not generated — a template APK would look like a finished port |

C/C++ is intentionally absent. PE work is a bounded in-process parser.

## Pipeline

```
queued → analyzing → preparing → building → validating → completed
                                    ↘ failed / cancelled
```

`android_package` enters `building`, probes the toolchain, and **fails closed**.  
v0.2 never reaches `completed` with an APK artifact.

## Detection layers

1. **Signature** — DEX, core scripts, JAR, magic bytes  
2. **Directory structure** — `Assets/`, `.uproject`, `project.godot`  
3. **Metadata** — editor version, EngineAssociation, features  
4. **Binary prefix** — MZ/PE machine, imports, CLR, version strings  
5. **Dependencies** — Gradle coordinates, package manifests  

## Adapters

`app/adapters/registry.py` is the registry.  
`build_android` returns `executed: false` and `missing_toolchain` or `execution_disabled`.  
Adding an engine means a detector branch plus an adapter whose notes say what is not implemented.

## Security boundary

- ZIP names normalized; `..`, absolute paths, NUL, symlinks, encryption rejected  
- Size and compression-ratio ceilings  
- PE parse never calls `exec` on the image  
- Build commands are fixed strings — not taken from ZIP metadata  
