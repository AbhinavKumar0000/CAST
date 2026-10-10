import json
import urllib.request

d = json.load(urllib.request.urlopen("https://opencode.ai/config.json", timeout=30))
defs = d.get("$defs") or d.get("definitions") or {}
print("top keys:", list(d.keys()))
for k, v in defs.items():
    if "agent" in k.lower():
        print("=== DEF", k)
        print(json.dumps(v, indent=1)[:3000])
