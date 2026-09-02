# 数据、配置与规则

## X API（只读）

凭据通过环境变量提供：

- `X_API_KEY`、`X_API_SECRET`
- `X_ACCESS_TOKEN`、`X_ACCESS_TOKEN_SECRET`

只应使用只读 OAuth 1.0a 用户上下文权限：`tweet.read`、`users.read`、`offline.access`。不需要发帖/删除权限；若发现配置含写权限，提醒审核人收紧。

用途：

- 拉取本账号最近历史帖子与表现指标；
- 按 ID 拉取单帖指标；
- 读取账号基本信息。

## 数据脚本

`scripts/fetch_history.py` 纯标准库实现，只读：

```bash
python scripts/fetch_history.py me
python scripts/fetch_history.py history --account @handle [--pages 5] [--offline]
python scripts/fetch_history.py tweet <tweet_id> [--account @handle]
```

- `me`：打印当前凭据对应的账号。
- `history`：拉取该账号最近帖文并计算基线；默认排除转贴与回复。结果合并写入 `work/<account>.json`（只增不删）。`--offline` 只读缓存不发请求。
- `tweet`：拉取单帖指标；给出 `--account` 时并入该账号缓存。
- 若账号数据权限不支持曝光等非公开指标，脚本会自动降级为仅公开指标并在输出中标注；此时“预期表现”不写曝光区间，改用公开互动量口径并说明。

缓存文件结构：

```json
{
  "fetched_at": "2026-09-02T10:00:00+00:00",
  "account": {"id": "…", "username": "…", "name": "…"},
  "tweets": [
    {
      "id": "…",
      "text": "…",
      "created_at": "…",
      "public_metrics": {"like_count": 0, "reply_count": 0, "retweet_count": 0, "quote_count": 0, "bookmark_count": 0},
      "non_public_metrics": {"impression_count": 0}
    }
  ],
  "degraded_metrics": false
}
```

新鲜度：缓存超过 24 小时或涉及“是否重复/是否撞期”判断时优先刷新；无法刷新则注明“基于 <日期> 数据”。

## 账号档案

每账号一份 JSON。查找顺序：

1. 固定数据目录：`~/.codex/x-content-optimizer-agent/profiles/<account>-profile.json`（Windows 下为 `C:\Users\<用户名>\.codex\x-content-optimizer-agent\profiles\...`）；
2. 当前运行目录的 `work/<account>-profile.json`；
3. 审核人直接提供 JSON 内容。

首次使用某账号且尚无档案时，按审核人给出的 handle、语言、定位创建档案并存入固定数据目录。关键字段：

```json
{
  "account": "@handle",
  "language": "en",
  "timezone": "America/Los_Angeles",
  "char_limit": 280,
  "niche": "产品与技术",
  "audience": "欧美开发者",
  "tone_rules": ["不用夸张疗效承诺", "保持技术细节准确"],
  "ad_disclosure": true,
  "hard_block_words": [],
  "soft_review_words": [],
  "max_posts_per_hour": 1,
  "max_posts_per_day": 4,
  "competitor_accounts": []
}
```

账号档案决定语言规则、字符上限、时间换算、节奏约束与敏感词档位；不同账号必须使用各自档案，不混用。

## 基线口径

- 互动 = 点赞 + 回复 + 转贴 + 引用 + 收藏。
- 互动率 = 互动 / 曝光。
- 基线：曝光与互动率的中位数、P25、P75（脚本输出；无足够数据时明确标注）。
- 时段：按账号时区统计各小时/星期的曝光中位数，取最高的 1–2 个时间窗。

## 默认阈值（可按账号覆盖）

| 项 | 默认 | 命中含义 |
|---|---|---|
| 自身历史重复度 | >80% | 禁止 |
| 自身历史重复度 | 50–80% | 修改后发布 |
| 话题标签 | >3 | 中风险信号 |
| 同小时已发 | ≥2 | 高健康风险 / 撞期 |
| 近 7 天日发 | ≥5 | 中健康风险 |
| 自推占比 | >1/3（近 30 帖） | 中健康风险 |
| 历史缓存 | >24 小时 | 优先刷新 |

## 规则沉淀

- 审核人每次驳回都要记录理由，转成“硬禁词 / 软风险词 / 账号口径”三类规则之一写入档案。
- 资讯类经审核人确认过的数据、来源、口径、链接记入事实库，供后续同类内容比对。
- 规则只增不改用户明确推翻过的条目；推翻时更新并记录原因。

## 常见 API 错误处理

- 401：凭据无效或过期，请审核人重新生成只读令牌。
- 403：权限不足（如账号数据等级不支持非公开指标），降级为公开指标并说明，或提醒提升数据访问等级。
- 404：账号或帖子不存在、已删除，或无权访问。
- 429：触发限流，等待后重试或改用缓存并注明时间。
