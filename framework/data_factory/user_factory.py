"""用户工厂：注册 + 登录 + Token 绑定。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from framework.clients.base_client import SystemClient
from framework.observability.allure_ext import allure, attach_json


@dataclass
class User:
    """一个测试用户：凭据 + account_id + 已绑定 token 的专属 client。"""

    username: str
    password: str
    account_id: int | None = None
    token: str | None = None
    client: SystemClient | None = field(default=None, repr=False)

    def auth_client(self, base_url: str) -> SystemClient:
        """返回已认证的独立 client（不影响其他用例的登录态）。"""
        return SystemClient(base_url, token=self.token)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None


def unique_username(prefix: str = "t") -> str:
    """生成唯一用户名（避免注册重复 & 并发冲突）。"""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def unique_password() -> str:
    return "Test#" + uuid.uuid4().hex[:8]


def register_and_login(base_url: str, prefix: str = "u") -> User:
    """注册 + 登录，返回完整 User。注册失败（如限流）时抛出可读错误。"""
    username = unique_username(prefix)
    password = unique_password()

    with allure.step(f"测试数据工厂：注册并登录用户 {username}"):
        anon = SystemClient(base_url)
        try:
            anon.account.register(username, password)
        except AssertionError as e:
            raise AssertionError(
                f"\n[工厂] 注册用户失败（可能触发注册限流 5次/小时/IP）\n"
                f"[缓解] 运行 make clean-ratelimit 清除限流后重试\n[详情] {e}"
            )
        finally:
            anon.close()

        c = SystemClient(base_url)
        data = c.account.login(username, password)
        c.set_token(data["token"])  # 绑定 token，后续请求自动携带 Authorization

    # 附件只放非敏感信息：密码 / token 不进报告
    attach_json(
        "[工厂] 新建用户",
        {"username": username, "account_id": data.get("account_id")},
    )
    return User(
        username=username,
        password=password,
        account_id=data.get("account_id"),
        token=data.get("token"),
        client=c,
    )
