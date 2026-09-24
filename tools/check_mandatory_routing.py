#!/usr/bin/env python3
"""Validate the mandatory Guidance -> Coordinator -> UI decision route.

The checker intentionally consumes only the public trace envelope.  It is a
small executable contract for the cross-project boundary: Guidance identifies
the decision, Coordinator creates one revision-bound batch, UI answers every
point, and Coordinator persists the complete response before the worker may
resume.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


AR = re.compile(r"AR-[0-9]{4}\Z")
REVISION = re.compile(r"[0-9]+\Z")


def fail(message: str) -> None:
    raise SystemExit(f"AWG-ROUTING-FAIL: {message}")


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"cannot read {path}: {error}")
    if not isinstance(value, dict):
        fail("trace root must be an object")
    return value


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{field} is required")
    return value


def check(value: dict[str, Any]) -> None:
    if value.get("schema_version") != 1:
        fail("unsupported schema version")
    text(value.get("trace_id"), "trace_id")
    project = text(value.get("project_id"), "project_id")
    revision = value.get("task_revision")
    if not isinstance(revision, int) or revision < 1:
        fail("task_revision must be a positive integer")

    trigger = value.get("trigger")
    if not isinstance(trigger, dict) or trigger.get("owner") != "guidance":
        fail("Guidance trigger is missing")
    if trigger.get("decision_class") not in {"important", "ambiguous"}:
        fail("trigger is not an important or ambiguous decision")
    if trigger.get("task_revision") != revision:
        fail("trigger revision is stale")
    refs = trigger.get("ar_refs")
    if not isinstance(refs, list) or not refs:
        fail("Guidance trigger has no AR references")
    if any(not isinstance(ref, str) or not AR.fullmatch(ref) for ref in refs):
        fail("Guidance trigger contains an invalid AR reference")
    if len(set(refs)) != len(refs):
        fail("Guidance trigger contains duplicate AR references")

    # A conversational answer is never an allowed route for an important
    # decision.  An attempted bypass is evidence of rejection, not an answer.
    attempts = value.get("direct_agent_interface_attempts", [])
    if not isinstance(attempts, list):
        fail("direct_agent_interface_attempts must be a list")
    if attempts:
        fail("direct agent-interface question bypasses UI")

    batch = value.get("batch")
    if not isinstance(batch, dict) or batch.get("owner") != "coordinator":
        fail("Coordinator batch is missing")
    batch_id = text(batch.get("batch_id"), "batch.batch_id")
    if batch.get("task_revision") != revision or batch.get("project_id") != project:
        fail("batch is stale or belongs to another project")
    if batch.get("query_count") != 1:
        fail("independent decisions must use one batched query")
    points = batch.get("points")
    if not isinstance(points, list) or not points:
        fail("batch has no decision points")
    point_keys: set[tuple[str, str]] = set()
    for point in points:
        if not isinstance(point, dict):
            fail("batch point is not an object")
        ar_id = point.get("ar_id")
        point_id = point.get("point_id")
        if not isinstance(ar_id, str) or not AR.fullmatch(ar_id) or ar_id not in refs:
            fail("batch point is not authorized by Guidance")
        if not isinstance(point_id, str) or not point_id:
            fail("batch point identity is missing")
        key = (ar_id, point_id)
        if key in point_keys:
            fail("duplicate batch point")
        point_keys.add(key)
        if point.get("task_revision") != revision:
            fail("batch point is stale")

    ui = value.get("ui_invocation")
    if not isinstance(ui, dict) or ui.get("owner") != "workflow-ui":
        fail("workflow-ui invocation is missing")
    if ui.get("batch_id") != batch_id or ui.get("task_revision") != revision:
        fail("UI invocation is stale or references another batch")
    if ui.get("session_count") != 1:
        fail("exactly one UI session is required")

    response = value.get("response")
    if not isinstance(response, dict) or response.get("owner") != "workflow-ui":
        fail("UI response is missing")
    if response.get("batch_id") != batch_id or response.get("task_revision") != revision:
        fail("UI response is stale or references another batch")
    events = response.get("events")
    if not isinstance(events, list) or len(events) != len(point_keys):
        fail("partial UI response cannot be persisted")
    seen: set[tuple[str, str]] = set()
    event_refs: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            fail("response event is not an object")
        key = (event.get("ar_id"), event.get("point_id"))
        if key not in point_keys or key in seen:
            fail("response event is cross-AR or duplicated")
        if event.get("task_revision") != revision:
            fail("response event is stale")
        if event.get("disposition") not in {"select", "reject", "clarify"}:
            fail("response event has no typed disposition")
        event_ref = event.get("event_ref")
        if not isinstance(event_ref, str) or not event_ref or event_ref in event_refs:
            fail("response event reference is missing or duplicated")
        seen.add(key)
        event_refs.add(event_ref)
    if seen != point_keys:
        fail("response does not cover every batch point")

    persistence = value.get("persistence")
    if not isinstance(persistence, dict) or persistence.get("owner") != "coordinator":
        fail("Coordinator persistence is missing")
    if persistence.get("batch_id") != batch_id or persistence.get("task_revision") != revision:
        fail("persistence is stale or references another batch")
    if persistence.get("event_refs") != sorted(event_refs):
        fail("persistence does not contain the complete response")
    text(persistence.get("coordinator_event_ref"), "persistence.coordinator_event_ref")

    resume = value.get("resume")
    if not isinstance(resume, dict) or resume.get("owner") != "worker":
        fail("worker resume is missing")
    if resume.get("status") != "resumed" or resume.get("task_revision") != revision:
        fail("worker resumed without the persisted current revision")
    if resume.get("coordinator_event_ref") != persistence["coordinator_event_ref"]:
        fail("worker resume is not bound to Coordinator persistence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    check(load(args.trace))
    print(f"AWG-ROUTING-PASS: {args.trace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
