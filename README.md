# nonebot-plugin-catcake

适用与 NoneBot2 的猫猫糕查询＆上传插件,数据通过API与 [`猫猫糕统计`](https://catcs.v6.army/) 网站同步。


## 安装

### 使用 NB-CLI 安装（推荐）

```bash
nb plugin install nonebot-plugin-catcake
```

### 使用 pip 安装

```bash
pip install nonebot-plugin-catcake
```

安装后，在 NoneBot 项目中加载插件：

```python
nonebot.load_plugin("nonebot_plugin_catcake")
```

如果使用 `pyproject.toml` 管理 NoneBot 插件，也可以添加：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_catcake"]
```

## 配置

插件支持零配置加载；如需修改默认值，可在 `.env` 中配置：

```env
CATCAKE_API_BASE=https://catcs.v6.army
CATCAKE_DEFAULT_SERVER=官服
CATCAKE_TIMEOUT=10
```

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `CATCAKE_API_BASE` | `https://catcs.v6.army` | 猫猫糕 API 基础地址。 |
| `CATCAKE_DEFAULT_SERVER` | `官服` | 查询指令未提供有效服务器时使用的默认服务器。 |
| `CATCAKE_TIMEOUT` | `10` | HTTP 请求超时时间，单位为秒。 |

## 指令

| 指令 | 说明 |
| --- | --- |
| `搜索 <服务器> <猫糕名称>` | 返回匹配记录。默认每行格式：`<UID> <猫糕1> <猫糕2> <猫糕3>`。 |
| `上传 <UID> <猫糕1> <猫糕2> <猫糕3>` | 按 UID 自动识别服务器并上传 3 个猫糕。 |
| `上传阿基喵利 <UID>` | 按 UID 自动识别服务器并上传当日阿基喵利 UID。 |
| `今日阿基喵利 <服务器>` | 返回指定服务器的当日阿基喵利 UID。 |
| `收录数量` | 返回本周收录数量。 |
| `地点设置` | 设置是否显示地点、是否过滤无地点记录、上传时是否选择地点。 |
| `cathelp` | 显示指令说明。 |

服务器参数支持：

- `1`：官服
- `2`：B服
- 其他文本会按原值传递给 API

上传类指令会按 UID 首位自动识别服务器：

- `1` 开头：官服
- `5` 开头：B服

## 示例

```text
搜索 1 薄荷提拉咪
上传 123456789 薄荷提拉咪 白玉青团 红豆牛奶
上传阿基喵利 123456789
今日阿基喵利 2
```

