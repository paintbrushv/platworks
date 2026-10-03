"""Check public catalog claims against recorded or live GitHub metadata."""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from platworks import catalog


def verify(live=False):
    snapshot = Path(__file__).resolve().parents[1] / "docs/catalog-evidence.json"
    evidence = json.loads(snapshot.read_text())
    recorded = {item["name"]: item for item in evidence["components"]}
    public = {item["name"]: item for item in catalog.list_components() if item["public"]}
    if set(recorded) != set(public):
        raise ValueError("public catalog membership differs from the evidence snapshot")
    for name, component in public.items():
        source = recorded[name]
        if live:
            request = Request(f"https://api.github.com/repos/paintbrushv/{name}",
                              headers={"User-Agent": "platworks-catalog-verifier"})
            with urlopen(request, timeout=20) as response:
                data = json.load(response)
            source = {
                "repository": data["html_url"], "visibility": data["visibility"],
                "description": data["description"],
                "license": (data.get("license") or {}).get("spdx_id"),
            }
        expected = {
            "repository": component["repo"], "visibility": component["status"],
            "description": component["description"], "license": component["license"],
        }
        for key, value in expected.items():
            if source[key] != value:
                raise ValueError(f"catalog metadata drift: {name}.{key}")
    return {"status": "passed", "public_components": len(public),
            "source": "live GitHub public API" if live else "committed snapshot",
            "snapshot_date": evidence["verified_on"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.live), indent=2))
