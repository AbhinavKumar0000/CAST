import json

o = json.load(open("eval/results/_presnap_adhoc/llm_aggregates.json"))
n = json.load(open("eval/results/llm_aggregates.json"))
print("keys equal:", set(o) == set(n))
mt = ["jaccard_mean", "acc5_mean", "mrr_mean", "prec5_mean", "hallucination_mean", "season_mean"]
print(f"{'cell':16s} " + "  ".join(f"{m.replace('_mean',''):>12s}" for m in mt))
for k in sorted(o):
    if k in ("llama|C1", "llama|C2", "llama|C0", "nemotron|C0", "nemotron|C1", "nemotron|C2",
             "llama|C0b", "nemotron|C0b", "glm|C0", "glm|C1", "glm|C2", "glm|C0b"):
        row = []
        for m in mt:
            a, b = o[k].get(m), n[k].get(m)
            if a is None or b is None:
                row.append("   n/a")
            else:
                d = b - a
                row.append(f"{a:.3f}->{b:.3f}" + ("*" if abs(d) > 1e-9 else " "))
        print(f"{k:16s} " + "  ".join(f"{c:>12s}" for c in row))