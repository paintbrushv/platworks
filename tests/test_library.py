"""Library contract, retrieval, deterministic search and alias boundary checks."""

import copy
import json
from importlib.resources import files

import pytest

from platworks import library
from platworks.library_tools import LocalSources, synthetic_example


def test_packaged_index_and_dated_original_references():
    corpus, index = library._load()
    assert len(corpus["references"]) == 15
    assert index == library.compile_index(corpus)
    assert corpus["license"] == "Apache-2.0"
    for ref in corpus["references"]:
        result = library.get_reference(ref["id"], ref["version"])
        assert result["reference_sha256"] == library.sha256(ref)
        assert ref["review"]["independent_domain_review"] == "pending"
        assert ref["review"]["checked_on"] == "2026-10-05"
        assert result["sources"] and all(s["url"].startswith("https://") for s in result["sources"])
    duplicate = copy.deepcopy(corpus)
    duplicate["references"].append(duplicate["references"][0])
    with pytest.raises(library.LibraryError):
        library.compile_index(duplicate)
    assert json.loads(files("platworks").joinpath("data/library/index.json").read_text()) == index


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("DSCR debt coverage", "mf.debt"),
        ("NOI net operating income", "mf.noi"),
        ("correction supersedes immutable", "mf.corrections"),
        ("variance actual budget missing zero", "mf.variance"),
        ("insurance deductible quote", "mf.insurance"),
        ("original thesis acquisition freeze", "mf.original-thesis"),
    ],
)
def test_search_task_ranking(query, first):
    result = library.search_library(query)
    assert result["results"][0]["id"] == first
    assert result["results"] == library.search_library(query.upper())["results"]
    assert result == library.search_library(query)
    assert result["count"] <= 5


def test_search_empty_and_typed_refusals():
    assert library.search_library("zzzzzznonsense")["count"] == 0
    for query, limit in [("", 5), ("x" * 501, 5), ("NOI", True), ("NOI", 11)]:
        with pytest.raises(library.LibraryError):
            library.search_library(query, limit)
    for ref, version, code in [
        ("mf.absent", None, "REFERENCE_NOT_FOUND"),
        ("../../secret", None, "INVALID_REFERENCE"),
        ("mf.noi", "0.0.0", "REFERENCE_VERSION_NOT_FOUND"),
    ]:
        with pytest.raises(library.LibraryError) as error:
            library.get_reference(ref, version)
        assert error.value.code == code
    result = library.get_reference("mf.noi")
    result["reference"]["body"] = "tampered"
    assert library.get_reference("mf.noi")["reference"]["body"] != "tampered"


def test_local_source_allowlist_and_changes(tmp_path):
    path = tmp_path / "private.csv"
    path.write_text("account,amount\nrent,1.23\n")
    sources = LocalSources({"ledger": str(path)})
    result = sources.read("ledger")
    assert result["input_status"] == "unverified_source"
    assert "1.23" in result["text"]
    assert str(tmp_path) not in json.dumps(result)
    assert sources.read(str(path))["error"]["code"] == "SOURCE_NOT_FOUND"
    assert sources.read("../private.csv")["error"]["code"] == "SOURCE_NOT_FOUND"
    path.write_bytes(b"\xff")
    assert sources.read("ledger")["error"]["code"] == "SOURCE_UNAVAILABLE"
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    assert "error" in sources.read("ledger")


def test_local_source_symlink_replacement_refused(tmp_path):
    import os

    if os.name == "nt":
        return  # Windows symlink creation needs a separately granted OS privilege.
    path, secret = tmp_path / "data.txt", tmp_path / "secret.txt"
    path.write_text("original")
    secret.write_text("unconfigured")
    sources = LocalSources({"data": str(path)})
    path.unlink()
    path.symlink_to(secret)
    assert sources.read("data")["error"]["code"] == "SOURCE_UNAVAILABLE"


def test_synthetic_examples_are_explicit_and_not_approved():
    for kind in ("acquisition", "operations"):
        result = synthetic_example(kind)
        assert result["data_class"] == "synthetic"
        assert result["human_approval"] == "not_granted"
        assert result["input_sha256"] == library.sha256(result["inputs"])
    assert synthetic_example("../file")["error"]["code"] == "UNKNOWN_EXAMPLE"
