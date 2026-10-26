"""Build a bounded fulfillment shift board from rehearsed operator journeys."""

from __future__ import annotations

from typing import Any

from metrics_api.operator_journey import (
    FulfillmentOperatorJourney,
    rehearse_fulfillment_journeys,
)


STATUS_ORDER = {"BLOCKED": 0, "PRIORITY": 1, "GUIDED": 2, "READY": 3}
ACTION_MINUTES = {
    "REFRESH_OPERATING_METRICS": 4,
    "OPEN_INVENTORY_REBALANCING": 12,
    "ADD_PACKING_CAPACITY": 10,
    "OPEN_CARRIER_HANDOFF": 8,
    "EXPEDITE_HANDOFF": 6,
    "REVIEW_AND_RELEASE": 5,
}


def build_fulfillment_shift_board(
    journeys: list[FulfillmentOperatorJourney], *, visible_limit: int = 16
) -> dict[str, Any]:
    """Expose the next safe shift actions without dispatching warehouse commands."""
    if not 1 <= visible_limit <= 25:
        raise ValueError("visible limit must be between 1 and 25")
    rehearsal = rehearse_fulfillment_journeys(journeys)
    ordered = sorted(
        rehearsal["journeys"],
        key=lambda item: (
            STATUS_ORDER[item["status"]],
            -item["priority"],
            item["journey_id"],
        ),
    )
    focus_items = []
    for rank, item in enumerate(ordered[:visible_limit], start=1):
        focus_items.append({
            **item,
            "rank": rank,
            "estimated_minutes": ACTION_MINUTES[item["primary_action"]],
            "resume_key": f"{item['journey_id']}:{item['primary_action']}",
            "lane": {
                "BLOCKED": "数据待刷新",
                "PRIORITY": "临近截单",
                "GUIDED": "资源协调",
                "READY": "放行复核",
            }[item["status"]],
        })
    lane_counts = {
        status.lower(): sum(item["status"] == status for item in ordered)
        for status in STATUS_ORDER
    }
    return {
        "status": "FULFILLMENT_SHIFT_BOARD_READY",
        "journey_count": 100,
        "visible_count": len(focus_items),
        "remaining_count": 100 - len(focus_items),
        "lane_counts": lane_counts,
        "estimated_focus_minutes": sum(item["estimated_minutes"] for item in focus_items),
        "focus_items": focus_items,
        "guidance": "先刷新失效指标，再处理临近截单任务和资源协调事项。",
        "warehouse_commands_started": False,
    }
