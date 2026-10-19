import json
import os
import time
from collections import Counter

results_file = 'eval/runs/full_nemotron-3-ultra_20261011_074835/results.json'

print("=== Nemotron-3-Ultra Retry Progress Monitor ===")
print("Watching: eval/runs/full_nemotron-3-ultra_20261011_074835/results.json")
print("Press Ctrl+C to stop\n")

last_failed = -1
start_time = time.time()

while True:
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        with open(results_file) as f:
            data = json.load(f)
        
        failed = [r for r in data if r.get('error')]
        total = len(data)
        failed_count = len(failed)
        success_count = total - failed_count
        
        elapsed = time.time() - start_time
        rate = success_count / elapsed * 60 if elapsed > 0 else 0
        
        print(f"=== Nemotron-3-Ultra Retry Progress ===")
        print(f"Time: {time.strftime('%H:%M:%S')} | Elapsed: {elapsed/60:.1f} min")
        print(f"Total: {total} | Success: {success_count} | Failed: {failed_count} ({failed_count/total*100:.1f}%)")
        print(f"Success rate: {success_count/total*100:.1f}% | Rate: {rate:.1f} req/min")
        
        # By condition
        from collections import Counter
        cond_counts = Counter(r['condition'] for r in failed)
        print(f"\nFailed by condition ({len(failed)} total):")
        for cond, count in cond_counts.most_common():
            print(f"  {cond}: {count}")
        
        # Recent failures
        recent_failed = [r for r in data[-20:] if r.get('error')]
        if recent_failed:
            print(f"\nRecent failures (last 20 calls):")
            for r in data[-20:]:
                status = "FAIL" if r.get('error') else "OK"
                print(f"  {r['scenario_id']} {r['condition']} r{r.get('repeat',0)}: {status} ({r['latency_s']:.1f}s)")
        
        # Progress bar
        pct = success_count / total * 100
        bar = "█" * int(pct/5) + "░" * (20 - int(pct/5))
        print(f"\nProgress: [{bar}] {success_count}/{total} ({pct:.1f}%)")
        
        # ETA
        if rate > 0:
            remaining = failed_count / rate
            print(f"ETA: {remaining:.1f} min")
        
        print(f"\nRefreshing in 15s... (Ctrl+C to stop)")
        time.sleep(15)
        
    except KeyboardInterrupt:
        print("\nStopped.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(15)