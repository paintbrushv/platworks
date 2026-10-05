"""Prepare a minimal offline OCI context from reviewed candidate wheels and lock."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from clean_install import VERSIONS

ROOT = Path(__file__).resolve().parents[1]


def prepare(wheelhouse, output):
    if output.exists():
        raise ValueError("Choose a new output directory; existing evidence is preserved")
    output.mkdir(parents=True)
    wheels = output / "wheels"
    wheels.mkdir()
    lock = ROOT / "requirements-analysis.lock"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--require-hashes",
            "--only-binary=:all:",
            "-r",
            str(lock),
            "--dest",
            str(wheels),
        ],
        check=True,
    )
    for name, version in VERSIONS.items():
        matches = list(wheelhouse.glob(f"{name}-{version}-*.whl"))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {name} candidate wheel")
        shutil.copyfile(matches[0], wheels / matches[0].name)
    shutil.copyfile(lock, output / lock.name)
    shutil.copyfile(ROOT / "deploy/Dockerfile", output / "Dockerfile")
    manifest = {
        "contract_version": "plat.container-build/1",
        "platform": "linux/amd64",
        "sources": json.loads((ROOT / "release-sources.json").read_text()),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "wheels": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(wheels.iterdir())
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.wheelhouse.resolve(), args.output.resolve()), indent=2))
