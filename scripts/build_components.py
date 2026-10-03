"""Build pure Python candidates from immutable public source pins."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    sources = json.loads((ROOT / "release-sources.json").read_text())
    wheelhouse = ROOT / "wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="plat-source-build-") as temporary:
        for name, entry in sources.items():
            if name == "plat-operations":
                continue
            checkout = Path(temporary) / name
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-checkout",
                    "--filter=blob:none",
                    f"https://github.com/paintbrushv/{name}.git",
                    str(checkout),
                ],
                check=True,
            )
            subprocess.run(["git", "checkout", "--detach", entry["sha"]], cwd=checkout, check=True)
            subprocess.run([sys.executable, "scripts/release_gate.py"], cwd=checkout, check=True)
            subprocess.run(
                [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheelhouse)],
                cwd=checkout,
                check=True,
            )
    subprocess.run([sys.executable, "-m", "build"], cwd=ROOT, check=True)
    for wheel in (ROOT / "dist").glob("*.whl"):
        (wheelhouse / wheel.name).write_bytes(wheel.read_bytes())


if __name__ == "__main__":
    build()
