"""账号域端点封装（对齐 backend/internal/account/handler.go）。

既作为 SystemClient 的 Mixin（平铺方法），也作为子客户端视图
（client.account.xxx）——同一份实现两种用法。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.clients.base_client import BaseClient


class AccountAPI:
    """注册 / 登录 / 刷新 / 登出 / 改名 / 改密。"""

    def __init__(self, base: "BaseClient") -> None:
        self._b = base

    def _c(self):
        """子客户端视图返回 base；作为 Mixin 平铺使用时返回自身。"""
        return self._b if getattr(self, "_b", None) is not None else self

    # ---------- 端点 ----------
    def register(self, username: str, password: str) -> dict:
        return self._c().post_ok(
            "/account/register", {"username": username, "password": password}, schema="register"
        )

    def login(self, username: str, password: str) -> dict:
        """返回 {token, refresh_token, account_id, username}。"""
        return self._c().post_ok(
            "/account/login", {"username": username, "password": password}, schema="login"
        )

    def login_and_bind(self, username: str, password: str) -> dict:
        """登录并把 token 绑定到当前 client。"""
        data = self.login(username, password)
        self._c().set_token(data["token"])
        return data

    def refresh(self, refresh_token: str) -> dict:
        """刷新 access token（响应无 refresh_token 字段，与 login 契约不同）。"""
        return self._c().post_ok("/account/refresh", {"refresh_token": refresh_token})

    def logout(self) -> dict:
        """登出：撤销当前 token（服务端 Redis 黑名单）。"""
        return self._c().post_ok("/account/logout", {})

    def rename(self, new_username: str) -> dict:
        """改名：成功返回新 token（旧 token 仍有效直至过期）。"""
        return self._c().post_ok("/account/rename", {"new_username": new_username})

    def change_password(self, username: str, old_password: str, new_password: str) -> dict:
        """改密：接口无 JWT 中间件，靠旧密码自证身份（路由层公开接口）。"""
        return self._c().post_ok(
            "/account/changePassword",
            {"username": username, "old_password": old_password, "new_password": new_password},
        )

    # ---------- v1 兼容平铺名 ----------
    def login_and_auth(self, username: str, password: str) -> dict:
        return self.login_and_bind(username, password)

    # ---------- 供 AI 白名单/数据工厂使用的原语 ----------
    def find_by_id(self, account_id: int) -> dict:
        return self._c().post_ok("/account/findByID", {"id": account_id})
