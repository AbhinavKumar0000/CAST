"""Probe Gemini access via the SDKs actually installed in this repo.

Tries ListModels then a tiny GenerateContent across candidate models, reporting
which (SDK, model) pairs the key can actually use. Never prints the key.
"""

import os

from dotenv import load_dotenv

load_dotenv()

KEY = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")

CANDIDATES = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]


def try_old_sdk():
    print("=== google-generativeai (old SDK) ===")
    try:
        import google.generativeai as genai
    except Exception as exc:  # noqa: BLE001
        print("  import failed:", exc)
        return
    genai.configure(api_key=KEY)
    try:
        models = list(genai.list_models())
        print(f"  list_models OK: {len(models)} models")
        for m in models:
            print("   -", m.name, m.supported_generation_methods)
    except Exception as exc:  # noqa: BLE001
        print("  list_models failed:", type(exc).__name__, str(exc)[:300])
    for name in CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name=name)
            resp = model.generate_content("Reply with the single word: OK")
            print(f"  generate[{name}] -> {resp.text[:40]!r}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  generate[{name}] failed:", type(exc).__name__, str(exc)[:200])


def try_new_sdk():
    print("=== google-genai (new SDK) ===")
    try:
        from google import genai
    except Exception as exc:  # noqa: BLE001
        print("  import failed:", exc)
        return
    try:
        client = genai.Client(api_key=KEY)
    except Exception as exc:  # noqa: BLE001
        print("  client init failed:", exc)
        return
    try:
        count = 0
        for m in client.models.list():
            count += 1
            print("   -", m.name)
            if count >= 60:
                break
        print(f"  list OK ({count} shown)")
    except Exception as exc:  # noqa: BLE001
        print("  list failed:", type(exc).__name__, str(exc)[:300])
    for name in CANDIDATES:
        try:
            resp = client.models.generate_content(model=name, contents="Reply with the single word: OK")
            print(f"  generate[{name}] -> {resp.text[:40]!r}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  generate[{name}] failed:", type(exc).__name__, str(exc)[:200])


if __name__ == "__main__":
    try_old_sdk()
    try_new_sdk()
