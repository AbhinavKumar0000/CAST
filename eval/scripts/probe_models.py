"""Probe which Gemini models the configured API key can use.

Reads GEMINI_API_KEY from the environment (or .env). Never prints the key.
Calls the REST ListModels endpoint. Free of charge.
"""

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

KEY = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
if not KEY:
    raise SystemExit("GEMINI_API_KEY not set")

print(f"key length={len(KEY)} prefix={KEY[:4]} has_whitespace={any(c.isspace() for c in KEY)}")

URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
    "https://generativelanguage.googleapis.com/v1/models?pageSize=200",
]

for base in URLS:
    req = urllib.request.Request(base, headers={"x-goog-api-key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"{base} -> HTTP {exc.code}: {exc.read()[:200]!r}")
        continue
    except Exception as exc:  # noqa: BLE001
        print(f"{base} -> ERR {type(exc).__name__}: {str(exc)[:200]}")
        continue

    models = data.get("models", [])
    names = sorted(m["name"].split("/")[-1] for m in models)
    print(f"{base} -> OK, {len(names)} models:")
    for n in names:
        print("  ", n)
    break
