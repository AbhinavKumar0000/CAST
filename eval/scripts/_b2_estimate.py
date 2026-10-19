import json

with open("eval/runs/eval_nemotron-3-ultra/results.json", encoding="utf-8") as f:
    r = json.load(f)

conds = ["C1a", "C2a", "C2b"]
tot_http = tot_lat = tot_ti = tot_to = 0
for c in conds:
    rs = [x for x in r if x["condition"] == c]
    http = sum(len(x.get("tool_log") or []) + 1 for x in rs)
    lat = sum(x.get("latency_s", 0) for x in rs)
    ti = sum(x.get("tokens_in", 0) for x in rs)
    to = sum(x.get("tokens_out", 0) for x in rs)
    tot_http += http
    tot_lat += lat
    tot_ti += ti
    tot_to += to
    print(f"{c}: n={len(rs)} http={http} ({http/len(rs):.2f}/scen) lat_sum={lat:.0f}s tokens_in={ti} tokens_out={to}")

print(f"TOTAL per 150 scenarios: http={tot_http} lat_sum={tot_lat:.0f}s tokens_in={tot_ti} tokens_out={tot_to}")

scale = 350 / 150
print(f"B2 (350) est: http={tot_http*scale:.0f} tokens_in={tot_ti*scale:.0f} tokens_out={tot_to*scale:.0f}")
for w in (4, 6, 8):
    print(f"  wall @workers={w}: {tot_lat*scale/w/3600:.1f} h")
print("B1 actual wall: 142.9 min with 4 workers")
print(f"days needed at 4000 HTTP/day: {tot_http*scale/4000:.2f}")
