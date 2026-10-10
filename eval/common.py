"""Shared helpers for the AgroLLaMA evaluation harness.

Loads eval/config.yaml, resolves paths, computes the config SHA256 that is
stamped into every results artefact, and provides small IO utilities.

Everything here is additive; the core MCP tools are never modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required: pip install pyyaml") from exc

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
CONFIG_PATH = EVAL_DIR / "config.yaml"


def _read_config_text(path: Path = CONFIG_PATH) -> str:
    return path.read_text(encoding="utf-8")


def config_sha256(path: Path = CONFIG_PATH) -> str:
    """SHA256 of the raw config file — the provenance anchor for all results."""
    return hashlib.sha256(_read_config_text(path).encode("utf-8")).hexdigest()


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    cfg = yaml.safe_load(_read_config_text(path))
    if not isinstance(cfg, dict):
        raise ValueError(f"config did not parse to a mapping: {path}")
    return cfg


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (REPO_ROOT / p)


def config_dirs(cfg: dict[str, Any]) -> dict[str, Path]:
    paths = cfg["paths"]
    out = {k: resolve(v) for k, v in paths.items() if k.endswith("_dir") or k.endswith("_root")}
    for key in ("scenarios_path", "stress_path", "llm_subset_path"):
        out[key] = resolve(paths[key])
    return out


def ensure_dirs(cfg: dict[str, Any]) -> dict[str, Path]:
    dirs = config_dirs(cfg)
    for key, p in dirs.items():
        if key.endswith("_dir") or key.endswith("_root"):
            p.mkdir(parents=True, exist_ok=True)
    return dirs


@dataclass
class ResultMeta:
    run_id: str
    protocol_version: str
    config_sha256: str
    git_commit: str
    model_name_used: str
    created_utc: str

    @classmethod
    def build(cls, cfg: dict[str, Any], model_name_used: str = "n/a") -> "ResultMeta":
        return cls(
            run_id=str(cfg["meta"]["run_id"]),
            protocol_version=str(cfg["meta"]["protocol_version"]),
            config_sha256=config_sha256(),
            git_commit=git_commit(),
            model_name_used=model_name_used,
            created_utc=datetime.now(timezone.utc).isoformat(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "protocol_version": self.protocol_version,
            "config_sha256": self.config_sha256,
            "git_commit": self.git_commit,
            "model_name_used": self.model_name_used,
            "created_utc": self.created_utc,
        }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def rng_seed(cfg: dict[str, Any], name: str) -> int:
    return int(cfg["seeds"][name])


if __name__ == "__main__":
    cfg = load_config()
    print("config_sha256:", config_sha256())
    print("git_commit:", git_commit())
    print("dirs:")
    for k, v in config_dirs(cfg).items():
        print(f"  {k}: {v}")
    print("python:", sys.version.split()[0])
