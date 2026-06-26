#!/usr/bin/env python3
"""Shared executable contract for start-work scripts."""

from __future__ import annotations

import re

RUN_STATUS_ORDER = [
    "init",
    "manager_work_order",
    "developer_running",
    "developer_done",
    "main_integration_check",
    "reviewer_running",
    "review_done",
    "fix_required",
    "developer_fix_running",
    "main_fixing",
    "accepted",
    "blocked",
    "final_delivery",
]

RUN_STATUSES = set(RUN_STATUS_ORDER)

NORMAL_STATUS_FLOW = [
    "init",
    "manager_work_order",
    "developer_running",
    "developer_done",
    "main_integration_check",
    "reviewer_running",
    "review_done",
    "accepted",
    "final_delivery",
]

FIX_STATUS_FLOW = [
    "review_done",
    "fix_required",
    ("developer_fix_running", "main_fixing"),
    "main_integration_check",
    "reviewer_running",
]

DIRECT_SEND_STATUSES = {
    "developer_running",
    "reviewer_running",
    "developer_fix_running",
}

ORDERED_STATUS_TRANSITIONS = {
    "init": ["manager_work_order", "blocked"],
    "manager_work_order": ["developer_running", "blocked"],
    "developer_running": ["developer_done", "blocked"],
    "developer_done": ["main_integration_check", "blocked"],
    "main_integration_check": ["reviewer_running", "blocked"],
    "reviewer_running": ["review_done", "blocked"],
    "review_done": ["accepted", "fix_required", "blocked"],
    "fix_required": ["developer_fix_running", "main_fixing", "blocked"],
    "developer_fix_running": ["main_integration_check", "blocked"],
    "main_fixing": ["main_integration_check", "blocked"],
    "accepted": ["final_delivery"],
    "blocked": ["final_delivery"],
    "final_delivery": [],
}

ALLOWED_STATUS_TRANSITIONS = {
    status: set(next_statuses)
    for status, next_statuses in ORDERED_STATUS_TRANSITIONS.items()
}

DIRECT_MANAGER_TARGET = "M"
MANUAL_RELAY_MANAGER_TARGET = "M via recorded callback (manual relay)"


def manager_target(manager_direct: bool) -> str:
    return DIRECT_MANAGER_TARGET if manager_direct else MANUAL_RELAY_MANAGER_TARGET


def required_route_specs(manager_direct: bool) -> list[tuple[str, str, str, str]]:
    target = manager_target(manager_direct)
    return [
        ("M", "D1", "work order ready", "n/a"),
        ("D1", target, "implementation ready", "n/a"),
        ("M", "R1", "review-ready package", "n/a"),
        ("R1", "D1", "blocking findings", "yes"),
        ("D1", target, "fix ready", "n/a"),
        ("R1", target, "accepted or blocked", "n/a"),
    ]


def next_allowed_statuses(status: str) -> list[str]:
    return list(ORDERED_STATUS_TRANSITIONS.get(status, []))


def current_run_status(text: str) -> str:
    match = re.search(r"^Status:\s*(\S+).*$", text, flags=re.MULTILINE)
    return match.group(1) if match else ""
