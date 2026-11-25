# -*- coding: utf-8 -*-
"""密钥读取：环境变量优先，其次是项目根目录的 ``.env``。

所属模块：基础设施（被 scripts 与 app 共用）。

为什么单独成一个模块
-------------------
项目里出现过的密钥有一把把各自的读法：``amap.py`` 自己解析 ``.env``，
``fetch_amap_sport_poi.py`` / ``fetch_amap_toilet_poi.py`` 又各写了一份正则，
``baidu_place.py`` 还认 ``AK.txt``。同一个 Key 三套逻辑，谁都不知道优先级。
本模块把"从哪儿读"收敛成一条规则：

    环境变量  >  项目根 ``.env``  >  项目根 ``.env.txt``

环境变量优先，是为了让临时会话 / CI / 别人的机器能覆盖仓库里的 ``.env``，
而不用改动或覆盖那个文件。

安全约定（本仓库强制，见 ``docs/过程/密钥与安全.md``）
----------------------------------------------------
1. 密钥值只在内存里流转：**不打印、不写日志、不进异常消息、不进 API 响应**；
2. 需要确认"到底配没配"时用 :func:`check` / :func:`describe`，它们只输出
   来源与掩码（``…abcd``），不输出值；
3. 异常消息里只出现**变量名**，不出现值；
4. 任何要落盘的日志如果可能含 URL（高德 URL 带 ``key=``），先过 :func:`redact`。

命令行
------
    # 在仓库根目录，看所有已知密钥是否就绪（只输出掩码）
    .\\.venv\\Scripts\\python.exe -m app.secrets check

    # 只看某一个；--json 供脚本消费
    .\\.venv\\Scripts\\python.exe -m app.secrets check GAODE_KEY --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from . import paths

# 依次尝试的本地文件（越靠前优先级越高）
ENV_FILES = (".env", ".env.txt")

# 已知密钥：规范名 -> 可接受的变量名（按优先级）
KNOWN_KEYS: dict[str, tuple[str, ...]] = {
    "GAODE_KEY": ("AMAP_WEB_KEY", "GAODE_KEY", "AMAP_KEY"),
    "BAIDU_SERVER_AK": ("BAIDU_SERVER_AK", "BAIDU_AK"),
    "TIANDITU_KEY": ("TIANDITU_KEY",),
    "AQICN_TOKEN": ("AQICN_TOKEN",),
}

SOURCE_ENV = "环境变量"
SOURCE_FILE = "文件"
SOURCE_MISSING = "未配置"


class SecretMissing(RuntimeError):
    """需要的密钥没有配置。

    消息里只有变量名和配置方法，**不含任何值**，可以安全地展示给用户或写进日志。
    """


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    """读取项目根目录的 ``.env`` / ``.env.txt``，只做最简单的 ``KEY=VALUE`` 解析。

    没有引入 python-dotenv：少一个依赖，行为也更可预期。支持
    ``export KEY=VALUE`` 前缀、值两侧的引号、``#`` 整行注释。
    文件不存在或读不了时返回空字典；进程启动后修改文件需要重启才生效。
    """
    values: dict[str, str] = {}
    # 先读 .env.txt 再读 .env，让 .env 覆盖同名项
    for name in reversed(ENV_FILES):
        try:
            text = (paths.PROJECT / name).read_text(encoding="utf-8-sig")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
    return values


def get(*names: str, default: str = "") -> str:
    """按优先级返回第一个非空值：先环境变量，再 ``.env``。

    ``names`` 可以写多个候选名，第一个非空的生效（例如
    ``get("AMAP_WEB_KEY", "GAODE_KEY", "AMAP_KEY")``）。
    """
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    env = _dotenv()
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return default


def require(*names: str, hint: str = "") -> str:
    """同 :func:`get`，但没有值时抛 :class:`SecretMissing`。

    ``hint`` 追加一句"去哪儿拿"的提示（例如申请地址），不会回显任何密钥值。
    """
    value = get(*names)
    if value:
        return value
    if len(names) == 1:
        where = names[0]
    else:
        where = " / ".join(names)
    message = (
        f"缺少密钥 {where}：请设置同名环境变量，"
        f"或在项目根目录 .env 里写一行 {names[0]}=<你的Key>"
    )
    if hint:
        message += f"（{hint}）"
    raise SecretMissing(message)


def source_of(*names: str) -> tuple[str, str]:
    """返回 ``(来源, 命中的变量名)``，来源是 ``环境变量`` / ``文件`` / ``未配置``。

    只报告"从哪儿读到的"，返回值本身由调用方决定要不要用；
    **不要把返回值直接拼进消息**，要展示就用 :func:`mask`。
    """
    value_name, source = _locate(*names)
    if value_name and source:
        return source, value_name
    return SOURCE_MISSING, ""


def _locate(*names: str) -> tuple[str, str]:
    for name in names:
        if os.environ.get(name, "").strip():
            return name, SOURCE_ENV
    env = _dotenv()
    for name in names:
        if (env.get(name) or "").strip():
            return name, SOURCE_FILE
    return "", ""


# ---------------------------------------------------------------------------
# 掩码与脱敏
# ---------------------------------------------------------------------------

def mask(value: str) -> str:
    """把密钥变成可安全展示的字符串。

    形如 ``已设置（32 位，末 4 位 …a1b2）``。短于 12 位时连末 4 位也不给，
    避免把本来就很短的凭据整个暴露出来。
    """
    value = (value or "").strip()
    if not value:
        return "未设置"
    if len(value) < 12:
        return f"已设置（{len(value)} 位，过短，不显示）"
    return f"已设置（{len(value)} 位，末 4 位 …{value[-4:]})"


def redact(text: str, *names: str) -> str:
    """把文本里出现的密钥值替换成 ``***``，用于日志/异常/URL。

    不传 ``names`` 时按 :data:`KNOWN_KEYS` 里所有候选名逐个替换。
    """
    if not text:
        return text
    candidates: list[str] = []
    if names:
        candidates.extend(names)
    else:
        for aliases in KNOWN_KEYS.values():
            candidates.extend(aliases)
    secrets_found = [get(name) for name in candidates]
    for secret in secrets_found:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "***")
    return text


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def check(names: list[str] | None = None) -> list[dict[str, str]]:
    """检查密钥是否就绪，返回可安全打印的记录列表。

    每条记录只有：``name``（规范名）、``source``（环境变量/文件/未配置）、
    ``masked``（掩码）。**不含值本身。**
    """
    records: list[dict[str, str]] = []
    for canonical in names or list(KNOWN_KEYS):
        aliases = KNOWN_KEYS.get(canonical, (canonical,))
        source, hit = source_of(*aliases)
        records.append(
            {
                "name": canonical,
                "source": source if source != SOURCE_MISSING else SOURCE_MISSING,
                "masked": mask(get(*aliases)),
                "aliases": " / ".join(aliases),
            }
        )
    return records


def describe(names: list[str] | None = None) -> str:
    """人类可读的就绪报告（每行一把钥匙，只有掩码与来源）。"""
    lines = ["密钥就绪情况（只显示掩码，不显示值）："]
    for record in check(names):
        state = f"[{record['source']}]" if record["source"] != SOURCE_MISSING else "[未配置]"
        lines.append(f"  {record['name']:<16} {state:<12} {record['masked']}")
    lines.append("")
    lines.append("提示：环境变量优先于 .env；文件位置 = 项目根目录 .env / .env.txt")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.secrets",
        description="检查密钥是否配置（只输出掩码，不输出值）",
    )
    parser.add_argument("action", nargs="?", default="check", choices=["check"])
    parser.add_argument("names", nargs="*", help="只看这些规范名，默认全部")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    unknown = [n for n in args.names if n not in KNOWN_KEYS]
    if unknown:
        parser.error(f"未知密钥名：{', '.join(unknown)}；可选：{', '.join(KNOWN_KEYS)}")

    records = check(args.names or None)
    if args.json:
        print(json.dumps({"keys": records}, ensure_ascii=False, indent=2))
    else:
        print(describe(args.names or None))
    return 0 if all(r["source"] != SOURCE_MISSING for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
