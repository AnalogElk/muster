# Per-script responder overrides

Drop a `<script-stem>.py` here to give one script custom stubbed responses when
the default policy in `harness/responder.py` can't carry it far enough (e.g. a
script gates on specific data existing before it proceeds).

The stem is the script filename without `.py` (e.g. `seed-D3` for
`provision/seed-full/seed-D3.py`). The module must expose `OVERRIDES`:

```python
# overrides/seed-D3.py
OVERRIDES = [
    # (matcher(method, path, body) -> bool, (status, json_obj))
    (lambda m, p, b: m == "GET" and p.startswith("/fields/os_tasks/workspace"),
     (200, {"data": {"field": "workspace"}})),   # pretend F1 already landed
]
```

Overrides are consulted before the default policy, in order; the first match
wins. Keep them minimal and deterministic. After adding one, regenerate that
script's golden (`.venv/bin/python gen_goldens.py seed-D3`) and re-run the suite.
