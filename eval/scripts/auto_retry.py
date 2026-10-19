"""Auto-restarting retry manager with continuous monitoring."""

import json
import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path

RESULTS_FILE = Path("eval/runs/full_nemotron-3-ultra_20261011_082444/results.json")

def check_progress():
    """Check current progress."""
    with open(RESULTS_FILE) as f:
        data = json.load(f)
    failed = [r for r in data if r.get("error")]
    success = 2000 - len(failed)
    return len(failed), success, 2000

def run_retry():
    """Run the retry script as a subprocess."""
    cmd = [sys.executable, "-u", "eval/scripts/retry_fast.py"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

def monitor():
    """Monitor and restart until all fixed."""
    last_failed = 166
    start_time = time.time()
    last_progress_time = time.time()
    
    while True:
        # Check current progress
        failed, success, total = check_progress()
        elapsed = time.time() - start_time
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Failed: {failed} | Success: {success}/2000 | Elapsed: {elapsed/60:.1f}min")
        
        if failed == 0:
            print("\n✅ ALL DONE! 2000/2000 successful!")
            break
        
        # Check if process is running
        procs = [p for p in psutil.process_iter(['pid', 'name', 'cmdline']) if 'python' in p.info['name'] and 'retry' in ' '.join(p.info['cmdline'] or [])]
        
        if not procs:
            print("⚠️ Process died, restarting...")
            proc = subprocess.Popen([sys.executable, "-u", "eval/scripts/retry_fast.py"], 
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                    text=True, bufsize=1)
            time.sleep(5)
        else:
            print(f"  Process running (PID: {procs[0].pid})")
        
        # Check for progress
        failed_now, _, _ = check_progress()
        if failed < last_failed:
            last_progress_time = time.time()
            last_failed = failed
            print(f"  ✅ Progress: {last_failed - failed} fixed!")
        
        # Check for stall (no progress in 5 minutes)
        if time.time() - last_progress_time > 300:
            print("⚠️ Stalled for 5 minutes, restarting...")
            for p in psutil.process_iter(['pid']):
                try:
                    p.kill()
                except:
                    pass
            time.sleep(2)
        
        if failed == 0:
            break
            
        time.sleep(30)  # Check every 30 seconds

if __name__ == "__main__":
    import json, os, time, subprocess, sys
    import psutil
    from datetime import datetime
    
    print("🚀 Starting auto-monitored retry manager")
    print("=" * 60)
    
    # Check initial state
    failed, success, _ = check_progress()
    print(f"Initial: {failed} failed, {success}/2000 success")
    
    if failed == 0:
        print("✅ Already complete!")
        sys.exit(0)
    
    monitor()