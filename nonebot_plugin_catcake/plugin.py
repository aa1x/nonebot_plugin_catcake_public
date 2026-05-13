from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import httpx
from nonebot import get_driver, on_command, on_message, require
from nonebot.adapters import Event, Message
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

from .api import CatcakeApi
from .config import Config


__plugin_meta__ = PluginMetadata(
    name="猫猫糕公开版",
    description="面向 NoneBot 插件市场发布的猫猫糕查询/上传插件。",
    usage=(
        "指令:\n"
        "- 搜索 <服务器> <猫糕名称>\n"
        "- 上传 <UID> <猫糕名称> <猫糕名称> <猫糕名称>\n"
        "- 上传阿基喵利 <UID>\n"
        "- 今日阿基喵利 <服务器>\n"
        "- 收录数量\n"
        "- 设置\n"
        "- cathelp"
    ),
    type="application",
    homepage="https://github.com/aa1x/nonebot_plugin_catcake_public/",
    config=Config,
    supported_adapters=None,
)

config = Config.parse_obj(get_driver().config.dict())
api = CatcakeApi(base_url=config.catcake_api_base, timeout=config.catcake_timeout)

SETTINGS_FILE = store.get_plugin_config_file("user_settings.json")
LOCATION_OPTIONS = [
    "猫爬架旁桌上台灯",
    "吧台上固定电话",
    "车厢上中部沙发",
    "留声机旁盆栽",
    "二楼楼梯旁花坛",
    "帕姆衣架旁椅子",
    "车厢下中部沙发",
]
_SETTING_SESSION_USERS: set[str] = set()


def _map_server(server_raw: str) -> str:
    v = server_raw.strip()
    if v == "1":
        return "官服"
    if v == "2":
        return "B服"
    return v or config.catcake_default_server


def _infer_server_from_uid(uid: str) -> Optional[str]:
    if uid.startswith("1"):
        return "官服"
    if uid.startswith("5"):
        return "B服"
    return None


def _split_args(args: Any) -> List[str]:
    return [x for x in str(args).strip().split() if x]



def _map_error_code_to_text(code: str) -> str:
    mapping = {
        "23505": "记录重复（该服务器本周期已上传）",
        "23514": "数据格式错误（UID/服务器/猫糕或地点不符合要求）",
        "SQLITE_CONSTRAINT_UNIQUE": "记录重复（唯一约束冲突）",
        "SQLITE_CONSTRAINT_CHECK": "数据格式错误（UID/服务器/猫糕或地点不符合要求）",
        "SQLITE_CONSTRAINT_NOTNULL": "数据缺失（必填字段为空）",
        "SQLITE_CONSTRAINT": "数据约束冲突",
    }
    return mapping.get(code.upper(), mapping.get(code, ""))


def _map_d1_error_to_text(message: str) -> str:
    if not message:
        return ""

    normalized = re.sub(r"\s+", " ", message).strip()
    upper_message = normalized.upper()
    if "D1_ERROR" not in upper_message and "SQLITE_" not in upper_message:
        return ""

    if "UNIQUE CONSTRAINT FAILED" in upper_message or "SQLITE_CONSTRAINT_UNIQUE" in upper_message:
        if "CAT_CAKES" in upper_message and "WEEK_START" in upper_message:
            return "记录重复（该服务器本周期已上传）"
        if "DAILY_AJI" in upper_message:
            return "记录重复（今日阿基喵利已上传）"
        return "记录重复（唯一约束冲突）"

    if "CHECK CONSTRAINT FAILED" in upper_message or "SQLITE_CONSTRAINT_CHECK" in upper_message:
        return "数据格式错误（UID/服务器/猫糕或地点不符合要求）"
    if "NOT NULL CONSTRAINT FAILED" in upper_message or "SQLITE_CONSTRAINT_NOTNULL" in upper_message:
        return "数据缺失（必填字段为空）"
    if "FOREIGN KEY CONSTRAINT FAILED" in upper_message or "SQLITE_CONSTRAINT_FOREIGNKEY" in upper_message:
        return "数据关联错误（外键约束冲突）"
    if "SQLITE_CONSTRAINT" in upper_message:
        return "数据约束冲突"
    if "NO SUCH TABLE" in upper_message:
        return "数据库表不存在，请检查D1表结构是否已初始化"
    if "DATABASE IS LOCKED" in upper_message or "SQLITE_BUSY" in upper_message:
        return "数据库繁忙，请稍后再试"

    return ""


def _format_http_error_reason(e: httpx.HTTPStatusError) -> str:
    status = e.response.status_code
    text = (e.response.text or "").strip()
    try:
        payload = e.response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        code = str(payload.get("code", "")).strip()
        message = str(payload.get("message", "")).strip()
        d1_mapped = _map_d1_error_to_text(" ".join(x for x in [message, code] if x))
        if d1_mapped:
            return f"{d1_mapped} (code: {code})" if code else d1_mapped
        if code:
            mapped = _map_error_code_to_text(code)
            if mapped:
                return f"{mapped} (code: {code})"
            if message:
                return f"{message} (code: {code})"
            return f"错误代码 {code}"
        if message:
            return message

    d1_mapped = _map_d1_error_to_text(text)
    if d1_mapped:
        return d1_mapped

    return text[:120] if text else f"HTTP {status}"


def _with_quote(event: Any, text: str) -> str:
    return text


def _load_settings() -> Dict[str, Dict[str, bool]]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(data: Dict[str, Dict[str, bool]]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_user_key(event: Event) -> Optional[str]:
    uid = getattr(event, "user_id", None)
    return str(uid) if uid is not None else None


def _get_user_settings(event: Event) -> Dict[str, bool]:
    key = _get_user_key(event)
    defaults = {"show_location": False, "filter_location": False, "choose_location": False}
    if not key:
        return defaults
    data = _load_settings()
    raw = data.get(key, {})
    return {
        "show_location": bool(raw.get("show_location", False)),
        "filter_location": bool(raw.get("filter_location", False)),
        "choose_location": bool(raw.get("choose_location", False)),
    }


def _set_user_setting(event: Event, key: str, value: bool) -> None:
    user_key = _get_user_key(event)
    if not user_key:
        return
    data = _load_settings()
    row = data.get(user_key, {})
    row[key] = value
    data[user_key] = row
    _save_settings(data)


def _settings_panel(event: Event) -> str:
    s = _get_user_settings(event)
    onoff = lambda v: "开" if v else "关"
    return (
        f"1.搜索时显示地点信息:{onoff(s['show_location'])}\n"
        f"2.搜索时过滤无地点信息的数据:{onoff(s['filter_location'])}\n"
        f"3.上传时选择地点信息:{onoff(s['choose_location'])}\n"
        "您要更改哪一项呢？请发送1/2/3\n"
        "发送 0 退出设置"
    )

search_cmd = on_command("搜索", priority=10, block=True)
upload_cmd = on_command("上传", priority=10, block=True)
upload_aji_cmd = on_command("上传阿基喵利", priority=10, block=True)
daily_cmd = on_command("今日阿基喵利", priority=10, block=True)
count_cmd = on_command("收录数量", priority=10, block=True)
setting_cmd = on_command("设置", priority=10, block=True)
help_cmd = on_command("cathelp", priority=10, block=True)


@setting_cmd.handle()
async def _(event: Event, args: Message = CommandArg()) -> None:
    parts = _split_args(args)
    if not parts:
        key = _get_user_key(event)
        if key:
            _SETTING_SESSION_USERS.add(key)
        await setting_cmd.finish(_with_quote(event, _settings_panel(event)))
    if parts[0] == "0":
        await setting_cmd.finish(_with_quote(event, "已退出设置"))
    mapping = {
        "1": ("show_location", "搜索时显示地点信息"),
        "2": ("filter_location", "搜索时过滤无地点信息的数据"),
        "3": ("choose_location", "上传时选择地点信息"),
    }
    item = mapping.get(parts[0])
    if not item:
        await setting_cmd.finish(_with_quote(event, "请输入1/2/3或0"))
    key, name = item
    old = _get_user_settings(event)[key]
    _set_user_setting(event, key, not old)
    await setting_cmd.finish(_with_quote(event, f"{name}已设置为{'开' if not old else '关'}"))

setting_select_cmd = on_message(priority=9, block=False)


@setting_select_cmd.handle()
async def _(event: Event) -> None:
    key = _get_user_key(event)
    if not key or key not in _SETTING_SESSION_USERS:
        return
    parts = _split_args(getattr(event, "message", ""))
    if len(parts) != 1:
        return
    mapping = {
        "1": ("show_location", "搜索时显示地点信息"),
        "2": ("filter_location", "搜索时过滤无地点信息的数据"),
        "3": ("choose_location", "上传时选择地点信息"),
    }
    if parts[0] == "0":
        _SETTING_SESSION_USERS.discard(key)
        await setting_select_cmd.finish(_with_quote(event, "已退出设置"))
    item = mapping.get(parts[0])
    if not item:
        return
    option_key, name = item
    old = _get_user_settings(event)[option_key]
    _set_user_setting(event, option_key, not old)
    _SETTING_SESSION_USERS.discard(key)
    await setting_select_cmd.finish(_with_quote(event, f"{name}已设置为{'开' if not old else '关'}"))


@search_cmd.handle()
async def _(event: Event, args: Message = CommandArg()) -> None:
    parts = _split_args(args)
    if len(parts) < 2:
        await search_cmd.finish(_with_quote(event, "用法：搜索 <服务器> <猫糕名称>"))

    server = _map_server(parts[0])
    target_cake = parts[1]
    setting = _get_user_settings(event)

    try:
        rows = await api.search(server)
        lines_with_loc: List[str] = []
        lines_no_loc: List[str] = []
        for row in rows:
            cakes = row.get("cat_cakes", []) or []
            if not isinstance(cakes, list) or target_cake not in cakes:
                continue
            locations = row.get("cat_locations", []) or []
            valid_locations = isinstance(locations, list) and len(locations) == 3
            if setting["filter_location"] and setting["show_location"] and not valid_locations:
                continue
            uid = str(row.get("uid", "-"))
            cakes_text = [str(x) for x in cakes[:3]]
            if len(cakes_text) < 3:
                cakes_text.extend(["-"] * (3 - len(cakes_text)))
            if setting["show_location"] and valid_locations:
                line = "\n".join(
                    [
                        uid,
                        f"{cakes_text[0]}·{str(locations[0])}",
                        f"{cakes_text[1]}·{str(locations[1])}",
                        f"{cakes_text[2]}·{str(locations[2])}",
                    ]
                )
                lines_with_loc.append(line)
            else:
                line = f"{uid} {cakes_text[0]} {cakes_text[1]} {cakes_text[2]}"
                lines_no_loc.append(line)

        lines = lines_with_loc + lines_no_loc if setting["show_location"] else lines_no_loc
        if not lines:
            await search_cmd.finish(_with_quote(event, "未搜索到结果"))
        await search_cmd.finish(_with_quote(event, "\n".join(lines[:20])))
    except httpx.HTTPStatusError as e:
        await search_cmd.finish(_with_quote(event, f"搜索失败:HTTP {e.response.status_code}"))
    except FinishedException:
        raise
    except Exception as e:
        await search_cmd.finish(_with_quote(event, f"搜索失败:{e}"))


@upload_cmd.handle()
async def _(event: Event, matcher, args: Message = CommandArg()) -> None:
    parts = _split_args(args)
    if len(parts) < 4:
        await upload_cmd.finish(_with_quote(event, "用法：上传 <UID> <猫糕1> <猫糕2> <猫糕3>"))
    uid = parts[0].strip()
    if not uid.isdigit() or len(uid) != 9:
        await upload_cmd.finish(_with_quote(event, "上传失败:UID必须是9位数字"))
    if _infer_server_from_uid(uid) is None:
        await upload_cmd.finish(_with_quote(event, "上传失败:UID首位必须为1(官服)或5(B服)"))
    matcher.set_arg("raw_parts", " ".join(parts))
    if _get_user_settings(event)["choose_location"]:
        cakes = parts[1:4]
        panel = (
            f"{cakes[0]} {cakes[1]} {cakes[2]}\n"
            "1.猫爬架旁桌上台灯 2.吧台上固定电话 3.车厢上中部沙发 4.留声机旁盆栽 5.二楼楼梯旁花坛 7.车厢下中部沙发 6.帕姆衣架旁椅子\n"
            "请按猫猫糕顺序输入地点序号\n"
            "发送 0 跳过上传地点"
        )
        await matcher.send(_with_quote(event, panel))
        await matcher.pause()


@upload_cmd.handle()
async def _(event: Event, matcher) -> None:
    parts = _split_args(matcher.get_arg("raw_parts"))
    uid = parts[0].strip()
    server = _infer_server_from_uid(uid)
    cakes = parts[1:4]
    locations: List[str] = []

    if not uid.isdigit() or len(uid) != 9:
        await upload_cmd.finish(_with_quote(event, "上传失败:UID必须是9位数字"))
    if server is None:
        await upload_cmd.finish(_with_quote(event, "上传失败:UID首位必须为1(官服)或5(B服)"))
    assert server is not None

    if _get_user_settings(event)["choose_location"]:
        reply_parts = _split_args(getattr(event, "message", ""))
        if len(reply_parts) == 1 and reply_parts[0] == "0":
            locations = []
        elif len(reply_parts) != 3:
            await upload_cmd.finish(_with_quote(event, "请同时输入三个地点序号。"))
        else:
            try:
                idxs = [int(x) for x in reply_parts]
                if len(set(idxs)) != 3:
                    await upload_cmd.finish(_with_quote(event, "地点不能重复输入"))
                for x in idxs:
                    if x < 1 or x > 7:
                        raise ValueError
                locations = [LOCATION_OPTIONS[x - 1] for x in idxs]
            except Exception:
                await upload_cmd.finish(_with_quote(event, "地点序号无效"))

    try:
        ok = await api.upload(server=server, uid=uid, cat_cakes=cakes, cat_locations=locations)
        if ok:
            await upload_cmd.finish(_with_quote(event, "上传成功"))
        await upload_cmd.finish(_with_quote(event, "上传失败:接口未返回成功"))
    except httpx.HTTPStatusError as e:
        reason = _format_http_error_reason(e)
        await upload_cmd.finish(_with_quote(event, f"上传失败:{reason}"))
    except FinishedException:
        raise
    except Exception as e:
        await upload_cmd.finish(_with_quote(event, f"上传失败:{e}"))


@upload_aji_cmd.handle()
async def _(event: Event, args: Message = CommandArg()) -> None:
    parts = _split_args(args)
    if len(parts) < 1:
        await upload_aji_cmd.finish(_with_quote(event, "用法：上传阿基喵利 <UID>"))

    uid = parts[0].strip()
    server = _infer_server_from_uid(uid)
    if not uid.isdigit() or len(uid) != 9:
        await upload_aji_cmd.finish(_with_quote(event, "上传失败:UID必须是9位数字"))
    if server is None:
        await upload_aji_cmd.finish(_with_quote(event, "上传失败:UID首位必须为1(官服)或5(B服)"))
    assert server is not None

    try:
        ok = await api.upload_aji(server=server, uid=uid)
        if ok:
            await upload_aji_cmd.finish(_with_quote(event, "上传成功"))
        await upload_aji_cmd.finish(_with_quote(event, "上传失败:接口未返回成功"))
    except httpx.HTTPStatusError as e:
        reason = _format_http_error_reason(e)
        await upload_aji_cmd.finish(_with_quote(event, f"上传失败:{reason}"))
    except FinishedException:
        raise
    except Exception as e:
        await upload_aji_cmd.finish(_with_quote(event, f"上传失败:{e}"))


@daily_cmd.handle()
async def _(event: Event, args: Message = CommandArg()) -> None:
    parts = _split_args(args)
    if len(parts) < 1:
        await daily_cmd.finish(_with_quote(event, "用法：今日阿基喵利 <服务器>"))

    server = _map_server(parts[0])
    try:
        uid = await api.daily_aji(server)
        await daily_cmd.finish(_with_quote(event, f"阿基喵利:{uid or '无'}"))
    except httpx.HTTPStatusError as e:
        await daily_cmd.finish(_with_quote(event, f"查询失败:HTTP {e.response.status_code}"))
    except FinishedException:
        raise
    except Exception as e:
        await daily_cmd.finish(_with_quote(event, f"查询失败:{e}"))


@count_cmd.handle()
async def _(event: Event) -> None:
    try:
        count = await api.weekly_count()
        await count_cmd.finish(_with_quote(event, f"本周收录:{count}"))
    except httpx.HTTPStatusError as e:
        await count_cmd.finish(_with_quote(event, f"查询失败:HTTP {e.response.status_code}"))
    except FinishedException:
        raise
    except Exception as e:
        await count_cmd.finish(_with_quote(event, f"查询失败:{e}"))


@help_cmd.handle()
async def _(event: Event) -> None:
    await help_cmd.finish(
        _with_quote(
            event,
            "指令说明：\n"
            "1) 搜索 <服务器> <猫糕名称>\n"
            "2) 上传 <UID> <猫糕1> <猫糕2> <猫糕3>\n"
            "3) 上传阿基喵利 <UID>\n"
            "4) 今日阿基喵利 <服务器>\n"
            "5) 收录数量\n"
            "6) 设置\n"
            "上传会按UID首位自动选择服务器：1=官服，5=B服\n"
            "查询服务器可用: 1=官服, 2=B服（默认官服）",
        )
    )