"""统一 API Client 层（对应《改进方案》3.1）。

分层设计：
- BaseClient      HTTP 基础能力：base_url/超时/JWT/request_id/脱敏日志/Allure/证据
- AccountAPI 等   业务客户端 Mixin：鉴权、Feed、视频、社交、缺陷平台，各自封装业务端点
- SystemClient    组合全部业务能力（对外名 APIClient 向后兼容）

测试函数只做两件事：准备数据（data_factory）、验证业务行为（断言），
不再复制大量请求代码。
"""
from framework.clients.base_client import (
    APIError,
    APIClient,
    BaseClient,
    SystemClient,
)

__all__ = ["APIError", "APIClient", "BaseClient", "SystemClient"]
