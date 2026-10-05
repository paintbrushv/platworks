# Review local acquisition and operating files

Milestone D adds `platworks review WORKSPACE` to the unpublished analysis candidate.
It opens a local browser interface for ownership and asset-management review.
Files stay in your chosen local workspace. Human decisions, source mappings,
effective assumptions and producer identities are retained with the results.

```bash
platworks doctor --analysis
platworks review ./my-review-workspace
```

Keep the printed session link private. Use `--no-open` to open it yourself, and
Ctrl-C to stop the server. Reopen the same workspace to resume. Use **Older**
and **Newer** in the history panel to reach records beyond the latest 100. Use a directory
outside a source repository or shared/cloud-synced folder for private files.
The analysis profile is required. A catalog-only install cannot calculate.

## Acquisition walkthrough

1. Choose **Acquisition** and select canonical JSON or the standardized CSV/XLSX
   below. **Load synthetic example** fills a fabricated example for learning.
2. Declare whether the source is synthetic or user supplied. Enter the preparer,
   dated policy ID/version, source reconciliation, unit-use evidence and expected
   unit count. Supply explicit downside changes in basis points (100 bps = one
   percentage point). At least one stress must be nonzero.
3. **Prepare draft**. Inspect blockers, warnings, downloaded source bytes, every
   field mapping, normalized input and policy. The original filename and SHA-256
   accompany each source. Correct a file or assumption and save a revised draft
   when needed. Unsupported files are refused with a reason.
4. Enter your reviewer name and decision notes, confirm the exact draft, then
   **Authorize the base and downside calculation**. This grants execution only.
5. Review both cases, their full effective inputs, ownership questions and engine
   results. Record your conclusion and separately **Freeze the original thesis**.
   Download the report or reopen it from history. The original thesis cannot be
   replaced for the same canonical deal ID.

Initial acquisition support requires **zero down units**, reconciled cohort
counts, explicit purchase/debt/exit/growth assumptions, operating expenses and
fund assumptions. Every expense needs an explicit `growth_rate`; the sponsor/LP
shares, preferred return, partnership costs and acquisition/management/disposition
fees must be supplied. Optional engine defaults still apply where optional fields
are omitted, and the review shows that limitation. Growth must use `annual_compound`. Rent-growth stress must be
nonpositive; cap-rate, vacancy and expense-growth stresses must be nonnegative.
Each change is bounded to 2,000 bps. Both effective scenarios are engine-validated.
Optional capex, renovation and revenue schedules must be inspected by the reviewer;
the workflow cannot supply missing source evidence. Nonzero/unresolved down-unit
schedules require later workflow support. The engine remains the calculation owner.

### Acquisition formats

Canonical JSON follows the installed underwriting engine's input schema; the
synthetic example is a complete example. The workflow preserves its numeric
values and records the original bytes. Editing a downloaded synthetic source
does not make its fabricated assumptions suitable for an actual investment.

CSV must be UTF-8 and have exactly `pointer,value_json` as its header. XLSX must
contain exactly one worksheet, **Inputs**, with the same headers. Each row maps
one JSON scalar to its canonical JSON pointer. Use JSON string quoting inside
`value_json`; in CSV, escape those quotes using ordinary CSV quoting.

```csv
pointer,value_json
/schema_version,"""0.1"""
/metadata/deal_id,"""example-only"""
/unit_cohorts/0/unit_count,100
```

This fragment is not a complete deal. Include every leaf field of the canonical
input. Empty arrays/objects may be represented as `[]`/`{}`. Arrays must start at
index zero without gaps. Duplicate/overlapping pointers are refused. `/` and `~`
in a key use JSON pointer escapes `~1` and `~0`.

## Operations walkthrough

1. Choose **Operations**. Select a canonical dataset JSON, or select separate
   actual and budget CSV/XLSX files plus a snapshot JSON. For tables, enter the
   exact property ID, month (`YYYY-MM`) and total unit count.
2. Enter the dated close policy, unit-use evidence and reconciliation notes.
   Prepare the draft. Inspect source rows, sign conventions, coverage, occupancy,
   blockers, category mappings and the Rust-calculated NOI bridge.
3. Map any unknown accounts to a supported category and explain changes. Save
   the revised draft. Every row for an account uses that chosen category.
4. Answer the ownership questions in decision notes, enter your reviewer name,
   confirm the exact result and **Issue the reviewed operating report**.
5. To correct that month, select its **latest issued report** as the parent,
   supply corrected source files and a reason, then prepare a new draft. Review
   its change bridge and issue it explicitly. The original report and source
   files remain unchanged. A stale parent is blocked.

Operating money is USD decimal-string money with at most two fractional digits;
exact cents and variance arithmetic belong to Rust. Expenses use positive costs;
signed credits are preserved. Negative net expenses require explicit inspection
and appear as a warning. Unmatched actual/budget accounts, invalid occupancy,
excess precision and overflow prevent issuance. Zero budget must be an explicit
row; absence is not treated as zero.

### Operations formats

A dataset JSON has exactly these keys:

```json
{
  "property": "synthetic-ops",
  "period": "2026-05",
  "currency": "USD",
  "expense_convention": "positive_costs",
  "unit_count": 10,
  "actuals": [{"account_code":"4000","account_name":"Rent","category":"rental income","amount":"0.30"}],
  "budgets": [{"account_code":"4000","account_name":"Rent","category":"rental income","amount":"0.29"}],
  "snapshot": {"as_of_date":"2026-05-31","occupied_units":9,"vacant_units":1,"down_units":0}
}
```

The amounts above deliberately test a one-cent variance; they are fabricated.

Actual and budget CSV files must each have exactly this header and one property
and month throughout. XLSX uses exactly one **GL** worksheet with these headers:

```csv
property,period,account_code,account_name,category,amount
synthetic-ops,2026-05,4000,Rent,rental income,0.30
```

The separate snapshot JSON contains the `snapshot` object shown above, without
an outer `snapshot` key. Snapshot date and counts must reconcile for that month.
Split exports containing different properties/months before review. Supported
categories are rental income, concessions, bad debt, other income, payroll,
repairs & maintenance, utilities, marketing, administrative, taxes, insurance
and management fees. Match their exact spelling or choose an explicit mapping.

## File and review limits

- Acquisition review allows 1–600 monthly periods and up to 1,000 cohorts.
- Each file is at most 2 MiB. Tables allow 10,000 data rows. Expanded XLSX content
  is at most 16 MiB. XLSX cells must be text, including codes and money; formulas
  and numeric/date cells are refused to avoid guessing at their meaning.
- Canonical JSON allows 10,000 leaf values per source, 64 nesting levels, and
  1 MiB of combined UTF-8 source locators. Empty containers count as leaf values.
  Each JSON pointer allows 1,000 characters; table input pointers also allow at
  most 64 levels. Inputs exceeding any limit are refused before review.
- Canonical JSON and these standardized layouts are supported. Raw vendor rent
  rolls, T12 workbooks, scanned PDFs and arbitrary exports need a separately
  reviewed normalization step. The interface retains the selected canonical
  files; it does not claim independent reconciliation to documents not supplied.
- An approval binds source hashes, mappings, settings, producer code and the
  specific calculation. Revised drafts need fresh review. Restoring earlier
  source bytes also creates a fresh review generation. Close and restart review
  after upgrading installed code, then prepare and review a fresh draft. Unsaved form edits disable
  approval. Repeating an already successful decision returns its original result.
- A successful report has contract `local-reviewed-draft/1.0.0`, status
  `reviewed_local_draft`, explicit data class and `certified: false`. It includes
  provenance, full effective assumptions, warnings and human decision records.
  The existing synthetic `approved-execution/1.0.0` contract is unchanged. A Rust
  result's own `human_approval: not_granted` remains unchanged; the outer local
  report records the actual review decision.
- The local OS account is trusted. Reviewer names are recorded attestations,
  not verified organizational identities. A colleague can review on this computer;
  this is not remote collaboration or authenticated separation of duties. Code
  with access to the OS account/workspace can act with that account's authority.
  No MCP tool can grant these approvals.
- The UI binds only to `127.0.0.1`, uses a fresh session capability and checks
  Host/Origin. It sends no files to an assistant or external service. It has no
  HTTP access logs. Original files live in `review.sqlite`; protect and back up
  that workspace with your operating system's permissions/encryption. Close the
  server before copying its database. Reports refer to original source hashes;
  retain the workspace or separately download the corresponding source files.

## Verification status

Automated checks use fabricated files and simulated decisions. The installed
probe (`python -I -m platworks.verify_install`) exercises acquisition, restart,
operating issuance and a linked one-cent correction in a temporary workspace.
It records `human_pilot: false` and deletes those test records afterward.

The installed-wheel suite, real loopback HTTP checks and synthetic Chromium
journeys pass locally. Browser checks cover file upload, both decisions, unsaved
changes, resume, linked corrections and mobile layout. CI repeats the browser
check and runs the installed-workflow probe across the supported platform matrix.
Actual independent-reviewer, first-time-user and private vendor-file acceptance
remain release gates; automated synthetic checks are not evidence of those pilots.
