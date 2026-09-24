#!/usr/bin/env python3
"""Validate the revision-bound multi-AR UI batch and document projections.

The Coordinator owns this envelope.  Both clients receive the same complete
batch; neither client may reconstruct points or anchors from a partial view.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

AR = re.compile(r"AR-[0-9]{4}\Z")
ANCHOR = re.compile(r"#[a-z0-9][a-z0-9-]*\Z")


def fail(message: str) -> None:
    raise SystemExit(f"AWUI-BATCH-FAIL: {message}")


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"cannot read {path}: {error}")
    if not isinstance(value, dict):
        fail("envelope root must be an object")
    return value


def required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{field} is required")
    return value


def check(value: dict[str, Any]) -> None:
    if value.get("schema_version") != 1:
        fail("unsupported schema version")
    project = required_text(value.get("project_id"), "project_id")
    batch_id = required_text(value.get("batch_id"), "batch_id")
    revision = value.get("task_revision")
    if not isinstance(revision, int) or revision < 1:
        fail("task_revision must be a positive integer")
    if value.get("owner") != "coordinator":
        fail("Coordinator must own the batch")
    graph = value.get("structure_graph")
    if not isinstance(graph, dict) or graph.get("owner") != "coordinator":
        fail("authoritative structure graph is missing")
    if graph.get("task_revision") != revision or graph.get("project_id") != project:
        fail("structure graph is stale or belongs to another project")
    required_text(graph.get("digest"), "structure_graph.digest")

    points = value.get("points")
    if not isinstance(points, list) or not points:
        fail("batch must contain at least one decision point")
    keys: set[tuple[str, str]] = set()
    for point in points:
        if not isinstance(point, dict):
            fail("decision point is not an object")
        ar_id = point.get("ar_id")
        decision_id = point.get("decision_id")
        if not isinstance(ar_id, str) or not AR.fullmatch(ar_id):
            fail("decision point has invalid ar_id")
        if not isinstance(decision_id, str) or not decision_id:
            fail("decision point has no decision_id")
        key = (ar_id, decision_id)
        if key in keys:
            fail("duplicate decision point")
        keys.add(key)
        if point.get("task_revision") != revision:
            fail("decision point is stale")
        dependencies = point.get("dependency_ids")
        if not isinstance(dependencies, list) or any(not isinstance(item, str) or not item for item in dependencies):
            fail("decision point dependencies are invalid")
        proposals = point.get("proposals")
        if not isinstance(proposals, list) or not proposals or len(set(proposals)) != len(proposals):
            fail("decision point proposals are empty or duplicated")
        if any(not isinstance(item, str) or not item for item in proposals):
            fail("decision point proposal identity is invalid")

    projections = value.get("projections")
    if not isinstance(projections, dict):
        fail("document projections are missing")
    anchor_sets: dict[str, dict[tuple[str, str], str]] = {}
    for name in ("design", "workplan"):
        document = projections.get(name)
        if not isinstance(document, dict):
            fail(f"{name} projection is missing")
        if document.get("batch_id") != batch_id or document.get("task_revision") != revision:
            fail(f"{name} projection is stale or references another batch")
        markdown = document.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            fail(f"{name} Markdown is empty")
        anchors = document.get("anchors")
        if not isinstance(anchors, list) or len(anchors) != len(keys):
            fail(f"{name} projection does not cover every point")
        seen: dict[tuple[str, str], str] = {}
        for anchor in anchors:
            if not isinstance(anchor, dict):
                fail(f"{name} anchor is not an object")
            key = (anchor.get("ar_id"), anchor.get("decision_id"))
            if key not in keys or key in seen:
                fail(f"{name} anchor is unknown or duplicated")
            value_anchor = anchor.get("anchor")
            if not isinstance(value_anchor, str) or not ANCHOR.fullmatch(value_anchor):
                fail(f"{name} anchor value is invalid")
            if value_anchor in seen.values():
                fail(f"{name} anchors are not distinct")
            if value_anchor not in markdown:
                fail(f"{name} anchor is absent from Markdown")
            if anchor.get("task_revision") != revision:
                fail(f"{name} anchor is stale")
            seen[key] = value_anchor
        anchor_sets[name] = seen

    clients = value.get("clients")
    if not isinstance(clients, dict):
        fail("client projections are missing")
    for name in ("tui", "gui"):
        client = clients.get(name)
        if not isinstance(client, dict) or client.get("batch_id") != batch_id:
            fail(f"{name} does not consume this batch")
        if client.get("task_revision") != revision:
            fail(f"{name} client is stale")
        if client.get("point_keys") != [list(key) for key in sorted(keys)]:
            fail(f"{name} does not consume every point")
        if client.get("anchors") != {doc: {f"{key[0]}:{key[1]}": anchor for key, anchor in sorted(items.items())} for doc, items in anchor_sets.items()}:
            fail(f"{name} anchor projection differs from authoritative documents")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envelope", type=Path)
    args = parser.parse_args()
    check(load(args.envelope))
    print(f"AWUI-BATCH-PASS: {args.envelope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
