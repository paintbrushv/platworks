"use strict";
const $ = (id) => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem("plat-review-session");
if (location.hash) { sessionStorage.setItem("plat-review-session", token); history.replaceState(null, "", "/"); }
let selected = {}, current = null, reports = [], categories = [], dirty = false, working = false, fileReads = 0;
const policyFields = ["data_class", "preparer", "policy_id", "policy_version", "policy_date", "policy_note", "unit_use_note", "reconciliation_note"];
const deltas = ["rent_growth_delta_bps", "exit_cap_delta_bps", "vacancy_delta_bps", "opex_growth_delta_bps"];
const idFor = (name) => name.replaceAll("_", "-");
const labelFor = (name) => name.replaceAll("_", " ");
const format = (value) => JSON.stringify(value, null, 2);
function message(text, isError = false) { $("message").hidden = false; $("message").className = isError ? "error" : "success"; $("message").textContent = text; }
function node(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST", cache: "no-store",
    headers: {Authorization: "Bearer " + (token || ""), ...(body === undefined ? {} : {"Content-Type": "application/json"})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw Error((data.error?.code || "REQUEST_FAILED") + ": " + (data.error?.message || "Request failed"));
  return data;
}
async function download(path, name) {
  const response = await fetch(path, {headers: {Authorization: "Bearer " + token}, cache: "no-store"});
  if (!response.ok) throw Error("Cannot download this retained artifact.");
  const url = URL.createObjectURL(await response.blob()), link = node("a");
  link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function controls() {
  for (const el of document.querySelectorAll("input, select, textarea, button")) el.disabled = working || fileReads > 0;
  if (current) decisionState();
}
async function busy(button, work) {
  if (working || fileReads) return;
  working = true; button.dataset.busy = "true"; controls();
  try { await work(); } catch (error) { message(error.message, true); }
  finally { working = false; delete button.dataset.busy; controls(); }
}
function layout() {
  const ops = $("kind").value === "operations";
  $("operations-files").hidden = !ops; $("acquisition-files").hidden = ops; $("acquisition-settings").hidden = ops;
  const tables = $("ops-layout").value === "tables";
  $("table-files").hidden = !tables; $("dataset-files").hidden = tables;
  $("mapping-editor").hidden = !ops || !current;
  for (const field of ["expected-units", "down-units", ...deltas]) $(field).required = !ops;
  for (const field of ["property", "period", "unit-count"]) $(field).required = ops && tables;
}
function chosenSources() {
  $("source-selection").textContent = Object.entries(selected).map(([role, item]) =>
    `${labelFor(role)}: ${item.filename || "retained source snapshot"}`).join(" · ");
}
function setSettings(settings) {
  for (const name of policyFields) $(idFor(name)).value = settings[name] || "";
  $("expected-units").value = settings.expected_units ?? ""; $("down-units").value = settings.down_units ?? "";
  for (const name of deltas) $(name).value = settings.downside?.[name] ?? "";
  for (const name of ["property", "period", "unit_count", "mapping_note", "correction_reason"]) $(idFor(name)).value = settings[name] ?? "";
  $("parent-report").value = settings.parent_report || "";
}
function settings() {
  const data = Object.fromEntries(policyFields.map((name) => [name, $(idFor(name)).value]));
  if ($("kind").value === "acquisition") {
    data.expected_units = Number($("expected-units").value); data.down_units = Number($("down-units").value);
    data.downside = Object.fromEntries(deltas.map((name) => [name, Number($(name).value)]));
  } else {
    data.account_mapping = Object.fromEntries([...$("mapping-controls").querySelectorAll("select")].map((s) => [s.dataset.account, s.value]).filter((row) => row[1]));
    data.mapping_note = $("mapping-note").value; data.parent_report = $("parent-report").value || null; data.correction_reason = $("correction-reason").value;
    if ($("ops-layout").value === "tables") { data.property = $("property").value; data.period = $("period").value; data.unit_count = Number($("unit-count").value); }
  }
  return data;
}
async function refreshHistory() {
  const state = await api("/api/state"); reports = state.reports; categories = state.categories;
  $("draft-list").replaceChildren(); $("report-list").replaceChildren();
  if (!state.drafts.length) $("draft-list").append(node("p", "No drafts yet.", "muted"));
  for (const draft of state.drafts) {
    const button = node("button", draft.subject + (draft.period ? " · " + draft.period : ""), "history");
    button.append(node("small", labelFor(draft.status) + (draft.active ? "" : " · prior draft")));
    button.onclick = () => busy(button, async () => show(await api("/api/draft?id=" + draft.id), true)); $("draft-list").append(button);
  }
  if (!reports.length) $("report-list").append(node("p", "Reports appear after review.", "muted"));
  const parent = $("parent-report").value; $("parent-report").replaceChildren(new Option("New period / no parent", ""));
  for (const report of reports) {
    const button = node("button", report.subject + (report.period ? " · " + report.period : " · original thesis"), "history");
    button.append(node("small", report.parent_report ? "Linked correction" : "Original report"));
    button.onclick = () => busy(button, async () => { const record = await api("/api/report?id=" + report.id); show(await api("/api/draft?id=" + record.draft_id), true); });
    $("report-list").append(button);
    if (report.kind === "operations") $("parent-report").add(new Option(report.subject + " · " + report.period + " · " + report.id.slice(0, 10), report.id));
  }
  $("parent-report").value = parent;
}
function summaryTable(title, values, target) {
  target.append(node("h3", title)); const table = node("table"), tbody = node("tbody");
  for (const [key, value] of Object.entries(values || {})) {
    if (value && typeof value === "object") continue;
    const row = node("tr"); row.append(node("th", labelFor(key)), node("td", value === null ? "Not available" : String(value))); tbody.append(row);
  }
  table.append(tbody); target.append(table);
}
function decisionState() {
  if (!current) return;
  const issue = current.review_payload.action === "issue", issued = current.status === "issued";
  $("decision-form").hidden = issued; $("issued").hidden = !issued;
  const title = issue ? current.kind === "acquisition" ? "Freeze the original thesis" : "Issue the reviewed operating report" : "Authorize the base and downside calculation";
  $("decision-title").textContent = title; $("decision-button").textContent = title;
  $("decision-help").textContent = issue ? "Inspect the calculation, effective assumptions and owner questions. This decision records an immutable reviewed draft." : "Review source mappings, validation and policy. The engine runs only after you authorize it.";
  $("decision-button").disabled = working || fileReads > 0 || dirty || !!current.blockers.length || !current.active || current.producer_current === false;
}
function show(draft, restore) {
  current = draft; dirty = false; $("review-panel").hidden = false;
  if (restore) {
    $("kind").value = draft.kind;
    $("ops-layout").value = draft.sources.dataset ? "dataset" : "tables";
    selected = Object.fromEntries(Object.entries(draft.sources).map(([role, source]) => [role, {sha256: source.sha256}]));
    for (const role of ["inputs", "dataset", "actuals", "budgets", "snapshot"]) $(role + "-file").value = "";
    setSettings(draft.settings); chosenSources();
  }
  layout(); $("draft-status").textContent = labelFor(draft.settings.data_class) + " · " + labelFor(draft.status);
  $("prepare-button").textContent = "Save revised draft";
  $("findings").replaceChildren();
  for (const [items, severity] of [[draft.blockers, "error"], [draft.warnings, "warning"]]) for (const item of items) {
    const box = node("div", undefined, "notice " + severity); box.append(node("strong", labelFor(item.code).toLowerCase()), node("p", item.message));
    if (item.path) box.append(node("small", item.path)); $("findings").append(box);
  }
  if (!draft.active) $("findings").prepend(node("p", "This draft has been replaced. Open the active draft to approve further work.", "notice error"));
  if (draft.producer_current === false) $("findings").prepend(node("p", "Installed code changed. Prepare a new draft before approving.", "notice error"));
  if (!draft.blockers.length && !draft.warnings.length) $("findings").append(node("p", draft.status === "issued" ? "Human review recorded. The retained report contains the decision and its supporting notes." : "Automated checks passed. Human source and economic review is still required.", "notice"));
  $("source-links").replaceChildren();
  for (const [role, source] of Object.entries(draft.sources)) {
    const row = node("div", undefined, "source"), caption = node("div", labelFor(role) + " · " + source.filename);
    caption.append(node("small", "SHA-256 " + source.sha256)); const button = node("button", "Download source");
    button.onclick = () => busy(button, () => download("/api/source?sha=" + source.sha256, source.filename)); row.append(caption, button); $("source-links").append(row);
  }
  const tbody = $("mapping-table").querySelector("tbody"); tbody.replaceChildren();
  for (const mapping of draft.mappings) {
    const row = node("tr"); row.append(node("td", mapping.target), node("td", mapping.source + " · " + format(mapping.locator)), node("td", format(mapping.value))); tbody.append(row);
  }
  $("normalized").textContent = format(draft.normalized); $("effective-policy").textContent = format(draft.settings);
  $("identity").textContent = format({draft: draft.id, review: draft.review_sha256, producers: draft.producer_identity});
  $("mapping-controls").replaceChildren();
  if (draft.kind === "operations") {
    const accounts = new Map(); for (const row of [...draft.normalized.actuals, ...draft.normalized.budgets]) accounts.set(row.account_code, row);
    for (const [code, row] of accounts) {
      const label = node("label", code + " · " + row.account_name), select = node("select"); select.dataset.account = code;
      select.add(new Option("Choose category", "")); for (const category of categories) select.add(new Option(labelFor(category), category)); select.value = categories.includes(row.category) ? row.category : "";
      label.append(select); $("mapping-controls").append(label);
    }
  }
  $("results").hidden = !draft.result; $("result-summary").replaceChildren(); $("owner-questions").replaceChildren();
  if (draft.result) {
    if (draft.kind === "acquisition") {
      $("result-summary").append(node("p", "Both cases use the retained acquisition source. The downside applies your selected rent-growth, cap-rate, vacancy and expense-growth changes. IRR, cap rate and cash-on-cash values are fractions (0.07 = 7%); equity multiples and DSCR are ratios.", "help"));
      for (const name of ["base", "downside"]) summaryTable(name === "base" ? "Base" : "Downside", draft.result.comparison[name].metrics, $("result-summary"));
    } else {
      $("result-summary").append(node("p", "The bridge uses matched actual and budget accounts. NOI is revenue less positive expense costs. Account variances are actual minus budget; a positive expense variance reduces NOI. Signed credits retain their sign.", "help"));
      summaryTable("NOI bridge · USD", draft.result.variance.noi_bridge, $("result-summary"));
      const accounts = node("table"), head = node("tr"), body = node("tbody"), wrap = node("div", undefined, "table-wrap");
      for (const title of ["Account", "Category", "Actual · USD", "Budget · USD", "Variance · USD"]) head.append(node("th", title));
      accounts.className = "account-variance";
      const thead = node("thead"); thead.append(head); accounts.append(thead);
      for (const account of draft.result.variance.by_account) {
        const row = node("tr");
        for (const value of [account.account_code + " · " + account.account_name, account.category, account.actual, account.budget, account.variance]) row.append(node("td", value));
        body.append(row);
      }
      accounts.append(body); wrap.append(accounts); $("result-summary").append(node("h3", "Account variance · actual minus budget"), wrap);
      if (Object.keys(draft.result.changes).length) summaryTable("Change from prior issued revision · USD", draft.result.changes, $("result-summary"));
      if (draft.result.excluded_accounts.length) $("result-summary").append(node("p", "Unmatched accounts are excluded from this bridge. Resolve coverage before issuing.", "notice error"));
    }
    const questions = draft.kind === "acquisition" ? ["Does the base case agree with your reviewed source and policy evidence?", "Which downside assumptions change the ownership decision?", "Are tax, insurance, debt, unit-use and exit assumptions supported and dated?"] : ["What explains the actual-versus-budget NOI bridge?", "Which variances or signed credits are recurring, and who owns each follow-up?", "Do occupancy, down-unit use and account coverage reconcile for this exact month?"];
    for (const question of questions) $("owner-questions").append(node("li", question));
    $("result-json").textContent = format(draft.result);
  }
  $("confirmed").checked = false; $("review-note").value = ""; decisionState();
  $("download-report").onclick = () => busy($("download-report"), () => download("/api/report?id=" + draft.report_id, "platworks-reviewed-report.json"));
}
for (const role of ["inputs", "dataset", "actuals", "budgets", "snapshot"]) $(role + "-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  delete selected[role]; chosenSources();
  if (current) { dirty = true; decisionState(); }
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) { message("Each source is limited to 2 MiB.", true); event.target.value = ""; return; }
  fileReads += 1; controls();
  try {
    const data = new Uint8Array(await file.arrayBuffer()); let binary = "";
    for (let i = 0; i < data.length; i += 8192) binary += String.fromCharCode(...data.subarray(i, i + 8192));
    selected[role] = {filename: file.name, data_base64: btoa(binary)}; chosenSources();
  } catch (_) { message("Cannot read this source. Select the file again.", true); }
  finally { fileReads -= 1; controls(); }
});
$("prepare-form").addEventListener("input", () => {
  if (current) { dirty = true; decisionState(); message("Unsaved source or assumption changes. Save a revised draft before approving.", true); }
});
$("kind").onchange = () => { selected = {}; current = null; $("review-panel").hidden = true; $("mapping-controls").replaceChildren(); layout(); chosenSources(); };
$("ops-layout").onchange = () => { selected = {}; layout(); chosenSources(); };
$("prepare-form").onsubmit = (event) => { event.preventDefault(); busy($("prepare-button"), async () => {
  const kind = $("kind").value, roles = kind === "acquisition" ? ["inputs"] : $("ops-layout").value === "dataset" ? ["dataset"] : ["actuals", "budgets", "snapshot"];
  const inputs = Object.fromEntries(roles.filter((role) => selected[role]).map((role) => [role, selected[role]]));
  const draft = await api("/api/prepare", {kind, files: inputs, settings: settings()}); await refreshHistory(); show(draft, true);
  message(draft.blockers.length ? "Draft saved with blockers. Resolve them before approval." : "Draft saved. Inspect the source mappings and assumptions below.", !!draft.blockers.length);
  $("review-panel").scrollIntoView({behavior: "smooth", block: "start"});
}); };
$("decision-form").onsubmit = (event) => { event.preventDefault(); busy($("decision-button"), async () => {
  if (dirty) throw Error("Save the revised draft before approving.");
  const action = current.review_payload.action;
  const draft = await api("/api/" + action, {draft_id: current.id, review_sha256: current.review_sha256,
    reviewer: $("reviewer").value, note: $("review-note").value, confirmed: $("confirmed").checked});
  await refreshHistory(); show(draft, true); message(action === "execute" ? "Calculation complete. Review both cases before freezing the original thesis." : "Reviewed report recorded. Its source files and earlier history are preserved.");
}); };
$("example").onclick = () => busy($("example"), async () => {
  const data = await api("/api/example?kind=" + $("kind").value); selected = data.files; current = null;
  $("ops-layout").value = "dataset"; setSettings(data.settings); $("review-panel").hidden = true; $("mapping-controls").replaceChildren(); layout(); chosenSources();
  message("Synthetic example loaded. Review the settings, prepare the draft, and make each decision yourself.");
});
$("new-draft").onclick = () => { $("prepare-form").reset(); current = null; selected = {}; $("review-panel").hidden = true; $("message").hidden = true; $("mapping-controls").replaceChildren(); $("prepare-button").textContent = "Prepare draft"; layout(); chosenSources(); window.scrollTo({top: 0, behavior: "smooth"}); };
layout(); refreshHistory().catch((error) => message(error.message, true));
