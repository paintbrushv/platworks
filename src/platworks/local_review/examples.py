"""Fabricated examples for learning the two local journeys; never approvals."""

import base64
from importlib.resources import files

from .common import encode


def example(kind):
    settings = {
        "data_class": "synthetic",
        "preparer": "Example preparer",
        "policy_id": "synthetic-example",
        "policy_version": "1",
        "policy_date": "2026-10-05",
        "policy_note": "Fabricated training assumptions; replace for your own analysis.",
        "unit_use_note": "Fabricated residential units; no employee, model or down units.",
        "reconciliation_note": "Synthetic rows are complete for this example only.",
    }
    if kind == "acquisition":
        raw = files("platworks").joinpath("data/synthetic_acquisition.json").read_bytes()
        role, name = "inputs", "synthetic-acquisition.json"
        settings.update(
            expected_units=100,
            down_units=0,
            downside={
                "rent_growth_delta_bps": -50,
                "exit_cap_delta_bps": 25,
                "vacancy_delta_bps": 200,
                "opex_growth_delta_bps": 25,
            },
        )
    else:
        role, name = "dataset", "synthetic-operations.json"
        raw = encode(
            {
                "property": "synthetic-ops",
                "period": "2026-05",
                "currency": "USD",
                "expense_convention": "positive_costs",
                "unit_count": 10,
                "actuals": [
                    {
                        "account_code": "4000",
                        "account_name": "Rent",
                        "category": "rental income",
                        "amount": "0.30",
                    }
                ],
                "budgets": [
                    {
                        "account_code": "4000",
                        "account_name": "Rent",
                        "category": "rental income",
                        "amount": "0.29",
                    }
                ],
                "snapshot": {
                    "as_of_date": "2026-05-31",
                    "occupied_units": 9,
                    "vacant_units": 1,
                    "down_units": 0,
                },
            }
        )
        settings.update(
            account_mapping={}, mapping_note="", parent_report=None, correction_reason=""
        )
    return {
        "kind": kind,
        "files": {role: {"filename": name, "data_base64": base64.b64encode(raw).decode("ascii")}},
        "settings": settings,
    }
