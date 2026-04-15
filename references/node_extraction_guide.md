# Node Extraction Guide

怎么从对话里判断：**该不该建节点、该建什么节点、什么时候只写 session 就够了。**

## 先记住一个原则

**不是每句话都值得进树。**

树里只放“结构性信息”：

- 目标
- 方向
- 决策
- 问题
- 状态变化
- 阶段性推进

下面这些一般**不值得单独建节点**：

- 参数顺序调整
- 一行修 bug
- 局部重构但不影响方向
- 纯闲聊
- 已经在当前节点 `Summary` 里表达清楚的小修小补

## 信号 → 动作

| 信号 | 建什么 / 怎么改 |
|---|---|
| 方向变了 | `branch` |
| 冒出一个值得跟踪的新想法 | `idea` |
| 方案拍板了 | `decision` + `accepted` |
| 某个方案被否了 | 现有节点改成 `rejected` |
| 某件事先不做 | 现有节点改成 `parked` |
| 出现重要未决问题 | `question` |
| 根目标发生变化 | 更新 `root-goal`，再补一个 `decision` 说明原因 |
| 这轮有推进，但没出现以上结构变化 | 只写 `capture-session` |

## 怎么选 `idea` 和 `branch`

### 用 `idea`

当它还是一个想法、提议、候选方案，还没发展成明确推进方向时。

例子：

- “要不要以后加个导出功能？”
- “也许可以把日志打到 ES 里。”

### 用 `branch`

当它已经是一个明确方向，后续大概率会继续展开、分叉、被收敛时。

例子：

- “日志这块我们改成走 Elasticsearch。”
- “客户端观测先从 metrics 方向推进。”

简单说：**`idea` 偏灵感，`branch` 偏要推进的方向。**

## 对话 → 节点映射示例

### 示例 1：用户提出新方向

```text
用户：我觉得我们应该把日志存到 ES 里，不只是本地文件。
```

动作：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --title "日志存储迁移到 ES" \
  --parent root-goal \
  --kind branch \
  --status active \
  --summary "把日志从本地文件改为写入 Elasticsearch。"
```

### 示例 2：用户拍板

```text
用户：就用方案 B 吧，WebSocket 比轮询好。
```

动作：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --node-id websocket-vs-polling \
  --kind decision \
  --status accepted \
  --summary "确认用 WebSocket，放弃轮询方案。"
```

### 示例 3：用户否决

```text
用户：Redis 那个方案算了，太重了。
```

动作：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --node-id redis-cache-branch \
  --status rejected \
  --summary "Redis 方案因复杂度过高被否决。"
```

### 示例 4：用户搁置

```text
用户：国际化先不做，等核心功能稳了再说。
```

动作：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --node-id i18n-support \
  --status parked \
  --summary "国际化搁置，等核心功能稳定后再启动。"
```

### 示例 5：出现未解决的问题

```text
用户：鉴权到底用 JWT 还是 session？我还没想好。
```

动作：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --title "鉴权方案选型" \
  --parent root-goal \
  --kind question \
  --status active \
  --summary "JWT vs session，待定。"
```

### 示例 6：目标本身变了

```text
用户：其实我不只是要一个监控面板，我要的是一整套可观测性方案。
```

第一步，更新根目标：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --node-id root-goal \
  --summary "从监控面板扩展为完整的可观测性方案。"
```

第二步，补一个 decision 记录为什么变：

```bash
python3 scripts/init_discussion_tree.py upsert-node \
  --root $ROOT \
  --title "目标从监控扩展为可观测性" \
  --parent root-goal \
  --kind decision \
  --status accepted \
  --summary "原目标是监控面板，现在扩展为可观测性全套。" \
  --why "用户认为只做面板不够，需要从日志、metrics、trace 三个维度覆盖。"
```

### 示例 7：只写 session，不建节点

```text
用户：这个函数的参数顺序调一下。
AI：调好了。
```

动作：**不建节点。**

如果这轮还有实质推进，写一条 `capture-session` 就够：

```bash
python3 scripts/init_discussion_tree.py capture-session \
  --root $ROOT \
  --summary "完成了一个局部实现调整，没有新增方向或决策" \
  --change "无结构性变化" \
  --follow-up "继续当前 active branch"
```

## 一个简单判断流程

```text
这轮对话里有没有出现：
├── 新方向 / 新想法       → upsert-node (branch / idea)
├── 拍板 / 否决 / 搁置    → 更新状态或写 decision
├── 未解决的重要问题      → upsert-node (question)
├── 目标本身变化          → 更新 root-goal + 补 decision
├── 没有以上变化，但有推进 → capture-session
└── 纯闲聊 / 极小改动     → 跳过
```

## 常见误判

### 误判 1：把“讨论实现方式”当成“新方向”

如果只是同一条 active branch 里的实现收敛，通常改 `Summary` 或写 session 就够，不一定要新开节点。

### 误判 2：用户只是倾向，不是拍板

“我有点偏向方案 B” 不是 `accepted`。

只有出现这类明确信号时，才写成已确定：

- “就这个吧”
- “按这个做”
- “不用比了，定这个”
- “另一个方案放弃”

### 误判 3：目标已经变了，但你只改叶子节点

如果根问题变了，只修枝叶没有用。要先改 `root-goal`。

## 最后一句

**先判断这句话会不会改变项目树的形状；会，再写节点；不会，就别硬写。**
