"""Background job launcher for Windows - runs jobs in background with logging and PID tracking."""

import json
import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, config_dirs


class BackgroundJobManager:
    """Manage long-running background jobs with logging and PID tracking."""
    
    def __init__(self):
        self.cfg = load_config()
        self.dirs = config_dirs(self.cfg)
        self.runs_dir = self.dirs['runs_dir']
        self.logs_dir = self.runs_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.pids_dir = self.runs_dir / "pids"
        self.pids_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.runs_dir / "jobs.json"
    
    def _load_jobs(self) -> dict:
        if self.jobs_file.exists():
            with open(self.jobs_file) as f:
                return json.load(f)
        return {}
    
    def _save_jobs(self, jobs: dict):
        with open(self.jobs_file, 'w') as f:
            json.dump(jobs, f, indent=2)
    
    def start_job(self, job_name: str, command: list[str], env: dict = None) -> int:
        """Start a background job and return its PID."""
        jobs = self._load_jobs()
        
        # Check if already running
        if job_name in jobs:
            existing_pid = jobs[job_name].get('pid')
            if existing_pid and self._is_process_alive(existing_pid):
                print(f"Job '{job_name}' already running (PID: {existing_pid})")
                return existing_pid
        
        # Prepare environment
        job_env = os.environ.copy()
        if env:
            job_env.update(env)
        
        # Create log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.logs_dir / f"{job_name}_{timestamp}.log"
        pid_file = self.pids_dir / f"{job_name}.pid"
        
        # Start process
        with open(log_file, 'w') as log_fp:
            proc = subprocess.Popen(
                command,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                env=job_env,
                cwd=os.getcwd(),
            )
        
        # Save PID
        with open(pid_file, 'w') as f:
            f.write(str(proc.pid))
        
        # Update jobs registry
        jobs[job_name] = {
            'pid': proc.pid,
            'command': ' '.join(command),
            'log_file': str(log_file),
            'pid_file': str(pid_file),
            'started_at': datetime.now(timezone.utc).isoformat(),
            'status': 'running'
        }
        self._save_jobs(jobs)
        
        print(f"Started job '{job_name}' (PID: {proc.pid})")
        print(f"  Log: {log_file}")
        print(f"  PID file: {pid_file}")
        return proc.pid
    
    def stop_job(self, job_name: str) -> bool:
        """Stop a background job gracefully."""
        jobs = self._load_jobs()
        
        if job_name not in jobs:
            print(f"Job '{job_name}' not found in registry")
            return False
        
        pid = jobs[job_name].get('pid')
        if not pid:
            print(f"No PID for job '{job_name}'")
            return False
        
        if not self._is_process_alive(pid):
            print(f"Process {pid} not alive")
            jobs[job_name]['status'] = 'stopped'
            self._save_jobs(jobs)
            return True
        
        # Try graceful termination
        try:
            if os.name == 'nt':
                # Windows: use taskkill
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
            else:
                # Unix: SIGTERM then SIGKILL
                os.kill(pid, 15)  # SIGTERM
                time.sleep(2)
                if self._is_process_alive(pid):
                    os.kill(pid, 9)  # SIGKILL
        except Exception as e:
            print(f"Error stopping process: {e}")
            return False
        
        jobs[job_name]['status'] = 'stopped'
        jobs[job_name]['stopped_at'] = datetime.now(timezone.utc).isoformat()
        self._save_jobs(jobs)
        
        # Clean up PID file
        pid_file = self.pids_dir / f"{job_name}.pid"
        if pid_file.exists():
            pid_file.unlink()
        
        print(f"Stopped job '{job_name}' (PID: {pid})")
        return True
    
    def get_status(self, job_name: str = None) -> dict:
        """Get status of one or all jobs."""
        jobs = self._load_jobs()
        
        if job_name:
            if job_name not in jobs:
                return {'error': f"Job '{job_name}' not found"}
            job = jobs[job_name]
            job['alive'] = self._is_process_alive(job.get('pid', 0))
            return job
        
        # Return all jobs with alive status
        result = {}
        for name, job in jobs.items():
            job_copy = job.copy()
            job_copy['alive'] = self._is_process_alive(job.get('pid', 0))
            result[name] = job_copy
        return result
    
    def tail_log(self, job_name: str, lines: int = 50) -> str:
        """Get last N lines of job log."""
        jobs = self._load_jobs()
        
        if job_name not in jobs:
            return f"Job '{job_name}' not found"
        
        log_file = Path(jobs[job_name]['log_file'])
        if not log_file.exists():
            return f"Log file not found: {log_file}"
        
        with open(log_file) as f:
            all_lines = f.readlines()
        
        return ''.join(all_lines[-lines:])
    
    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process is still running."""
        try:
            if os.name == 'nt':
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True, text=True
                )
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)  # Signal 0 just checks existence
                return True
        except:
            return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Background job manager for Windows")
    subparsers = parser.add_subparsers(dest='action', help='Action to perform')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start a background job')
    start_parser.add_argument('--name', '-n', required=True, help='Job name')
    start_parser.add_argument('--command', '-c', nargs=argparse.REMAINDER, required=True, help='Command to run')
    
    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop a background job')
    stop_parser.add_argument('--name', '-n', required=True, help='Job name')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show job status')
    status_parser.add_argument('--name', '-n', help='Job name (optional)')
    status_parser.add_argument('--watch', '-w', action='store_true', help='Watch mode')
    status_parser.add_argument('--interval', type=int, default=5, help='Watch interval in seconds')
    
    # Logs command
    logs_parser = subparsers.add_parser('logs', help='Show job logs')
    logs_parser.add_argument('--name', '-n', required=True, help='Job name')
    logs_parser.add_argument('--lines', '-l', type=int, default=50, help='Number of log lines')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all jobs')
    
    args = parser.parse_args()
    
    if not args.action:
        parser.print_help()
        sys.exit(1)
    
    manager = BackgroundJobManager()
    
    if args.action == 'start':
        if not args.name or not args.command:
            print("Error: --name and --command required for start")
            sys.exit(1)
        manager.start_job(args.name, args.command)
    
    elif args.action == 'stop':
        if not args.name:
            print("Error: --name required for stop")
            sys.exit(1)
        manager.stop_job(args.name)
    
    elif args.action == 'status':
        if args.watch:
            try:
                while True:
                    os.system('cls' if os.name == 'nt' else 'clear')
                    status = manager.get_status()
                    print(f"=== Job Status ({datetime.now().strftime('%H:%M:%S')}) ===")
                    print(f"{'Job Name':<30} {'PID':<8} {'Status':<10} {'Alive':<6} {'Started'}")
                    print("-" * 80)
                    for name, job in status.items():
                        alive = "YES" if job.get('alive', False) else "NO"
                        started = job.get('started_at', '')[:19].replace('T', ' ')
                        print(f"{name:<30} {job.get('pid', 'N/A'):<8} {job.get('status', 'unknown'):<10} {alive:<6} {started}")
                    print(f"\nPress Ctrl+C to exit watch mode")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nStopped watching")
        else:
            status = manager.get_status(args.name)
            print(json.dumps(status, indent=2))
    
    elif args.action == 'logs':
        if not args.name:
            print("Error: --name required for logs")
            sys.exit(1)
        print(manager.tail_log(args.name, args.lines))
    
    elif args.action == 'list':
        status = manager.get_status()
        if not status:
            print("No jobs registered")
        else:
            print(f"{'Job Name':<30} {'PID':<8} {'Status':<10} {'Alive':<6} {'Started'}")
            print("-" * 80)
            for name, job in status.items():
                alive = "YES" if job.get('alive', False) else "NO"
                started = job.get('started_at', '')[:19].replace('T', ' ')
                print(f"{name:<30} {job.get('pid', 'N/A'):<8} {job.get('status', 'unknown'):<10} {alive:<6} {started}")


if __name__ == "__main__":
    main()