import json

from click.testing import CliRunner

from platworks.cli import main
from platworks.doctor import diagnose


def test_real_analysis_installation_and_cent_contract():
    result = diagnose(analysis=True)
    assert result["status"] == "ready", result
    producer = next(c for c in result["checks"] if c["name"] == "operating_producer")
    assert producer["contract"] == "plat.ops/1"
    assert len(producer["binary_sha256"]) == 64


def test_missing_producer_refuses_without_exposing_private_path(monkeypatch):
    private = "/private/deal-name/no-such-producer"
    monkeypatch.setenv("PLAT_BOXSCORE_EXACT_BIN", private)
    response = CliRunner().invoke(main, ["doctor", "--analysis", "--json"])
    assert response.exit_code == 2
    assert private not in response.output
    report = json.loads(response.output)
    assert report["status"] == "incomplete"
    assert any(
        c["name"] == "operating_producer" and c["status"] == "failed" for c in report["checks"]
    )


def test_catalog_does_not_require_optional_producer(monkeypatch):
    monkeypatch.setenv("PLAT_BOXSCORE_EXACT_BIN", "/missing/producer")
    report = diagnose()
    assert report["status"] == "ready"
    assert all(c["name"] != "operating_producer" for c in report["checks"])


def test_dependency_mismatch_is_reported(monkeypatch):
    from platworks import doctor

    original = doctor.metadata.version
    monkeypatch.setattr(
        doctor.metadata, "version", lambda name: "1.0.0" if name == "mcp" else original(name)
    )
    report = diagnose()
    assert report["status"] == "incomplete"
    check = next(c for c in report["checks"] if c["name"] == "dependencies")
    assert check["status"] == "failed"
    assert "mcp: incompatible version" in check["problems"]
