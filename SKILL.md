---
name: tree-of-discussion
description: "Use this skill when a user wants a discussion tree where the original goal is the root and later ideas, decisions, and abandoned paths grow as child nodes that both the user and the agent can revisit over time."
---

# Tree of Discussion

一棵自动维护的 Markdown 讨论树。记录项目目标的演变、方向的分叉、决策的拍板与否决。

不是知识库，不是项目管理工具。只干一件事：**让长周期项目在多轮对话后依然能低成本恢复上下文。**

## Operating loop

### Session start

```
1. ensure --root <project>
2. 读 .discussion/context.md
3. 检查 Drift Check — 有 warning 先纠偏
```

### During conversation

只在出现结构性信号时写节点：

| 信号 | 动作 |
|---|---|
| 新方向 | `upsert-node --kind branch` |
| 新想法 | `upsert-node --kind idea` |
| 拍板 | `upsert-node --kind decision --status accepted` |
| 否决 | `upsert-node --status rejected` |
| 搁置 | `upsert-node --status parked` |
| 未决问题 | `upsert-node --kind question` |
| 目标变了 | 更新 `root-goal` + 补 decision 记录原因 |

没命中 → 不写。

### Session end

```
capture-session --summary "..." --node <id> --change "..." --follow-up "..."
```

纯闲聊或极小改动可跳过。

## What gets generated

```
.discussion/
├── tree.md       # 人看
├── context.md    # AI 看
├── log.md        # 变更时间线（记录 before → after）
├── nodes/        # 源数据：每个节点一个文件
└── sessions/     # 源数据：每轮讨论一个文件
```

`tree.md` 和 `context.md` 是视图，不是源数据。源数据在 `nodes/` 和 `sessions/`。

## Commands

脚本：`scripts/init_discussion_tree.py`

| 命令 | 用途 |
|---|---|
| `ensure` | 建树 / 补齐缺失结构 |
| `upsert-node` | 建 / 改节点 |
| `capture-session` | 沉淀一轮讨论 |
| `context` | 刷新 context.md（`--stdout` 可直接输出） |
| `rebuild` | 从源数据重建所有视图 |

## Boundary

这个 skill 只管**会随讨论演变的方向和决策**。

- 不会变的偏好 → Memory / Rules
- 当前 session 的执行步骤 → TODO
- 需求全文 → Spec（tree 里只放摘要）
- 不要把同一条信息同时写进 tree 和 Memory

## Rules

1. Agent 负责维护树，不甩给用户
2. 只记录结构性信息，不写流水账
3. `root-goal` 是占位符时先补真实目标
4. 当前工作追不到 active branch → 建新 branch 或承认跑偏
5. 不忽略 Drift Check 的 warning
6. 默认拒绝写入 skill 项目根目录和 workspace 根目录（`--allow-skill-project` / `--allow-workspace-root` 放行）

## Anti-patterns

- 每句话建一个节点
- 纯实现细节建节点
- 用户没拍板就写 `accepted`
- 目标变了只改叶子不改 `root-goal`
- 一轮结束什么都不写

## Reference

- `references/node_extraction_guide.md` — 怎么判断该不该建节点
