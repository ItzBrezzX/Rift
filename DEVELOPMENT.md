# Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --reload --port 8000
```

## Adding an engine

1. Add a branch in `app/detection/analyzer.py` that appends `Evidence` with a layer and weight.  
2. Add an `Adapter` in `app/adapters/registry.py`.  
3. Add a finding when the strategy is easy to over-claim.  
4. Add synthetic pytest fixtures — never commercial game content.  
5. Keep `native_apk_buildable_from_upload_alone` false.

## Job rules

- Progress values follow the stage table in `app/jobs/runner.py`.  
- `completed` is only legal after validation.  
- An artifact ending in `.apk` / `.aab` without a real toolchain write is a bug. v0.2 has no such writer.
