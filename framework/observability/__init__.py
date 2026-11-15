"""观测能力：失败证据采集、脱敏、Allure 降级封装、pytest 失败证据插件。"""
from framework.observability.allure_ext import allure, attach_json, attach_text
from framework.observability.evidence import EvidenceStore, store

__all__ = ["allure", "attach_json", "attach_text", "EvidenceStore", "store"]
