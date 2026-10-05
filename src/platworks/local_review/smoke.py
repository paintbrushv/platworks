"""Installed-workflow probe with fabricated files and simulated decisions only.

This temporary self-test is never a production approval or human pilot record.
"""

import base64
import json
import tempfile
from pathlib import Path

from .common import encode
from .examples import example
from .store import Workspace


def verify():
    if not __debug__:
        raise RuntimeError("Run installation checks without Python optimization")

    def prepare(workspace, payload):
        sources = {
            role: (item["filename"], base64.b64decode(item["data_base64"], validate=True))
            for role, item in payload["files"].items()
        }
        draft = workspace.prepare(payload["kind"], sources, payload["settings"])
        assert not draft["blockers"], "Synthetic workflow blocked"
        return draft

    def simulate(workspace, draft, action):
        return workspace.decide(
            action,
            draft["id"],
            draft["review_sha256"],
            reviewer="Synthetic installation test",
            note="Automated synthetic check; no real human approval or pilot occurred.",
            confirmed=True,
        )

    with tempfile.TemporaryDirectory(prefix="plat-synthetic-review-") as temporary:
        root = Path(temporary) / "workspace"
        workspace = Workspace(root)
        acquisition = prepare(workspace, example("acquisition"))
        assert acquisition["result"] is None and acquisition["report_id"] is None
        calculated = simulate(workspace, acquisition, "execute")
        assert calculated["review_sha256"] != acquisition["review_sha256"]
        assert calculated["result"]["base"]["metrics"]
        assert calculated["result"]["downside"]["metrics"]
        # Persist/reopen between the two decisions.
        workspace = Workspace(root)
        thesis = simulate(workspace, workspace.get(calculated["id"]), "issue")
        assert len(workspace.report(thesis["report_id"])["approvals"]) == 2
        payload = example("operations")
        original = simulate(workspace, prepare(workspace, payload), "issue")
        original_report = workspace.report(original["report_id"])
        assert original_report["result"]["variance"]["noi_bridge"]["noi_variance"] == "0.01"
        data = json.loads(base64.b64decode(payload["files"]["dataset"]["data_base64"]))
        data["actuals"][0]["amount"] = "0.31"
        payload["files"]["dataset"]["data_base64"] = base64.b64encode(encode(data)).decode("ascii")
        payload["settings"].update(
            parent_report=original["report_id"], correction_reason="Synthetic cent correction"
        )
        corrected = simulate(workspace, prepare(workspace, payload), "issue")
        revised = workspace.report(corrected["report_id"])
        assert revised["result"]["changes"]["actual_noi"] == "0.01"
        assert revised["parent_report"] == original["report_id"]
        assert workspace.report(original["report_id"]) == original_report
        assert simulate(workspace, corrected, "issue")["report_id"] == corrected["report_id"]
        assert len(workspace.list_reports()) == 3
    return {
        "status": "passed",
        "data_class": "synthetic",
        "human_pilot": False,
        "checks": [
            "two_phase_acquisition",
            "restart",
            "rust_operating_review",
            "one_cent_linked_correction",
            "immutable_original",
            "idempotent_issue",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
