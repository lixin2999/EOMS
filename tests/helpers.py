"""测试辅助：文件上传与流程审批驱动。"""

from __future__ import annotations

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5b0000000049454e44ae426082"
)


def upload_png(client, headers, name: str = "file.png") -> int:
    response = client.post(
        "/api/v1/files/upload",
        files={"file": (name, PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def pending_task(client, headers, instance_id: int) -> dict | None:
    response = client.get(
        "/api/v1/workflow/tasks",
        params={"status": "PENDING", "mine": "true", "page": 1, "page_size": 100},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    for item in response.json()["data"]["items"]:
        if int(item.get("instance_id") or 0) == instance_id:
            return item
    return None


def approve_instance(client, headers_list, instance_id: int, *, max_rounds: int = 12) -> int:
    """轮流尝试审批人，直到实例不再有待办任务；返回处理的任务数。"""
    handled = 0
    for _ in range(max_rounds):
        progressed = False
        for headers in headers_list:
            task = pending_task(client, headers, instance_id)
            if task is None:
                continue
            acted = client.post(
                f"/api/v1/workflow/instances/{instance_id}/actions",
                json={"action": "APPROVE", "task_id": task["id"], "comment": "同意"},
                headers=headers,
            )
            assert acted.status_code == 200, acted.text
            handled += 1
            progressed = True
            break
        if not progressed:
            break
    return handled


def expense_payload(project_id: int, remark: str, amount: str = "100.00") -> dict:
    return {
        "project_id": project_id,
        "type": "TRAVEL",
        "items": [
            {
                "category": "TRAVEL",
                "amount": amount,
                "occur_date": "2026-12-10",
                "description": remark,
            }
        ],
        "remark": remark,
    }
