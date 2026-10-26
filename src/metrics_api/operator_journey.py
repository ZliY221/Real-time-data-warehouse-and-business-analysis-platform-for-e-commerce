"""Rehearse ecommerce fulfillment operator journeys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FulfillmentOperatorJourney:
    journey_id: str
    inventory_ready: bool
    packing_capacity: int
    carrier_slot_available: bool
    data_age_minutes: int
    cutoff_minutes: int
    priority: int


def rehearse_fulfillment_journeys(
    journeys: list[FulfillmentOperatorJourney],
) -> dict[str, Any]:
    """Guide exactly 100 fulfillment sessions to an explicit next action."""
    if len(journeys) != 100:
        raise ValueError("fulfillment usability rehearsal requires exactly 100 journeys")
    identifiers = [item.journey_id.strip() for item in journeys]
    if any(not value for value in identifiers) or len(identifiers) != len(set(identifiers)):
        raise ValueError("journey ids must be non-empty and unique")

    results = []
    for item in sorted(journeys, key=lambda row: (-row.priority, row.cutoff_minutes,
                                                   row.journey_id)):
        if (item.journey_id != item.journey_id.strip()
                or not 0 <= item.packing_capacity <= 500
                or not 0 <= item.data_age_minutes <= 1440
                or not 0 <= item.cutoff_minutes <= 10080
                or not 1 <= item.priority <= 100):
            raise ValueError("fulfillment operator journey is invalid")
        if item.data_age_minutes > 5:
            status, action = "BLOCKED", "REFRESH_OPERATING_METRICS"
            steps = ["刷新经营指标", "确认最新采集时间", "重新计算履约建议"]
            message = "经营数据超过五分钟未更新，先刷新再做调度决定。"
        elif not item.inventory_ready:
            status, action = "GUIDED", "OPEN_INVENTORY_REBALANCING"
            steps = ["查看节点库存缺口", "生成调拨建议", "人工确认调拨范围"]
            message = "库存未满足履约需求，优先处理节点间再平衡。"
        elif item.packing_capacity == 0:
            status, action = "GUIDED", "ADD_PACKING_CAPACITY"
            steps = ["查看打包工位负载", "补充分班产能", "重新生成波次计划"]
            message = "当前无可用打包能力，需要先恢复工位容量。"
        elif not item.carrier_slot_available:
            status, action = "GUIDED", "OPEN_CARRIER_HANDOFF"
            steps = ["查看可用交接时隙", "调整货件优先级", "重新预约承运容量"]
            message = "缺少可用承运时隙，应先处理交接容量。"
        elif item.cutoff_minutes <= 30:
            status, action = "PRIORITY", "EXPEDITE_HANDOFF"
            steps = ["置顶临近截单货件", "确认打包完成", "复核交接时隙"]
            message = "距离截单不足三十分钟，工作台应进入加急路径。"
        else:
            status, action = "READY", "REVIEW_AND_RELEASE"
            steps = ["核对库存与打包状态", "确认承运时隙", "登记放行结果"]
            message = "当前履约条件完整，可完成放行复核。"
        results.append({
            "journey_id": item.journey_id,
            "priority": item.priority,
            "status": status,
            "primary_action": action,
            "steps": steps,
            "message": message,
            "expected_steps": len(steps),
            "requires_confirmation": action != "REFRESH_OPERATING_METRICS",
        })

    action_counts: dict[str, int] = {}
    for row in results:
        action_counts[row["primary_action"]] = action_counts.get(row["primary_action"], 0) + 1
    return {
        "status": "USABILITY_REHEARSAL_PASSED",
        "journey_count": len(results),
        "ready_count": sum(row["status"] == "READY" for row in results),
        "priority_count": sum(row["status"] == "PRIORITY" for row in results),
        "guided_count": sum(row["status"] in {"BLOCKED", "GUIDED"} for row in results),
        "unresolved_count": sum(not row["steps"] or not row["message"] for row in results),
        "average_expected_steps": round(
            sum(row["expected_steps"] for row in results) / len(results), 2
        ),
        "action_counts": dict(sorted(action_counts.items())),
        "journeys": results,
        "warehouse_commands_started": False,
    }
