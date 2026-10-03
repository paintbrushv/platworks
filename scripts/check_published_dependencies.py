"""Block umbrella publication until its exact analysis wheels are on PyPI."""

import json
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def registry_release(name, version):
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=30
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def supported_targets():
    platforms = {
        "linux-x64": [f"manylinux_2_{minor}_x86_64" for minor in range(28, 4, -1)]
        + ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"],
        "macos-intel": list(mac_platforms((15, 0), "x86_64")),
        "macos-arm": list(mac_platforms((15, 0), "arm64")),
        "windows-x64": ["win_amd64"],
    }
    for name, tags in platforms.items():
        for minor in (11, 12):
            interpreter = f"cp3{minor}"
            supported = set(cpython_tags((3, minor), abis=[interpreter], platforms=tags))
            supported.update(compatible_tags((3, minor), interpreter=interpreter, platforms=tags))
            yield f"{name}-py3.{minor}", f"3.{minor}.0", supported


def verify(fetch=registry_release):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    issues, published = [], {}
    for text in project["optional-dependencies"]["analysis"]:
        requirement = Requirement(text)
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise ValueError("Analysis dependencies must use exact release versions")
        name, version = requirement.name, pins[0].version
        release = fetch(name, version)
        if release is None:
            issues.append(f"Publish {name}=={version} first")
            continue
        info = release["info"]
        if canonicalize_name(info["name"]) != canonicalize_name(name) or info["version"] != version:
            raise ValueError("Registry identity differs from the requested dependency")
        wheels = [
            f
            for f in release["urls"]
            if f["packagetype"] == "bdist_wheel" and not f.get("yanked", False)
        ]
        for target, python, tags in supported_targets():
            available = any(
                SpecifierSet(info.get("requires_python") or "").contains(python)
                and SpecifierSet(f.get("requires_python") or "").contains(python)
                and parse_wheel_filename(f["filename"])[3] & tags
                for f in wheels
            )
            if not available:
                issues.append(f"{name}=={version}: no non-yanked wheel for {target}")
        published[name] = version
    return {"status": "blocked" if issues else "ready", "published": published, "issues": issues}


if __name__ == "__main__":
    try:
        result = verify()
    except Exception as error:
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__}))
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2))
    sys.exit(2 if result["issues"] else 0)
