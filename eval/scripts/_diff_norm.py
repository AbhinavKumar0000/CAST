import json

o = json.load(open("eval/results/_presnap_adhoc/normalization_fix_before_after.json"))
n = json.load(open("eval/results/normalization_fix_before_after.json"))
om = {(r["model"], r["condition"]): r for r in o}
print(f"{'model':9s}{'cond':5s}{'n':>5s}   acc_b old->new    acc_a old->new    jac_b old->new    sv_b old->new")
for r in n:
    a = om[(r["model"], r["condition"])]
    print(f"{r['model']:9s}{r['condition']:5s}{r['n']:5d}   "
          f"{a['acc_before']:.3f}->{r['acc_before']:.3f}   {a['acc_after']:.3f}->{r['acc_after']:.3f}   "
          f"{a['jac_before']:.3f}->{r['jac_before']:.3f}   {a['sv_before']:.3f}->{r['sv_before']:.3f}")