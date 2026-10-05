"""Versioned public references and a deterministic, packaged lexical index."""

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from importlib.resources import files

STOP = frozenset(
    "a an and are as at be by for from in is it of on or that the this to with".split()
)


class LibraryError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def tokens(text):
    return [
        word
        for word in re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", text).lower())
        if word not in STOP
    ]


def compile_index(corpus):
    references = corpus.get("references", [])
    if not references or len({ref["id"] for ref in references}) != len(references):
        raise LibraryError("LIBRARY_INTEGRITY", "References must have unique IDs.")
    documents = {}
    for reference in references:
        if not re.fullmatch(r"mf\.[a-z0-9-]{1,64}", reference["id"]):
            raise LibraryError("LIBRARY_INTEGRITY", "Reference IDs must be stable.")
        if not reference["source_ids"] or any(
            key not in corpus["sources"] for key in reference["source_ids"]
        ):
            raise LibraryError("LIBRARY_INTEGRITY", "Each reference needs identified sources.")
        words = tokens(
            " ".join(
                [reference["title"]] * 3
                + reference["keywords"] * 2
                + [reference["summary"], reference["body"]]
            )
        )
        documents[reference["id"]] = {
            "terms": dict(sorted(Counter(words).items())),
            "length": len(words),
            "sha256": sha256(reference),
        }
    return {
        "contract_version": "plat.library-index/1",
        "corpus_sha256": sha256(corpus),
        "documents": documents,
    }


@lru_cache(maxsize=1)
def _load():
    root = files("platworks").joinpath("data", "library")
    corpus = json.loads(root.joinpath("references.json").read_text("utf-8"))
    index = json.loads(root.joinpath("index.json").read_text("utf-8"))
    if index != compile_index(corpus):
        raise LibraryError(
            "LIBRARY_INTEGRITY", "The packaged library index does not match its references."
        )
    return corpus, index


def get_reference(reference_id, version=None):
    if not isinstance(reference_id, str) or not re.fullmatch(r"mf\.[a-z0-9-]{1,64}", reference_id):
        raise LibraryError(
            "INVALID_REFERENCE", "Use a stable reference ID returned by search_library."
        )
    corpus, index = _load()
    reference = next((r for r in corpus["references"] if r["id"] == reference_id), None)
    if reference is None:
        raise LibraryError("REFERENCE_NOT_FOUND", "No packaged reference has that ID.")
    if version is not None and version != reference["version"]:
        raise LibraryError("REFERENCE_VERSION_NOT_FOUND", "That reference version is not packaged.")
    return {
        "contract_version": "plat.library-reference/1",
        "library_version": corpus["version"],
        "corpus_sha256": index["corpus_sha256"],
        "reference_sha256": index["documents"][reference_id]["sha256"],
        "reference": copy.deepcopy(reference),
        "sources": [copy.deepcopy(corpus["sources"][key]) for key in reference["source_ids"]],
    }


def search_library(query, limit=5):
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise LibraryError(
            "INVALID_QUERY", "Provide a nonempty search query of at most 500 characters."
        )
    if type(limit) is not int or not 1 <= limit <= 10:
        raise LibraryError("INVALID_LIMIT", "Request between one and ten references.")
    corpus, index = _load()
    documents = index["documents"]
    terms = sorted(set(tokens(query)))
    count = len(documents)
    average = sum(doc["length"] for doc in documents.values()) / count
    frequencies = {term: sum(term in doc["terms"] for doc in documents.values()) for term in terms}
    ranked = []
    for reference in corpus["references"]:
        doc = documents[reference["id"]]
        score = 0
        for term in terms:
            frequency = doc["terms"].get(term, 0)
            if frequency:
                idf = math.log(1 + (count - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                score += (
                    idf
                    * frequency
                    * 2.2
                    / (frequency + 1.2 * (0.25 + 0.75 * doc["length"] / average))
                )
        if score:
            ranked.append((score, reference))
    ranked.sort(key=lambda item: (-round(item[0], 12), item[1]["id"]))
    return {
        "contract_version": "plat.library-search/1",
        "library_version": corpus["version"],
        "corpus_sha256": index["corpus_sha256"],
        "query": query,
        "count": min(len(ranked), limit),
        "total_matches": len(ranked),
        "results": [
            {
                key: copy.deepcopy(ref[key])
                for key in ("id", "version", "title", "summary", "applicability", "review")
            }
            | {"reference_sha256": documents[ref["id"]]["sha256"]}
            for _, ref in ranked[:limit]
        ],
    }
