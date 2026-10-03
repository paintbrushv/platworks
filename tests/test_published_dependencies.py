"""Release ordering must protect the ordinary registry-only analysis install."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "published_gate",
    Path(__file__).resolve().parents[1] / "scripts/check_published_dependencies.py",
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def published(name, version):
    platforms = (
        ("manylinux_2_28_x86_64", "macosx_10_12_x86_64", "macosx_11_0_arm64", "win_amd64")
        if name == "plat-operations"
        else ("any",)
    )
    return {
        "info": {"name": name, "version": version},
        "urls": [
            {
                "filename": f"{name.replace('-', '_')}-{version}-py3-none-{platform}.whl",
                "requires_python": ">=3.11",
                "packagetype": "bdist_wheel",
                "yanked": False,
            }
            for platform in platforms
        ],
    }


def test_missing_dependency_versions_block_umbrella_publication():
    result = gate.verify(lambda name, version: None)
    assert result["status"] == "blocked"
    assert len(result["issues"]) == 4
    assert "Publish plat-operations==0.1.1 first" in result["issues"]


def test_all_supported_published_wheels_allow_publication():
    result = gate.verify(published)
    assert result["status"] == "ready"
    assert len(result["published"]) == 4


def test_missing_windows_native_wheel_blocks_publication():
    def missing(name, version):
        release = published(name, version)
        release["urls"] = [f for f in release["urls"] if "win_amd64" not in f["filename"]]
        return release

    result = gate.verify(missing)
    assert result["status"] == "blocked"
    assert len(result["issues"]) == 2
    assert all("windows-x64" in issue for issue in result["issues"])


def test_yanked_native_wheels_do_not_satisfy_the_release_gate():
    def yanked(name, version):
        release = published(name, version)
        if name == "plat-operations":
            for wheel in release["urls"]:
                wheel["yanked"] = True
        return release

    result = gate.verify(yanked)
    assert result["status"] == "blocked"
    assert len(result["issues"]) == 8


def test_release_python_floor_must_cover_both_supported_versions():
    def newer_python(name, version):
        release = published(name, version)
        if name == "plat-operations":
            release["info"]["requires_python"] = ">=3.12"
        return release

    result = gate.verify(newer_python)
    assert result["status"] == "blocked"
    assert len(result["issues"]) == 4
    assert all("py3.11" in issue for issue in result["issues"])
