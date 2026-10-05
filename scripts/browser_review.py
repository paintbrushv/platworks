"""Synthetic browser acceptance against the installed package and real loopback HTTP."""

import argparse
import base64
import json
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from platworks.local_review.examples import example
from platworks.local_review.server import create_server
from platworks.local_review.store import Workspace


def verify(output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix="plat-synthetic-browser-") as temporary:
        work = Path(temporary)
        server, token = create_server(work / "review")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.set_default_timeout(30000)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{server.server_port}/#{token}")
                    expect(page.locator("#draft-list")).to_contain_text("No drafts yet")
                    page.locator("#example").click()
                    expect(page.locator("#message")).to_contain_text("Synthetic example loaded")
                    page.locator("#prepare-button").click()
                    expect(page.locator("#draft-status")).to_have_text(
                        "synthetic · awaiting execution review"
                    )
                    # A changed unsaved policy must disable approval.
                    page.locator("#policy-note").fill("Synthetic revised policy for browser test")
                    expect(page.locator("#decision-button")).to_be_disabled()
                    page.locator("#prepare-button").click()
                    expect(page.locator("#decision-button")).to_be_enabled()

                    def confirm():
                        page.locator("#reviewer").fill("Synthetic browser reviewer")
                        page.locator("#review-note").fill(
                            "Automated synthetic test only. "
                            "Sources and assumptions inspected by test."
                        )
                        page.locator("#confirmed").check()
                        page.locator("#decision-button").click()

                    confirm()
                    expect(page.locator("#draft-status")).to_contain_text("awaiting report review")
                    expect(page.locator("#result-summary")).to_contain_text("Downside")
                    page.screenshot(path=str(output / "acquisition-calculated.png"), full_page=True)
                    # A browser reload must resume the persisted result without rerunning it.
                    page.reload()
                    page.locator("#draft-list button").first.click()
                    expect(page.locator("#draft-status")).to_contain_text("awaiting report review")
                    confirm()
                    expect(page.locator("#issued")).to_be_visible()

                    def report():
                        with page.expect_download() as pending:
                            page.locator("#download-report").click()
                        result = json.loads(Path(pending.value.path()).read_text())
                        assert result["data_class"] == "synthetic"
                        assert result["certified"] is False
                        return result

                    thesis = report()
                    assert len(thesis["approvals"]) == 2
                    assert thesis["result"]["base"]["metrics"]
                    assert thesis["result"]["downside"]["metrics"]
                    page.locator("#new-draft").click()
                    page.locator("#kind").select_option("operations")
                    page.locator("#example").click()
                    expect(page.locator("#message")).to_contain_text("Synthetic example loaded")
                    source = example("operations")["files"]["dataset"]
                    raw = base64.b64decode(source["data_base64"])
                    inputs = work / source["filename"]
                    inputs.write_bytes(raw)
                    page.locator("#dataset-file").set_input_files(inputs)
                    expect(page.locator("#source-selection")).to_contain_text(source["filename"])
                    page.locator("#prepare-button").click()
                    expect(page.locator("#draft-status")).to_contain_text("awaiting report review")
                    expect(page.locator("#result-summary")).to_contain_text("0.01")
                    expect(page.locator("#result-summary")).to_contain_text("4000 · Rent")
                    assert (
                        page.locator("#result-summary tbody th").first.evaluate(
                            "el => getComputedStyle(el).position"
                        )
                        == "static"
                    )
                    confirm()
                    expect(page.locator("#issued")).to_be_visible()
                    original = report()
                    assert original["result"]["variance"]["noi_bridge"]["noi_variance"] == "0.01"
                    page.locator("#parent-report").select_option(index=1)
                    page.locator("#correction-reason").fill("Synthetic corrected source cent")
                    revised = json.loads(raw)
                    revised["actuals"][0]["amount"] = "0.31"
                    inputs.write_text(json.dumps(revised))
                    page.locator("#dataset-file").set_input_files(inputs)
                    page.locator("#prepare-button").click()
                    expect(page.locator("#draft-status")).to_contain_text("awaiting report review")
                    expect(page.locator("#result-summary")).to_contain_text("Change from prior")
                    confirm()
                    expect(page.locator("#issued")).to_be_visible()
                    correction = report()
                    assert correction["result"]["changes"]["actual_noi"] == "0.01"
                    assert correction["parent_report"]
                    expect(page.locator("#report-list button")).to_have_count(3)
                    page.screenshot(path=str(output / "operations-correction.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(output / "mobile.png"), full_page=True)
                    # Seed unapproved synthetic drafts through the actual workspace API.
                    # Older issued history must remain reachable beyond the first 100 rows.
                    seed = example("acquisition")
                    source = seed["files"]["inputs"]
                    data = json.loads(base64.b64decode(source["data_base64"]))
                    data["metadata"]["deal_id"] = "SYN-PAGINATION"
                    selected = {"inputs": ("synthetic-pagination.json", json.dumps(data).encode())}
                    workspace = Workspace(work / "review")
                    for index in range(101):
                        seed["settings"]["policy_note"] = f"Synthetic history test {index}"
                        workspace.prepare("acquisition", selected, seed["settings"])
                    page.reload()
                    expect(page.locator("#history-older")).to_be_enabled()
                    page.locator("#history-older").click()
                    expect(page.locator("#history-page")).to_have_text("History page 2")
                    page.locator("#draft-list button").filter(has_text="PW-SYN-001").first.click()
                    expect(page.locator("#issued")).to_be_visible()
                    assert report()["kind"] == "acquisition"
                    page.locator("#draft-list button").filter(
                        has_text="synthetic-ops"
                    ).first.click()
                    expect(page.locator("#issued")).to_be_visible()
                    expect(page.locator("#parent-report")).to_have_value(
                        correction["parent_report"]
                    )
                    page.locator("#history-newer").click()
                    expect(page.locator("#history-page")).to_have_text("History page 1")
                    expect(page.locator("#parent-report")).to_have_value(
                        correction["parent_report"]
                    )
                    assert not errors, errors
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return {
        "status": "passed",
        "data_class": "synthetic",
        "human_pilot": False,
        "checks": [
            "acquisition",
            "explicit_decisions",
            "unsaved_edit_blocks_approval",
            "resume",
            "source_upload",
            "operating_report",
            "linked_correction",
            "mobile_layout",
            "history_pagination",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.output)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "result.json").write_text(
            json.dumps({"status": "failed", "error": str(error)})
        )
        raise
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
