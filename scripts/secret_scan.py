import re
import sys
from pathlib import Path

ROOT = Path('.')
patterns = {
    'nvapi-': r'nvapi-[a-zA-Z0-9_-]{20,}',
    'api_key': r'api[_-]?key\s*[=:]\s*[\'"][a-zA-Z0-9_-]{20,}',
    'password': r'password\s*[=:]\s*[\'"][^\'"]{8,}',
    'secret': r'(secret|token|auth)[_-]?(key|token)\s*[=:]\s*[\'"][^\'"]{16,}',
}

# Only scan working tree, exclude .git, __pycache__, eval/runs, eval/cache
exclude_dirs = {'.git', '__pycache__', 'eval/runs', 'eval/cache', '.pytest_cache', 'htmlcov', 'archive'}

found = False
for name, pattern in patterns.items():
    for f in ROOT.rglob('*'):
        if not f.is_file():
            continue
        # Check if file is in excluded directory
        if any(exc in f.parts for exc in exclude_dirs):
            continue
        if f.suffix not in ('.py', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.env'):
            continue
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            if re.search(pattern, content):
                print(f'FOUND {name} in {f}')
                found = True
        except Exception:
            pass

if not found:
    print('SECRET SCAN: CLEAN')
else:
    print('SECRET SCAN: ISSUES FOUND')
    sys.exit(1)