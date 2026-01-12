from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrisisResult:
    # 历史字段名保留：在本项目已改为 ACGN 资讯 Agent 后，这里用作“合规拦截”结果。
    # is_crisis=True 表示命中“盗版/破解/侵权资源”请求，需要拒绝并给出安全替代方案。
    is_crisis: bool
    matched: list[str]


_STRONG_SIGNALS = [
    # 明确指向盗版下载/破解/绕过付费
    "下载",
    "网盘",
    "百度云",
    "蓝奏",
    "磁力",
    "种子",
    "torrent",
    "bt",
    "破解",
    "crack",
    "激活码",
    "序列号",
    "解压密码",
    "直链",
]

_WEAK_SIGNALS = [
    # 语义较泛：单独出现不一定违规，但与强信号同时出现通常表示在要盗版/破解
    "资源",
    "免安装",
    "全CG",
    "补丁",
    "汉化补丁",
]


def detect_crisis(text: str) -> CrisisResult:
    t = (text or "").strip()
    strong = [kw for kw in _STRONG_SIGNALS if kw in t]
    weak = [kw for kw in _WEAK_SIGNALS if kw in t]

    # 只有当命中强信号，或“资源类弱信号 + 明确下载语义”时才拦截
    is_blocked = bool(strong)
    if not is_blocked and weak:
        if any(k in t for k in ["给个", "求", "发我", "链接", "link", "在哪下", "哪里下", "下载"]) :
            is_blocked = True

    matched = strong + weak
    return CrisisResult(is_crisis=is_blocked, matched=matched)
