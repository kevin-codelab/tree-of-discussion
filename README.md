# tree-of-discussion

AI 自动维护的项目讨论树。

vibe coding 做久了有三个真实痛点：AI 忘目标、人和 AI 都忘了哪些定了哪些没定、越做越偏纠偏成本高。这个 skill 用一棵 Markdown 树解决它们。

## 设计理念

受 [Karpathy 的 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 启发：

- **人是策展人，AI 是图书管理员** — 人负责方向判断，AI 负责记录和维护
- **源数据和视图分离** — `nodes/` + `sessions/` 是源数据，`tree.md` + `context.md` 是自动生成的视图
- **只追加的时间线** — `log.md` 记录每次变更的 before → after，不需要 git diff 就能看到演变过程
- **轻量** — 没有数据库、没有服务端、没有额外依赖，就是一堆 Markdown 文件

## 你会得到什么

```
项目/.discussion/
├── tree.md       # 人看：5 秒知道当前状态
├── context.md    # AI 看：恢复上下文 + 漂移检测
├── log.md        # 变更时间线（before → after）
├── nodes/        # 每个方向 / 决策 / 问题一个文件
└── sessions/     # 每轮讨论一个文件
```

隐藏目录，自动加 `.gitignore`。

## 快速开始

```bash
# 1. 建树
python3 scripts/init_discussion_tree.py ensure --root /path/to/project

# 2. 把根目标改成真实目标
python3 scripts/init_discussion_tree.py upsert-node \
  --root /path/to/project \
  --node-id root-goal \
  --summary "做一个轻量级的全栈 todo app"

# 3. 建几个关键方向
python3 scripts/init_discussion_tree.py upsert-node \
  --root /path/to/project \
  --node-id auth-choice \
  --title "鉴权方案" \
  --parent root-goal \
  --kind question \
  --summary "JWT vs session，待定。"

# 4. 一轮讨论结束
python3 scripts/init_discussion_tree.py capture-session \
  --root /path/to/project \
  --summary "确认了技术栈，留下了鉴权待定问题" \
  --node root-goal --node auth-choice \
  --change "新增鉴权选型问题节点" \
  --follow-up "比较 JWT 和 session 的复杂度"

# 5. 下次继续前
python3 scripts/init_discussion_tree.py context \
  --root /path/to/project --stdout
```

## 什么时候该写节点

| 信号 | 动作 |
|---|---|
| 出现新方向 | `upsert-node --kind branch` |
| 冒出新想法 | `upsert-node --kind idea` |
| 方案拍板 | `upsert-node --kind decision --status accepted` |
| 方案否了 | `upsert-node --status rejected` |
| 暂时不做 | `upsert-node --status parked` |
| 出现未决问题 | `upsert-node --kind question` |
| 目标本身变了 | 更新 `root-goal` + 补 decision |

什么都没发生 → 不写。

## 节点模型

每个节点是一个 `.md` 文件：

**frontmatter**：`id` / `title` / `parent` / `kind` / `status` / `created` / `updated`

**kind**：`root` / `goal` / `idea` / `branch` / `decision` / `question`

**status**：`active` / `accepted` / `parked` / `rejected`

**正文 section**：
- `Summary` — 这个节点现在是什么
- `Why this branch exists` — 为什么有这个分支
- `Next` — 跨 session 的方向性下一步
- `Related sessions` — 在哪些轮次被推进过

## 命令

| 命令 | 用途 |
|---|---|
| `ensure` | 建树或补齐缺失结构 |
| `upsert-node` | 建 / 改节点（推荐日常使用） |
| `capture-session` | 沉淀一轮讨论 |
| `context` | 刷新 context.md（`--stdout` 直接输出） |
| `rebuild` | 从源数据重建所有视图 |

### `upsert-node` 参数

| 参数 | 说明 |
|---|---|
| `--node-id` | 节点 id（推荐显式传） |
| `--title` | 标题（不传 node-id 时从 title 生成 id） |
| `--parent` | 父节点 id（默认 `root-goal`） |
| `--kind` | 节点类型 |
| `--status` | 节点状态 |
| `--summary` | 覆盖 Summary |
| `--why` | 覆盖 Why this branch exists |
| `--next` | 追加到 Next（可重复） |

### `capture-session` 参数

| 参数 | 说明 |
|---|---|
| `--summary` | 这轮推进了什么 |
| `--node` | 碰到的节点 id（可重复） |
| `--change` | 树里发生了什么变化（可重复） |
| `--follow-up` | 下一步做什么（可重复） |

## log.md 里能看到什么

```
[2026-04-15 10:00] upsert-node (update) | root-goal: summary: "做监控面板" → "做可观测性方案"
[2026-04-15 10:05] upsert-node (update) | auth-choice: status: active → accepted
[2026-04-15 10:10] upsert-node (create) | 日志存储迁移到-es
```

不需要 git diff，翻 log 就能看到什么时候、什么变了、从什么变成了什么。

## 不追求什么

- 不记录每句话
- 不替代 Jira / Linear / issue tracker
- 不做通用知识管理系统

它只服务一个目标：**让长周期项目在多轮对话之后，依然能快速恢复上下文，并保持方向稳定。**

## 配合 Obsidian 使用（可选）

不需要改任何配置。节点和 session 文件里已经有 `[[wikilink]]` 互相引用，直接用 Obsidian 打开 `.discussion/` 目录就能获得：

- **Graph View** — 自动生成的关系网络图，节点越多越好看
- **反向链接** — 点进任何节点都能看到哪些 session 推进过它
- **快速跳转** — Cmd+O 直接搜节点名

```bash
# 方法 1：把 .discussion 作为独立 vault
# Obsidian → Open folder as vault → 选 /path/to/project/.discussion

# 方法 2：项目本身就是 vault，.discussion 自动被包含
```

## 致谢

- [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — raw / wiki / schema 三层架构、index + log 双文件机制
- [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) — AI 自主维护知识库的理念
