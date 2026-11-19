from __future__ import annotations

from typing import Any

from app.core.errors import BusinessRuleError

DEFAULT_DUE_HOURS = 24


def _approval(
    code: str,
    name: str,
    assignee: dict[str, Any],
    *,
    mode: str = "ANY",
    condition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "type": "APPROVAL",
        "assignee": assignee,
        "mode": mode,
        "condition": condition or {},
    }


def _flow(nodes: list[dict[str, Any]], *, reject_mode: str = "INITIATOR") -> dict[str, Any]:
    return {
        "settings": {
            "reject_mode": reject_mode,
            "allow_withdraw": True,
            "due_hours": DEFAULT_DUE_HOURS,
            "allow_transfer": True,
            "allow_add_sign": True,
        },
        "nodes": nodes,
    }


DEFAULT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "EXPENSE": {
        "name": "费用报销审批（四级/阈值升级）",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                _approval(
                    "APPROVER_3",
                    "董事",
                    {"type": "ROLE", "value": "DIRECTOR"},
                    condition={"min_amount": 50000},
                ),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
    "LEAVE": {
        "name": "请假审批",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                _approval(
                    "APPROVER_3",
                    "董事",
                    {"type": "ROLE", "value": "DIRECTOR"},
                    condition={"min_days": 5},
                ),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
    "DOCUMENT": {
        "name": "文件（用印/发文/制度）审批",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                _approval(
                    "APPROVER_3",
                    "董事",
                    {"type": "ROLE", "value": "DIRECTOR"},
                    condition={"secret_levels": ["SECRET"]},
                ),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
    "PROJECT_INITIATION": {
        "name": "项目立项审批",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                _approval("APPROVER_3", "董事", {"type": "ROLE", "value": "DIRECTOR"}),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
    "PROJECT_CHANGE": {
        "name": "项目变更审批",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                _approval("APPROVER_3", "董事", {"type": "ROLE", "value": "DIRECTOR"}),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
    "PROJECT_ACCEPTANCE": {
        "name": "项目验收审批",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
    "VENDOR_ONBOARD": {
        "name": "供应商准入审批",
        "nodes_json": _flow(
            [
                {"code": "START", "name": "发起人提交", "type": "START"},
                _approval("APPROVER_1", "部门负责人", {"type": "DEPT_LEADER"}),
                _approval("APPROVER_2", "部门经理", {"type": "ROLE", "value": "MANAGER"}),
                {"code": "END", "name": "归档", "type": "END"},
            ]
        ),
    },
}


def validate_definition(nodes_json: dict[str, Any]) -> None:
    nodes = (nodes_json or {}).get("nodes")
    if not isinstance(nodes, list) or len(nodes) < 2:
        raise BusinessRuleError("流程定义至少需要 START 与 END 节点")
    codes: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not node.get("code") or not node.get("name"):
            raise BusinessRuleError("流程节点缺少 code/name")
        if node["code"] in codes:
            raise BusinessRuleError(f"流程节点编码重复：{node['code']}")
        codes.add(node["code"])
        node_type = node.get("type")
        if node_type not in {"START", "APPROVAL", "CC", "END"}:
            raise BusinessRuleError(f"流程节点类型非法：{node_type}")
        if node_type == "APPROVAL":
            assignee = node.get("assignee") or {}
            if assignee.get("type") not in {"USER", "ROLE", "DEPT_LEADER", "DEPT_MANAGER", "PM", "SUPERIOR", "CREATOR"}:
                raise BusinessRuleError(f"节点 {node['code']} 审批人配置非法")
            if assignee.get("type") in {"USER", "ROLE"} and not assignee.get("value"):
                raise BusinessRuleError(f"节点 {node['code']} 缺少审批人参数")
            if node.get("mode", "ANY") not in {"ANY", "ALL"}:
                raise BusinessRuleError(f"节点 {node['code']} 审批模式非法")
    if nodes[0].get("type") != "START":
        raise BusinessRuleError("流程首个节点必须是 START")
    if nodes[-1].get("type") != "END":
        raise BusinessRuleError("流程最后一个节点必须是 END")
