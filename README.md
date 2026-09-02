# X Content Optimizer Agent

面向人工审核的 X（Twitter）内容优化 Agent：对待发布内容做发布前检查与优化，给出“发布 / 修改后发布 / 延后 / 禁止”决策、发布时间与预期表现建议，并在发布后复盘。

**只检查、只建议、只报告，永不代发。** 支持中英文内容。

## 核心能力

- 发布前检查：格式合规（文本/图片/视频）、内容质量（按资讯/带货/观点/教程/互动分类）、发布风险（平台规则、账号健康、重复度、时间冲突）。
- 决策输出：禁止 / 延后 / 修改后发布 / 可发布，附置信度与核心理由。
- 优化建议：hook 改写、结构删减、CTA、标签与媒体建议。
- 人工确认卡：原文 vs 建议对比、风险摘要、时间建议、预期表现区间。
- 发布后复盘：对比预期、五维归因、沉淀可复用建议并回写账号基线。
- 数据只读：通过 X API 只读权限拉取账号历史与单帖指标，计算发布基线。

## 目录结构

```text
x-content-optimizer-agent/
|-- SKILL.md                    技能入口：角色、边界与工作流
|-- agents/openai.yaml          UI 元数据
|-- references/
|   |-- checks.md               三线检查完整清单
|   |-- report-templates.md     决策报告/确认卡/复盘模板
|   `-- config-data.md          API 配置、账号档案、阈值与错误处理
|-- scripts/
|   `-- fetch_history.py        只读历史与单帖指标拉取（纯标准库）
`-- README.md
```

## 快速开始

1. 配置只读凭据（环境变量）：

   ```bash
   export X_API_KEY=...
   export X_API_SECRET=...
   export X_ACCESS_TOKEN=...
   export X_ACCESS_TOKEN_SECRET=...
   ```

   仅需只读权限：`tweet.read`、`users.read`、`offline.access`。

2. 拉取账号历史并建立基线：

   ```bash
   python scripts/fetch_history.py history --account @yourhandle
   ```

3. 在 Codex 中使用：将本目录放入技能目录（如 `~/.codex/skills/x-content-optimizer-agent`），或使用你所在客户端的技能安装功能从本仓库安装。然后提交待发布草稿即可，Agent 会输出决策报告与确认卡；发布动作始终由你手动完成。

## 边界说明

- 不自动发布、不修改、不删除任何内容。
- 平台规范判断是启发式风险评估，不代表平台裁决。
- 报告正文为中文；帖文示例与改写按目标账号语言（en/zh）。

## License

本项目使用 [MIT](LICENSE) 许可证。

Copyright (c) 2026 万婧
