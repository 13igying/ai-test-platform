"""Allure 轻封装：装了 allure-pytest 用官方对象，没装自动降级为 no-op。

为什么要这一层（面试可讲）：
- 测试套件希望保持轻依赖（README 承诺 `pip install pytest requests` 就能跑），
  Allure 属于"报告呈现增强项"，不应成为硬依赖；
- 全项目统一 `from framework.observability.allure_ext import allure`，
  用法与官方 allure 完全一致（feature/story/severity/step/attach），
  环境里装了 allure-pytest 时透传的就是官方对象，行为零差异。

对应 Allure 五步法：
- 第一步 安装插件：pip install allure-pytest（pytest-allure-adaptor 已废弃）
- 第二步 用例装饰器：feature（功能模块）/ story（故事）/ severity（优先级）
- 第三步 关键步骤与附件：step（步骤日志）/ attach（请求响应、截图等附件）
- 第四步 执行用例生成 JSON：pytest --alluredir=./report
- 第五步 生成 HTML：allure generate ./report -o ./html --clean
"""
from __future__ import annotations

import json
from typing import Any

try:  # 第一步：安装插件后 import 成功，直接用官方 allure
    import allure

    HAS_ALLURE = True
except ImportError:  # pragma: no cover —— 仅在未安装 allure 的极简环境生效
    HAS_ALLURE = False

    class _NoopAttachmentType:
        """官方 attachment_type 的占位（属性访问不报错即可）。"""

        TEXT = "text"
        JSON = "json"
        HTML = "html"
        PNG = "png"
        XML = "xml"

    class _NoopAllure:
        """官方 allure 的 no-op 影子：装饰器原样返回，step 空上下文，attach 丢弃。"""

        attachment_type = _NoopAttachmentType()

        @staticmethod
        def _deco(*_args, **_kwargs):
            def wrapper(fn):
                return fn

            return wrapper

        # 第二步：类/用例装饰器
        epic = feature = story = severity = label = tag = id_ = link = _deco
        title = description = description_html = _deco

        @staticmethod
        def step(title_or_fn=None, *args, **kwargs):
            """兼容两种用法：with allure.step("xxx") 上下管理器 / @allure.step 装饰器。"""
            if callable(title_or_fn):  # 装饰器用法：原样返回函数
                return title_or_fn

            import contextlib

            @contextlib.contextmanager
            def _null_step():
                yield

            return _null_step()

        # 第三步：附件
        @staticmethod
        def attach(body, name=None, attachment_type=None, extension=None):
            return None

    allure = _NoopAllure()


def attach_json(name: str, payload: Any) -> None:
    """第三步实现：把请求/响应等对象以 JSON 附件挂到报告节点上。"""
    if payload is None:
        payload = {}
    try:
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        body = repr(payload)
    allure.attach(body, name=name, attachment_type=allure.attachment_type.JSON)


def attach_text(name: str, text: str) -> None:
    """第三步实现：把关键步骤日志/文本以 TEXT 附件挂到报告节点上。"""
    allure.attach(str(text), name=name, attachment_type=allure.attachment_type.TEXT)
