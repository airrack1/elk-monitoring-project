"""Core data model for an engagement.

An Engagement is the unit of work. It owns: metadata, authorization status,
scope, per-checklist-item state, findings, an evidence log, and an append-only
activity log. Everything serializes to plain dicts so storage stays JSON.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .data import checklist_template as tmpl
from .scope import Scope


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


SEVERITIES = ["critical", "high", "medium", "low", "info"]
ITEM_STATES = ["pending", "in_progress", "done", "na"]


@dataclass
class Authorization:
    """Phase 0 authorization record. Active tooling is blocked until granted."""

    signed: bool = False
    authorizing_officer: str = ""
    signed_date: str = ""
    letter_path: str = ""  # path to the offline get-out-of-jail letter
    notes: str = ""

    @property
    def granted(self) -> bool:
        return bool(self.signed and self.authorizing_officer and self.letter_path)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Authorization":
        return cls(**{k: v for k, v in (d or {}).items() if k in cls.__annotations__})


@dataclass
class Finding:
    id: str
    title: str
    severity: str = "info"
    phase: Optional[int] = None
    host: str = ""
    description: str = ""
    cvss: str = ""
    business_impact: str = ""
    remediation: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    false_positive: bool = False
    created: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class EvidenceEntry:
    id: str
    kind: str  # 'command' | 'file' | 'note' | 'screenshot'
    summary: str
    path: str = ""
    item_id: str = ""  # optional link to a checklist item
    finding_id: str = ""
    created: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class Engagement:
    id: str
    name: str
    client: str = ""
    sow_ref: str = ""
    lead_auditor: str = "Aaryon"
    testing_window: str = ""
    created: str = field(default_factory=_now)
    authorization: Authorization = field(default_factory=Authorization)
    scope: Scope = field(default_factory=Scope)
    # item_id -> {"state": str, "note": str, "updated": iso}
    checklist: Dict[str, dict] = field(default_factory=dict)
    qa: Dict[str, bool] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    evidence: List[EvidenceEntry] = field(default_factory=list)
    activity: List[dict] = field(default_factory=list)

    # ---- construction -------------------------------------------------
    @classmethod
    def create(cls, name: str, **kw) -> "Engagement":
        eng = cls(id=_new_id("eng"), name=name, **kw)
        eng._init_checklist()
        eng.log("engagement.created", f"Created engagement '{name}'")
        return eng

    def _init_checklist(self) -> None:
        for _phase, items in tmpl.build_phase_items().items():
            for item_id, _text in items:
                self.checklist.setdefault(item_id, {"state": "pending", "note": "", "updated": _now()})
        for i, _text in enumerate(tmpl.FINAL_QA, start=1):
            self.qa.setdefault(f"qa.{i}", False)

    # ---- activity log -------------------------------------------------
    def log(self, action: str, detail: str = "") -> None:
        self.activity.append({"ts": _now(), "action": action, "detail": detail})

    # ---- checklist ----------------------------------------------------
    def set_item(self, item_id: str, state: str, note: str = "") -> None:
        if state not in ITEM_STATES:
            raise ValueError(f"state must be one of {ITEM_STATES}")
        entry = self.checklist.setdefault(item_id, {"state": "pending", "note": "", "updated": _now()})
        entry["state"] = state
        if note:
            entry["note"] = note
        entry["updated"] = _now()
        self.log("item.update", f"{item_id} -> {state}")

    def phase_progress(self, phase_number: int) -> tuple:
        """Return (done, total, percent) for a phase, counting 'na' as done."""
        items = tmpl.build_phase_items().get(phase_number, [])
        total = len(items)
        if total == 0:
            return (0, 0, 100.0)
        done = sum(
            1 for item_id, _ in items if self.checklist.get(item_id, {}).get("state") in ("done", "na")
        )
        return (done, total, round(100.0 * done / total, 1))

    def phase_complete(self, phase_number: int) -> bool:
        done, total, _ = self.phase_progress(phase_number)
        return total > 0 and done == total

    # ---- findings / evidence -----------------------------------------
    def add_finding(self, title: str, **kw) -> Finding:
        f = Finding(id=_new_id("find"), title=title, **kw)
        self.findings.append(f)
        self.log("finding.add", f"{f.id}: {title} [{f.severity}]")
        return f

    def add_evidence(self, kind: str, summary: str, **kw) -> EvidenceEntry:
        e = EvidenceEntry(id=_new_id("ev"), kind=kind, summary=summary, **kw)
        self.evidence.append(e)
        self.log("evidence.add", f"{e.id}: {summary}")
        return e

    # ---- serialization -----------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": "netaudit.engagement/1",
            "template_version": tmpl.TEMPLATE_VERSION,
            "id": self.id,
            "name": self.name,
            "client": self.client,
            "sow_ref": self.sow_ref,
            "lead_auditor": self.lead_auditor,
            "testing_window": self.testing_window,
            "created": self.created,
            "authorization": self.authorization.to_dict(),
            "scope": self.scope.to_dict(),
            "checklist": self.checklist,
            "qa": self.qa,
            "findings": [f.to_dict() for f in self.findings],
            "evidence": [e.to_dict() for e in self.evidence],
            "activity": self.activity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Engagement":
        eng = cls(
            id=d["id"],
            name=d["name"],
            client=d.get("client", ""),
            sow_ref=d.get("sow_ref", ""),
            lead_auditor=d.get("lead_auditor", "Aaryon"),
            testing_window=d.get("testing_window", ""),
            created=d.get("created", _now()),
            authorization=Authorization.from_dict(d.get("authorization", {})),
            scope=Scope.from_dict(d.get("scope", {})),
            checklist=d.get("checklist", {}),
            qa=d.get("qa", {}),
            findings=[Finding.from_dict(x) for x in d.get("findings", [])],
            evidence=[EvidenceEntry.from_dict(x) for x in d.get("evidence", [])],
            activity=d.get("activity", []),
        )
        eng._init_checklist()  # backfill any items added since creation
        return eng
