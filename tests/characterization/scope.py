"""Shared helpers for the characterization suite: scope list, golden paths,
and running a script through the harness as a subprocess.
"""
import pathlib
import subprocess

CCHAR = pathlib.Path(__file__).resolve().parent  # tests/characterization
REPO_ROOT = CCHAR.parent.parent  # worktree root
SCOPE_FILE = CCHAR / "SCOPE.txt"
GOLDENS = CCHAR / "goldens"
VENV_PY = CCHAR / ".venv" / "bin" / "python"


def read_scope():
    """Return in-scope script paths (relative to REPO_ROOT), comments skipped."""
    out = []
    for line in SCOPE_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def slug(rel_path):
    """Filesystem-safe unique key for a script path, e.g.
    provision/seed-full/seed-F1.py -> provision__seed-full__seed-F1
    """
    stem = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    return stem.replace("/", "__")


def golden_path(rel_path):
    return GOLDENS / (slug(rel_path) + ".jsonl")


def run_harness(rel_path):
    """Run one script under the harness. Returns (stdout, stderr, returncode).

    PYTHONHASHSEED is pinned so any set-iteration ordering in a script is stable
    across processes (it must be set before the interpreter starts).
    """
    import os

    abs_path = REPO_ROOT / rel_path
    env = dict(os.environ, PYTHONHASHSEED="0")
    proc = subprocess.run(
        [str(VENV_PY), "-m", "harness.run_script", str(abs_path)],
        cwd=str(CCHAR),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.stdout, proc.stderr, proc.returncode
