"""Verify candidate wheels with hashed dependencies in empty environments.

The third-party locks deliberately exclude the local candidate distributions.
Each candidate wheel is installed by its exact path; its SHA-256 is recorded.
No editable installs or source directories participate in the probe.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {
    "platworks": "0.1.4",
    "plat_multifamily_underwriting": "0.1.2",
    "plat_costmodel": "0.1.1",
    "plat_harness": "0.1.1",
    "plat_operations": "0.1.1",
}


def verify(wheelhouse, profile):
    names = VERSIONS if profile == "analysis" else {"platworks": VERSIONS["platworks"]}
    wheels = []
    for name, version in names.items():
        matches = list(wheelhouse.glob(f"{name}-{version}-*.whl"))
        if len(matches) != 1:
            raise ValueError(f"Expected one {name} {version} wheel; found {len(matches)}")
        wheels.append(matches[0])
    lock = ROOT / f"requirements-{profile}.lock"
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PYTHON", "PLAT_", "UNDERWRITING_", "COSTMODEL_"))
    }
    with tempfile.TemporaryDirectory(prefix="plat-clean-install-") as temporary:
        work = Path(temporary)
        env_dir = work / "environment"
        venv.create(env_dir, with_pip=True, symlinks=os.name != "nt")
        scripts = env_dir / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")

        def run(*args):
            result = subprocess.run(
                [str(python), "-I", *map(str, args)],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode:
                # This build script handles public synthetic inputs only. Preserve
                # dependency errors for CI debugging; product doctor stays private.
                sys.stderr.write(result.stdout + result.stderr)
                raise RuntimeError(f"Installation check failed ({result.returncode})")
            return result.stdout

        # Verify the documented ordinary extra can resolve without compilers,
        # then install the reviewed hashed set for runtime acceptance.
        project = "platworks[analysis]" if profile == "analysis" else "platworks"
        run(
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--ignore-installed",
            "--only-binary=:all:",
            "--find-links",
            wheelhouse,
            f"{project}=={VERSIONS['platworks']}",
        )
        run("-m", "pip", "install", "--require-hashes", "--only-binary=:all:", "-r", lock)
        run("-m", "pip", "install", "--no-deps", *wheels)
        run("-m", "pip", "check")
        # Console entry point must exist as well as the module entry point.
        command = scripts / ("platworks.exe" if os.name == "nt" else "platworks")
        subprocess.run(
            [str(command), "--help"],
            cwd=work,
            env=environment,
            capture_output=True,
            check=True,
            timeout=30,
        )
        if profile == "analysis":
            probe = json.loads(run("-m", "platworks.verify_install"))
            if probe["status"] != "passed" or probe["source_overrides_present"]:
                raise RuntimeError("Analysis probe did not pass without overrides")
        else:
            code = (
                "import anyio, json; from platworks.doctor import diagnose; "
                "from platworks.verify_install import mcp_call; "
                "d=diagnose(); assert d['status'] == 'ready', d; "
                "anyio.run(mcp_call, 'platworks.mcp_server', "
                "[('get_component', {'name':'plat-harness'})]); "
                "print(json.dumps({'status':'passed','doctor':d,'catalog_mcp':True}))"
            )
            probe = json.loads(run("-c", code))
        installed = json.loads(run("-m", "pip", "list", "--format=json"))
    return {
        "status": "passed",
        "ordinary_installer_resolves_with_wheels": True,
        "profile": profile,
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine().lower()}",
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "wheels": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in wheels},
        "sources": json.loads((ROOT / "release-sources.json").read_text()),
        "installed": installed,
        "probe": probe,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--profile", choices=["catalog", "analysis"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.wheelhouse.resolve(), args.profile)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "profile", "python", "platform")}))
