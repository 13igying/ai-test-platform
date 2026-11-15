"""缺陷平台域端点封装（对齐 backend/internal/bugtracker/handler.go）。

状态机：open -> fixing -> fixed -> closed；fixed 可被 reporter 打回 open。
权限：assignee 推进修复流程；reporter 关闭 / 回归打回。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.clients.base_client import BaseClient


class BugAPI:
    """缺陷创建 / 状态流转 / 列表查询。"""

    def __init__(self, base: "BaseClient") -> None:
        self._b = base

    def _c(self):
        return self._b if getattr(self, "_b", None) is not None else self

    def create(
        self,
        title: str,
        description: str = "",
        severity: str = "minor",
        assignee_id: int | None = None,
    ) -> dict:
        body: dict = {"title": title, "description": description, "severity": severity}
        if assignee_id is not None:
            body["assignee_id"] = assignee_id
        return self._c().post_ok("/bug/create", body, schema="bug")

    def update_status(self, bug_id: int, status: str) -> dict:
        return self._c().post_ok("/bug/updateStatus", {"bug_id": bug_id, "status": status}, schema="bug")

    def list(self, status: str | None = None, role: str | None = None, limit: int = 50) -> dict:
        body: dict = {"limit": limit}
        if status:
            body["status"] = status
        if role:
            body["role"] = role
        return self._c().post_ok("/bug/list", body, schema="bug_list")
