"""流程定义校验、条件路由与版本递增。"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import select

from app.core.errors import BusinessRuleError
from app.db.session import SessionLocal
from app.models.iam import User
from app.models.workflow import WorkflowDefinition
from app.services import workflow_service
from app.workflow.definitions import DEFAULT_DEFINITIONS, validate_definition
from app.workflow.engine import _condition_ok


@pytest.mark.parametrize("code", sorted(DEFAULT_DEFINITIONS))
def test_builtin_definitions_are_valid(code):
    validate_definition(DEFAULT_DEFINITIONS[code]["nodes_json"])


def _base_nodes() -> dict:
    return copy.deepcopy(DEFAULT_DEFINITIONS["EXPENSE"]["nodes_json"])


def test_missing_end_node_rejected():
    nodes = _base_nodes()
    nodes["nodes"] = nodes["nodes"][:-1]
    with pytest.raises(BusinessRuleError):
        validate_definition(nodes)


def test_duplicate_node_code_rejected():
    nodes = _base_nodes()
    nodes["nodes"][1]["code"] = "START"
    with pytest.raises(BusinessRuleError):
        validate_definition(nodes)


def test_invalid_assignee_rejected():
    nodes = _base_nodes()
    nodes["nodes"][1]["assignee"] = {"type": "SQL"}
    with pytest.raises(BusinessRuleError):
        validate_definition(nodes)


def test_invalid_mode_rejected():
    nodes = _base_nodes()
    nodes["nodes"][1]["mode"] = "PARALLEL"
    with pytest.raises(BusinessRuleError):
        validate_definition(nodes)


def test_condition_threshold_matrix():
    assert _condition_ok(None, {}) is True
    assert _condition_ok({}, {"amount": "1"}) is True
    assert _condition_ok({"min_amount": 50000}, {"amount": "49999.99"}) is False
    assert _condition_ok({"min_amount": 50000}, {"amount": "50000"}) is True
    assert _condition_ok({"max_amount": 1000}, {"amount": "1000.01"}) is False
    assert _condition_ok({"min_days": 3}, {"days": "2"}) is False
    assert _condition_ok({"min_days": 3}, {"days": "3"}) is True
    assert _condition_ok({"secret_levels": ["SECRET"]}, {"secret_level": "INTERNAL"}) is False
    assert _condition_ok({"categories": ["TRAVEL"]}, {"category": "TRAVEL"}) is True
    assert _condition_ok({"types": ["EXPENSE"]}, {"type": "LEAVE"}) is False


def test_save_definition_increments_version_and_disables_previous():
    code = "TEST_FLOW_E2E"
    nodes = _base_nodes()
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
        first = workflow_service.save_definition(
            db,
            admin,
            {"code": code, "name": "测试流程", "nodes_json": nodes, "enabled": True},
        )
        db.commit()
        second = workflow_service.save_definition(
            db,
            admin,
            {"code": code, "name": "测试流程 V2", "nodes_json": nodes, "enabled": True},
        )
        db.commit()
        assert second.version == first.version + 1

        rows = (
            db.execute(
                select(WorkflowDefinition)
                .where(WorkflowDefinition.code == code)
                .order_by(WorkflowDefinition.version)
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert [row.enabled for row in rows] == [False, True]
        assert rows[-1].version == 2
