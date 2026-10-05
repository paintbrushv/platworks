"""Transactional, private local review workspace; no MCP approval API.

Original bytes and issued history are immutable application records. The local
OS account is trusted; this is an attestation log, not an identity provider.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import CONTRACT, producers
from .common import ReviewError, decode, digest, encode, finding, identity, now, refuse, text
from .normalize import normalize

DDL = """
CREATE TABLE IF NOT EXISTS metadata (contract TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS blobs (sha TEXT PRIMARY KEY, body BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, body_sha TEXT NOT NULL, item TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS heads (item TEXT PRIMARY KEY, draft TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions (draft TEXT PRIMARY KEY, body_sha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, draft TEXT UNIQUE NOT NULL,
 item TEXT NOT NULL, parent TEXT UNIQUE, body_sha TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, body_sha TEXT NOT NULL,
 payload_sha TEXT NOT NULL, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS draft_index (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
 subject TEXT NOT NULL, period TEXT, blocked INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS source_index (draft TEXT NOT NULL, role TEXT NOT NULL,
 sha TEXT NOT NULL, filename TEXT NOT NULL, PRIMARY KEY(draft, role));
CREATE INDEX IF NOT EXISTS source_index_sha ON source_index(sha);
"""


class Workspace:
    def __init__(self, path):
        try:
            self._session_identity = producers.producer_identity()
        except (ImportError, OSError, producers.OpsProducerError):
            refuse(
                "BACKEND_UNAVAILABLE",
                "Install the analysis profile and run platworks doctor --analysis.",
            )
        self.path = Path(path).absolute()
        if self.path.is_symlink():
            refuse("UNSAFE_WORKSPACE", "Choose a local workspace directory, not a symlink.")
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.path / "review.sqlite"
        if self.database.is_symlink():
            refuse("UNSAFE_WORKSPACE", "The workspace database must not be a symlink.")
        created = not self.database.exists()
        if created:
            fd = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        with self._connect() as connection:
            if created:
                connection.execute("PRAGMA application_id=1347899972")
                connection.execute("PRAGMA user_version=1")
            elif (
                connection.execute("PRAGMA application_id").fetchone()[0] != 1347899972
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                refuse("WORKSPACE_VERSION", "This is not a supported local review database.")
            connection.executescript(DDL)
            versions = connection.execute("SELECT contract FROM metadata").fetchall()
            if versions and versions != [(CONTRACT,)]:
                refuse("WORKSPACE_VERSION", "This workspace uses a different review contract.")
            connection.execute("INSERT OR IGNORE INTO metadata VALUES (?)", (CONTRACT,))
            for table in (
                "blobs",
                "drafts",
                "executions",
                "reports",
                "approvals",
                "metadata",
                "draft_index",
                "source_index",
            ):
                for verb in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb} BEFORE "
                        f"{verb} ON {table} BEGIN SELECT RAISE(ABORT, "
                        "'immutable review record'); END"
                    )
            # Additive indexes for older local workspaces. Backfill one verified
            # draft at a time; retained artifacts and their identities never change.
            for row in connection.execute(
                "SELECT d.id FROM drafts d LEFT JOIN draft_index i ON i.id=d.id "
                "WHERE i.id IS NULL OR NOT EXISTS "
                "(SELECT 1 FROM source_index s WHERE s.draft=d.id)"
            ):
                self._index_draft(connection, row[0], self._draft(connection, row[0]))

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=3)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        except sqlite3.Error:
            refuse(
                "WORKSPACE_BUSY_OR_CORRUPT", "Workspace unavailable; close other writers and retry."
            )
        finally:
            connection.close()

    def _put(self, connection, raw):
        sha = digest(raw)
        connection.execute("INSERT OR IGNORE INTO blobs VALUES (?,?)", (sha, raw))
        if self._blob(connection, sha) != raw:
            refuse("INTEGRITY_ERROR", "Stored content does not match its identity.")
        return sha

    def _blob(self, connection, sha):
        row = connection.execute("SELECT body FROM blobs WHERE sha=?", (sha,)).fetchone()
        if not row or digest(row[0]) != sha:
            refuse("INTEGRITY_ERROR", "A stored artifact is missing or has changed.")
        return row[0]

    def _record(self, connection, table, key, column="id"):
        # Table and column are fixed internal names, never request strings.
        row = connection.execute(
            f"SELECT body_sha FROM {table} WHERE {column}=?", (key,)
        ).fetchone()
        if not row:
            refuse("NOT_FOUND", "The requested review record does not exist.")
        return decode(self._blob(connection, row[0]))

    def _draft(self, connection, draft_id):
        body = self._record(connection, "drafts", draft_id)
        if identity(body["binding"]) != draft_id:
            refuse("INTEGRITY_ERROR", "Draft identity changed.")
        for source in body["sources"].values():
            self._blob(connection, source["sha256"])
        return body

    def _latest(self, connection, item):
        row = connection.execute(
            "SELECT id FROM reports WHERE item=? ORDER BY rowid DESC LIMIT 1", (item,)
        ).fetchone()
        return row[0] if row else None

    def _index_draft(self, connection, draft_id, body):
        connection.execute(
            "INSERT INTO draft_index VALUES (?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (draft_id, body["kind"], body["subject"], body["period"], bool(body["blockers"])),
        )
        connection.executemany(
            "INSERT INTO source_index VALUES (?,?,?,?) ON CONFLICT(draft,role) DO NOTHING",
            [
                (draft_id, role, source["sha256"], source["filename"])
                for role, source in body["sources"].items()
            ],
        )

    def prepare(self, kind, files, settings):
        # A live process retains imported code. A package update must not make
        # old in-memory normalization claim the new files' identities.
        self._ensure_session()
        normalized = normalize(kind, files, settings)
        code = producers.producer_identity()
        item = identity(
            {"kind": kind, "subject": normalized["subject"], "period": normalized["period"]}
        )
        binding = {
            "contract_version": CONTRACT,
            "kind": kind,
            "settings": settings,
            "sources": normalized["sources"],
            "normalized": normalized["normalized"],
            "mappings": normalized["mappings"],
            "producer_identity": code,
            "item": item,
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute("SELECT draft FROM heads WHERE item=?", (item,)).fetchone()
            if active and self._draft(connection, active[0])["binding"]["content"] == binding:
                return self._view(connection, active[0])
            # Restoring older source bytes creates a fresh review generation.
            # It never revives the approvals belonging to a superseded draft.
            binding = {"content": binding, "previous_draft": active[0] if active else None}
            draft_id = identity(binding)
            result, database_sha = None, None
            blockers = normalized["blockers"]
            parent = settings.get("parent_report")
            current = self._latest(connection, item)
            if kind == "operations":
                parent_db, parent_revision = None, None
                if parent != current:
                    blockers.append(
                        finding("STALE_PARENT", "Select the current issued report for correction.")
                    )
                elif parent:
                    previous = self._report(connection, parent)
                    if previous["item"] != item or previous["kind"] != "operations":
                        refuse(
                            "STALE_PARENT",
                            "Correction parent belongs to another property or period.",
                        )
                    if (
                        not isinstance(settings.get("correction_reason"), str)
                        or not settings["correction_reason"].strip()
                    ):
                        blockers.append(
                            finding("CORRECTION_REASON", "Explain the correction before review.")
                        )
                    parent_db = self._blob(connection, previous["database_sha256"])
                    parent_revision = previous["result"]["revision_id"]
                if not any(b["code"] == "STALE_PARENT" for b in blockers):
                    try:
                        result, database = producers.operations_preview(
                            normalized["normalized"],
                            code,
                            parent_database=parent_db,
                            parent_revision=parent_revision,
                            reason=settings.get("correction_reason", ""),
                        )
                        database_sha = self._put(connection, database)
                        for reason in result["variance"]["review_reasons"]:
                            target = (
                                normalized["warnings"]
                                if reason == "negative_net_expenses"
                                else blockers
                            )
                            target.append(finding(reason.upper(), reason.replace("_", " ")))
                    except ReviewError as error:
                        blockers.append(finding(error.code, error.message))
            for _, raw in files.values():
                self._put(connection, raw)
            body = {
                **normalized,
                "binding": binding,
                "kind": kind,
                "settings": settings,
                "item": item,
                "parent_report": parent,
                "producer_identity": code,
                "result": result,
                "database_sha256": database_sha,
                "created_at": now(),
            }
            sha = self._put(connection, encode(body))
            connection.execute("INSERT INTO drafts VALUES (?,?,?)", (draft_id, sha, item))
            self._index_draft(connection, draft_id, body)
            connection.execute(
                "INSERT INTO heads VALUES (?,?) ON CONFLICT(item) DO UPDATE "
                "SET draft=excluded.draft",
                (item, draft_id),
            )
            return self._view(connection, draft_id)

    def _ensure_session(self):
        if producers.producer_identity() != self._session_identity:
            refuse(
                "STALE_PRODUCER",
                "Installed code changed. Close and restart review, then prepare a fresh draft.",
            )

    def _view(self, connection, draft_id):
        draft = self._draft(connection, draft_id)
        execution = connection.execute(
            "SELECT body_sha FROM executions WHERE draft=?", (draft_id,)
        ).fetchone()
        result = draft["result"]
        approval = None
        if execution:
            saved = decode(self._blob(connection, execution[0]))
            result, approval = saved["result"], saved["approval"]
            self._verify_approval(connection, approval, saved["approval_payload"])
        issued = connection.execute("SELECT id FROM reports WHERE draft=?", (draft_id,)).fetchone()
        phase = "execute" if draft["kind"] == "acquisition" and not execution else "issue"
        review = {
            "contract_version": CONTRACT,
            "draft_id": draft_id,
            "action": phase,
            "result_sha256": identity(result),
            "execution_approval": approval,
            "producer_identity": draft["producer_identity"],
        }
        active = connection.execute(
            "SELECT draft FROM heads WHERE item=?", (draft["item"],)
        ).fetchone()
        status = (
            "issued"
            if issued
            else "blocked"
            if draft["blockers"]
            else "awaiting_execution_review"
            if phase == "execute"
            else "awaiting_report_review"
        )
        return {
            **draft,
            "id": draft_id,
            "status": status,
            "result": result,
            "review_payload": review,
            "review_sha256": identity(review),
            "active": bool(active and active[0] == draft_id),
            "report_id": issued[0] if issued else None,
        }

    def get(self, draft_id):
        with self._connect() as connection:
            value = self._view(connection, draft_id)
        value["producer_current"] = producers.producer_identity() == value["producer_identity"]
        return value

    @staticmethod
    def _history_bounds(offset, limit):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 101:
            refuse("INVALID_INPUT", "Use a nonnegative history offset and a bounded page size.")

    def list_drafts(self, *, offset=0, limit=100):
        self._history_bounds(offset, limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT d.id,i.kind,i.subject,i.period, "
                "CASE WHEN r.id IS NOT NULL THEN 'issued' "
                "WHEN i.blocked THEN 'blocked' "
                "WHEN i.kind='acquisition' AND e.draft IS NULL THEN 'awaiting_execution_review' "
                "ELSE 'awaiting_report_review' END, h.draft=d.id, r.id "
                "FROM drafts d JOIN draft_index i ON i.id=d.id "
                "LEFT JOIN reports r ON r.draft=d.id "
                "LEFT JOIN executions e ON e.draft=d.id "
                "LEFT JOIN heads h ON h.item=d.item "
                "ORDER BY d.rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [
                {
                    "id": row[0],
                    "kind": row[1],
                    "subject": row[2],
                    "period": row[3],
                    "status": row[4],
                    "active": bool(row[5]),
                    "report_id": row[6],
                }
                for row in rows
            ]

    def _approval(self, connection, payload, reviewer, note):
        from plat_harness import contracts

        record = {
            "approval_id": "local-" + identity({"payload": payload, "reviewer": reviewer}),
            "actor_id": reviewer,
            "actor_type": "human",
            "approved_at": now(),
            "reason": note,
            "record_locator": "local-workspace",
            "payload_sha256": contracts.canonical_sha256(payload),
        }
        sha = self._put(connection, encode(record))
        connection.execute(
            "INSERT INTO approvals VALUES (?,?,?,?)",
            (record["approval_id"], sha, record["payload_sha256"], reviewer),
        )
        self._verify_approval(connection, record, payload)
        return record

    def _verify_approval(self, connection, record, payload):
        from plat_harness import contracts

        row = connection.execute(
            "SELECT body_sha,payload_sha,actor FROM approvals WHERE id=?", (record["approval_id"],)
        ).fetchone()
        if not row or decode(self._blob(connection, row[0])) != record:
            refuse("APPROVAL_REQUIRED", "Human decision is absent from the local authority log.")
        registry = {
            record["approval_id"]: {
                "actor_id": row[2],
                "payload_sha256": row[1],
                "approval_sha256": row[0],
            }
        }
        try:
            contracts._approval(record, payload, registry)
        except Exception:
            refuse("STALE_REVIEW", "Approval no longer matches the reviewed content.")

    def decide(self, action, draft_id, review_sha256, *, reviewer, note, confirmed):
        """Internal browser handler entry; never registered as a CLI or MCP tool."""
        if action not in {"execute", "issue"}:
            refuse("INVALID_ACTION", "Choose execution review or report review.")
        reviewer = text(reviewer, "reviewer", limit=120)
        note = text(note, "review notes")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            draft = self._view(connection, draft_id)
            if confirmed is not True:
                refuse(
                    "HUMAN_REVIEW_REQUIRED",
                    "A reviewer must explicitly confirm this decision.",
                )
            # A retry of an already completed action may return its immutable
            # result, but can never turn changed content into a second decision.
            if draft["report_id"] and action == "issue":
                report = self._report(connection, draft["report_id"])
                if report["review_sha256"] != review_sha256:
                    refuse("STALE_REVIEW", "The submitted review is for different content.")
                return draft
            if action == "execute" and draft["result"] is not None:
                prior = self._record(connection, "executions", draft_id, "draft")
                if identity(prior["approval_payload"]) != review_sha256:
                    refuse("STALE_REVIEW", "The submitted review is for different content.")
                return draft
            if not draft["active"]:
                refuse("STALE_DRAFT", "Another draft replaced this one. Review the active draft.")
            if draft["blockers"]:
                refuse("REVIEW_BLOCKED", "Resolve every blocker and prepare a new draft.")
            if draft["kind"] == "acquisition" and action == "issue" and draft["result"] is None:
                refuse(
                    "EXECUTION_REQUIRED",
                    "Authorize and inspect the calculations before freezing a thesis.",
                )
            if (
                action != draft["review_payload"]["action"]
                or review_sha256 != draft["review_sha256"]
            ):
                refuse(
                    "STALE_REVIEW", "The draft or calculation changed; review the current content."
                )
            self._ensure_session()
            producers.ensure_identity(draft["producer_identity"])
            if action == "issue":
                current = self._latest(connection, draft["item"])
                if draft["kind"] == "acquisition" and current:
                    refuse(
                        "ORIGINAL_THESIS_EXISTS",
                        "The original thesis is already frozen and cannot be replaced.",
                    )
                if draft["kind"] == "operations" and current != draft["parent_report"]:
                    refuse(
                        "STALE_PARENT",
                        "A newer operating report exists. Prepare a correction to it.",
                    )
            approval = self._approval(connection, draft["review_payload"], reviewer, note)
            if action == "execute":
                result = producers.acquisition_run(
                    draft["normalized"], draft["settings"], draft["producer_identity"]
                )
                body = {
                    "result": result,
                    "approval": approval,
                    "approval_payload": draft["review_payload"],
                }
                sha = self._put(connection, encode(body))
                connection.execute("INSERT INTO executions VALUES (?,?)", (draft_id, sha))
            else:
                result = draft["result"]
                database_sha = None
                approvals = []
                if draft["kind"] == "operations":
                    result, database = producers.operations_issue(
                        self._blob(connection, draft["database_sha256"]),
                        result,
                        draft["producer_identity"],
                    )
                    database_sha = self._put(connection, database)
                else:
                    execution = self._record(connection, "executions", draft_id, "draft")
                    approvals.append(
                        {"record": execution["approval"], "payload": execution["approval_payload"]}
                    )
                approvals.append({"record": approval, "payload": draft["review_payload"]})
                report = {
                    "contract_version": CONTRACT,
                    "status": "reviewed_local_draft",
                    "data_class": draft["settings"]["data_class"],
                    "certified": False,
                    "kind": draft["kind"],
                    "item": draft["item"],
                    "draft_id": draft_id,
                    "review_sha256": review_sha256,
                    "subject": draft["subject"],
                    "period": draft["period"],
                    "parent_report": draft["parent_report"],
                    "issued_at": now(),
                    "sources": draft["sources"],
                    "normalized": draft["normalized"],
                    "mappings": draft["mappings"],
                    "policy": draft["settings"],
                    "producer_identity": draft["producer_identity"],
                    "approvals": approvals,
                    "warnings": draft["warnings"],
                    "result": result,
                    "database_sha256": database_sha,
                }
                report_id = self._put(connection, encode(report))
                connection.execute(
                    "INSERT INTO reports VALUES (?,?,?,?,?,?)",
                    (
                        report_id,
                        draft_id,
                        draft["item"],
                        draft["parent_report"],
                        report_id,
                        report["issued_at"],
                    ),
                )
            return self._view(connection, draft_id)

    def _report(self, connection, report_id):
        report = self._record(connection, "reports", report_id)
        if identity(report) != report_id:
            refuse("INTEGRITY_ERROR", "Issued report identity changed.")
        for approval in report["approvals"]:
            self._verify_approval(connection, approval["record"], approval["payload"])
        for source in report["sources"].values():
            self._blob(connection, source["sha256"])
        if report["database_sha256"]:
            self._blob(connection, report["database_sha256"])
        return report

    def report(self, report_id):
        with self._connect() as connection:
            return self._report(connection, report_id)

    def list_reports(self, *, offset=0, limit=100):
        self._history_bounds(offset, limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT r.id,i.kind,i.subject,i.period,r.parent,r.created_at "
                "FROM reports r JOIN draft_index i ON i.id=r.draft "
                "ORDER BY r.rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [
                {
                    "id": row[0],
                    "kind": row[1],
                    "subject": row[2],
                    "period": row[3],
                    "parent_report": row[4],
                    "issued_at": row[5],
                }
                for row in rows
            ]

    def source(self, sha):
        with self._connect() as connection:
            # Only source blobs referenced by a draft are downloadable here.
            row = connection.execute(
                "SELECT draft,filename FROM source_index WHERE sha=? ORDER BY rowid LIMIT 1",
                (sha,),
            ).fetchone()
            if row:
                draft = self._draft(connection, row[0])
                if not any(
                    s["sha256"] == sha and s["filename"] == row[1]
                    for s in draft["sources"].values()
                ):
                    refuse("INTEGRITY_ERROR", "Source index does not match its retained draft.")
                return row[1], self._blob(connection, sha)
        refuse("NOT_FOUND", "Source is not part of this workspace.")
