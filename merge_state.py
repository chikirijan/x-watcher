#!/usr/bin/env python3
"""
Union the local seen.json with the copy already on the remote branch, so no
ids are ever lost when a run overlaps or a push is retried.

Called by the workflow's "Save state" step.
"""
import json
import pathlib
import sys

CAP = 800


def load(path):
    try:
        data = json.loads(pathlib.Path(path).read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def main():
    remote = load(sys.argv[1] if len(sys.argv) > 1 else "/tmp/remote.json")
    local = load("seen.json")
    merged = list(dict.fromkeys(remote + local))[-CAP:]
    pathlib.Path("seen.json").write_text(json.dumps(merged, indent=0))
    print(f"state: {len(remote)} remote + {len(local)} local -> {len(merged)} kept")


if __name__ == "__main__":
    main()
