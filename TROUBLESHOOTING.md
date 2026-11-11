# Troubleshooting

| Symptom | Meaning |
|---------|---------|
| Unity + `compatibility_layer` | You uploaded a player, not the project. Need `ProjectSettings/ProjectVersion.txt`. |
| Modest confidence | Intentional. One weak signal is not enough. |
| `missing_toolchain` | Env vars for editor/SDK not set or paths missing. Correct failure. No hidden APK. |
| Godot export would fail even with Godot installed | Need export preset + matching templates. |
| `Unsafe ZIP path` | Archive has `..`, absolute path, symlink, or encryption. Repack. |
| HTTP 413 | Over `PORT_ENGINE_MAX_UPLOAD_BYTES`. |
| Game “works” in Winlator | Compatibility test, not a native port. |

```bash
pytest -q
```

If `TestClient` fails to import, install `requirements-dev.txt` (`httpx`).
