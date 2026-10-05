"""Build/check the committed lexical index from the original reference corpus."""

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("library_builder", ROOT / "src/platworks/library.py")
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)
parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
folder = ROOT / "src/platworks/data/library"
corpus = json.loads((folder / "references.json").read_text())
index = library.compile_index(corpus)
path = folder / "index.json"
if args.check:
    if json.loads(path.read_text()) != index:
        raise SystemExit("Library index is stale; run scripts/build_library.py")
else:
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "status": "passed",
            "references": len(corpus["references"]),
            "corpus_sha256": index["corpus_sha256"],
        }
    )
)
