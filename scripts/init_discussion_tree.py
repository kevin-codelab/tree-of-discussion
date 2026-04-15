#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M"
DEFAULT_DIR = ".discussion"
ROOT_NOTE_NAME = "root-goal.md"
CONTEXT_NOTE_NAME = "context.md"
LOG_NOTE_NAME = "log.md"

NODE_SECTION_ORDER = [
    "Summary",
    "Why this branch exists",
    "Next",
    "Related sessions",
]
SESSION_SECTION_ORDER = [
    "Summary",
    "Nodes touched",
    "What changed in the tree",
    "Follow-ups",
]


@dataclass
class TreeNode:
    id: str
    title: str
    parent: str
    kind: str
    status: str
    created: str
    updated: str
    path: Path
    relative_path: str
    summary: str


@dataclass
class SessionNote:
    title: str
    date: str
    related_nodes: list[str]
    path: Path
    relative_path: str
    summary: str


def now_date() -> str:
    return datetime.now(timezone.utc).strftime(DATE_FMT)


def now_datetime() -> str:
    return datetime.now(timezone.utc).strftime(DATETIME_FMT)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "node"


def write_file(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def child_project_dirs(project_root: Path) -> list[str]:
    if not project_root.exists() or not project_root.is_dir():
        return []
    children: list[str] = []
    for child in sorted(project_root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / ".git").exists() or (child / "SKILL.md").exists():
            children.append(child.name)
    return children


def skill_project_markers(project_root: Path) -> list[str]:
    markers: list[str] = []
    if (project_root / "SKILL.md").exists():
        markers.append("SKILL.md")
    if (project_root / "references").is_dir():
        markers.append("references/")
    if (project_root / "scripts").is_dir():
        markers.append("scripts/")
    return markers


def validate_target_root(
    project_root: Path,
    *,
    allow_skill_project: bool,
    allow_workspace_root: bool,
) -> None:
    markers = skill_project_markers(project_root)
    if markers and not allow_skill_project:
        marker_text = ", ".join(markers)
        raise SystemExit(
            "Refusing to write a discussion tree into a skill project root "
            f"(`{project_root}`; markers: {marker_text}). "
            "Pass --allow-skill-project only when you explicitly want the tree inside that skill repo."
        )

    child_projects = child_project_dirs(project_root)
    if len(child_projects) >= 2 and not allow_workspace_root:
        preview = ", ".join(child_projects[:5])
        raise SystemExit(
            "Refusing to write a discussion tree into a workspace-like root "
            f"(`{project_root}`; child projects: {preview}). "
            "Pass --allow-workspace-root only when you explicitly want that."
        )


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    raw_meta = parts[0][4:]
    body = parts[1]
    meta: dict[str, Any] = {}
    for line in raw_meta.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        raw_value = value.strip()
        if not raw_value:
            meta[key] = ""
            continue
        if raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                meta[key] = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError):
                meta[key] = raw_value
            continue
        if raw_value.lower() in {"true", "false"}:
            meta[key] = raw_value.lower() == "true"
            continue
        meta[key] = raw_value
    return meta, body


def frontmatter_value(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_frontmatter(meta: dict[str, Any], key_order: list[str]) -> str:
    lines = ["---"]
    seen: set[str] = set()
    for key in key_order:
        if key in meta:
            lines.append(f"{key}: {frontmatter_value(meta[key])}")
            seen.add(key)
    for key in meta:
        if key not in seen:
            lines.append(f"{key}: {frontmatter_value(meta[key])}")
    lines.append("---")
    return "\n".join(lines)


def parse_sections(text: str) -> tuple[list[str], dict[str, str]]:
    order: list[str] = []
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            order.append(current)
            buffer = []
            continue
        if current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return order, sections


def render_sections(
    sections: dict[str, str],
    preferred_order: list[str],
    discovered_order: list[str] | None = None,
) -> str:
    discovered_order = discovered_order or []
    ordered_titles = list(preferred_order)
    for title in discovered_order:
        if title not in ordered_titles:
            ordered_titles.append(title)
    for title in sections:
        if title not in ordered_titles:
            ordered_titles.append(title)

    blocks: list[str] = []
    for title in ordered_titles:
        content = sections.get(title, "").strip()
        blocks.append(f"## {title}\n\n{content}" if content else f"## {title}\n")
    return "\n\n".join(blocks).rstrip() + "\n"


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def dedupe_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def bulletize(items: list[str]) -> str:
    cleaned = dedupe_keep_order(items)
    if not cleaned:
        return ""
    return "\n".join(f"- {item}" for item in cleaned)


def merge_bullets(existing: str, new_items: list[str]) -> str:
    current = [line.strip()[2:] if line.strip().startswith("- ") else line.strip() for line in existing.splitlines() if line.strip()]
    merged = dedupe_keep_order([*current, *new_items])
    return bulletize(merged)


def node_note(
    *,
    node_id: str,
    title: str,
    parent: str,
    kind: str,
    status: str,
    created: str,
    updated: str,
    summary: str = "",
    why: str = "",
    next_items: list[str] | None = None,
    related_sessions: list[str] | None = None,
) -> str:
    meta = {
        "id": node_id,
        "title": title,
        "parent": parent,
        "kind": kind,
        "status": status,
        "created": created,
        "updated": updated,
    }
    sections = {
        "Summary": summary.strip(),
        "Why this branch exists": why.strip(),
        "Next": bulletize(next_items or []),
        "Related sessions": bulletize(related_sessions or []),
    }
    return (
        render_frontmatter(meta, ["id", "title", "parent", "kind", "status", "created", "updated"])
        + "\n\n"
        + f"# {title}\n\n"
        + render_sections(sections, NODE_SECTION_ORDER)
    )


def root_note(project_name: str) -> str:
    today = now_date()
    return node_note(
        node_id="root-goal",
        title=f"{project_name} original goal",
        parent="",
        kind="root",
        status="active",
        created=today,
        updated=now_datetime(),
        summary="写这里：这个项目最原始、最朴素的目标到底是什么。",
        why="这就是整棵树的根。后面所有方向都应该从这里长出来。",
    )


def session_note(
    *,
    title: str,
    timestamp: str,
    related_nodes: list[str],
    summary: str,
    changes: list[str],
    follow_ups: list[str],
) -> str:
    meta = {
        "type": "session",
        "date": timestamp,
        "title": title,
        "related_nodes": dedupe_keep_order(related_nodes),
    }
    sections = {
        "Summary": summary.strip(),
        "Nodes touched": bulletize([f"[[../nodes/{node_id}]]" for node_id in dedupe_keep_order(related_nodes)]),
        "What changed in the tree": bulletize(changes),
        "Follow-ups": bulletize(follow_ups),
    }
    return (
        render_frontmatter(meta, ["type", "date", "title", "related_nodes"])
        + "\n\n"
        + f"# {title}\n\n"
        + render_sections(sections, SESSION_SECTION_ORDER)
    )


def load_node_document(path: Path) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    order, sections = parse_sections(body)
    return meta, order, sections


def render_node_document(meta: dict[str, Any], sections: dict[str, str], discovered_order: list[str]) -> str:
    title = str(meta.get("title", meta.get("id", path_stem_from_meta(meta)))).strip() or path_stem_from_meta(meta)
    meta["title"] = title
    return (
        render_frontmatter(meta, ["id", "title", "parent", "kind", "status", "created", "updated"])
        + "\n\n"
        + f"# {title}\n\n"
        + render_sections(sections, NODE_SECTION_ORDER, discovered_order)
    )


def path_stem_from_meta(meta: dict[str, Any]) -> str:
    return str(meta.get("id", "node")).strip() or "node"



def status_icon(status: str) -> str:
    return {
        "active": "🌿",
        "accepted": "✅",
        "parked": "⏸️",
        "rejected": "❌",
    }.get(status, "•")



def load_nodes(discussion_root: Path) -> list[TreeNode]:
    nodes_dir = discussion_root / "nodes"
    if not nodes_dir.exists():
        return []
    nodes: list[TreeNode] = []
    for path in sorted(nodes_dir.glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        _, sections = parse_sections(body)
        node_id = str(meta.get("id", "")).strip()
        title = str(meta.get("title", path.stem)).strip()
        parent = str(meta.get("parent", "")).strip()
        kind = str(meta.get("kind", "idea")).strip() or "idea"
        status = str(meta.get("status", "active")).strip() or "active"
        created = str(meta.get("created", "")).strip() or now_date()
        updated = str(meta.get("updated", "")).strip() or created
        if not node_id:
            raise ValueError(f"Node {path} is missing frontmatter id")
        nodes.append(
            TreeNode(
                id=node_id,
                title=title,
                parent=parent,
                kind=kind,
                status=status,
                created=created,
                updated=updated,
                path=path,
                relative_path=path.relative_to(discussion_root).as_posix(),
                summary=sections.get("Summary", "").strip(),
            )
        )
    return nodes


def load_sessions(discussion_root: Path) -> list[SessionNote]:
    sessions_dir = discussion_root / "sessions"
    if not sessions_dir.exists():
        return []
    sessions: list[SessionNote] = []
    for path in sorted(sessions_dir.glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        _, sections = parse_sections(body)
        title = str(meta.get("title", "")).strip()
        if not title:
            title = first_heading(body) or path.stem
        raw_related = meta.get("related_nodes", [])
        related_nodes = [str(item).strip() for item in raw_related] if isinstance(raw_related, list) else []
        sessions.append(
            SessionNote(
                title=title,
                date=str(meta.get("date", "")).strip(),
                related_nodes=related_nodes,
                path=path,
                relative_path=path.relative_to(discussion_root).as_posix(),
                summary=sections.get("Summary", "").strip(),
            )
        )
    return sessions


def first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def validate_nodes(nodes: list[TreeNode]) -> None:
    seen: set[str] = set()
    ids = {node.id for node in nodes}
    for node in nodes:
        if node.id in seen:
            raise ValueError(f"Duplicate node id: {node.id}")
        seen.add(node.id)
        if node.parent and node.parent not in ids:
            raise ValueError(f"Node {node.id} references missing parent {node.parent}")


def build_children(nodes: list[TreeNode]) -> dict[str, list[TreeNode]]:
    children: dict[str, list[TreeNode]] = defaultdict(list)
    for node in sorted(nodes, key=lambda item: (item.created, item.title.lower())):
        children[node.parent].append(node)
    return children


def path_to_root(node_id: str, id_map: dict[str, TreeNode]) -> list[TreeNode]:
    path: list[TreeNode] = []
    cursor = id_map.get(node_id)
    while cursor is not None:
        path.append(cursor)
        cursor = id_map.get(cursor.parent)
    path.reverse()
    return path


def active_leaf_paths(nodes: list[TreeNode]) -> list[tuple[TreeNode, list[TreeNode]]]:
    children = build_children(nodes)
    id_map = {node.id: node for node in nodes}
    active_nodes = [node for node in nodes if node.status == "active"]
    leaves: list[tuple[TreeNode, list[TreeNode]]] = []
    for node in active_nodes:
        active_children = [child for child in children.get(node.id, []) if child.status == "active"]
        if active_children:
            continue
        leaves.append((node, path_to_root(node.id, id_map)))
    return sorted(leaves, key=lambda item: (item[0].created, item[0].title.lower()))



def render_human_tree(
    project_name: str,
    project_root: Path,
    nodes: list[TreeNode],
    sessions: list[SessionNote],
    discussion_root: Path,
) -> str:
    """The one file a human opens to understand the project. No special syntax, no metadata."""
    validate_nodes(nodes)
    roots = [n for n in nodes if not n.parent]
    root = roots[0] if roots else None
    root_summary = first_nonempty_line(root.summary) if root else ""

    lines = [f"# {project_name}", ""]
    if root_summary:
        lines.append(f"> {root_summary}")
        lines.append("")

    # --- Active ---
    active = [n for n in nodes if n.status == "active" and n.kind != "root"]
    if active:
        lines.append("## 当前在推进")
        lines.append("")
        for n in sorted(active, key=lambda x: x.updated, reverse=True):
            summary = first_nonempty_line(n.summary)
            lines.append(f"- **{n.title}**" + (f" — {summary}" if summary else ""))
        lines.append("")

    # --- Accepted ---
    accepted = [n for n in nodes if n.status == "accepted"]
    if accepted:
        lines.append("## 已确定")
        lines.append("")
        for n in sorted(accepted, key=lambda x: x.updated, reverse=True):
            summary = first_nonempty_line(n.summary)
            lines.append(f"- ✅ **{n.title}**" + (f" — {summary}" if summary else ""))
        lines.append("")

    # --- Parked / Rejected ---
    parked = [n for n in nodes if n.status in {"parked", "rejected"}]
    if parked:
        lines.append("## 已搁置 / 已否决")
        lines.append("")
        for n in sorted(parked, key=lambda x: x.updated, reverse=True):
            icon = "⏸️" if n.status == "parked" else "❌"
            summary = first_nonempty_line(n.summary)
            lines.append(f"- {icon} **{n.title}**" + (f" — {summary}" if summary else ""))
        lines.append("")

    # --- Questions ---
    questions = [n for n in nodes if n.kind == "question" and n.status == "active"]
    if questions:
        lines.append("## 未决问题")
        lines.append("")
        for n in questions:
            summary = first_nonempty_line(n.summary)
            lines.append(f"- ❓ **{n.title}**" + (f" — {summary}" if summary else ""))
        lines.append("")

    # --- Recent sessions ---
    recent = sorted(sessions, key=lambda s: s.date, reverse=True)[:5]
    if recent:
        lines.append("## 最近讨论")
        lines.append("")
        for s in recent:
            summary = first_nonempty_line(s.summary)
            date_short = s.date.split(" ")[0] if s.date else ""
            lines.append(f"- {date_short} **{s.title}**" + (f" — {summary}" if summary else ""))
        lines.append("")

    # --- Log tail ---
    log_path = discussion_root / LOG_NOTE_NAME
    if log_path.exists():
        log_lines = [l.strip() for l in log_path.read_text(encoding="utf-8").splitlines() if l.startswith("[")]
        tail = log_lines[-10:] if len(log_lines) > 10 else log_lines
        if tail:
            lines.append("## 变更时间线")
            lines.append("")
            for entry in tail:
                lines.append(entry)
            lines.append("")

    return "\n".join(lines)



def append_log(discussion_root: Path, action: str, detail: str) -> None:
    """Append one line to the append-only log. Never rewrite, only append."""
    log_path = discussion_root / LOG_NOTE_NAME
    timestamp = now_datetime()
    entry = f"[{timestamp}] {action} | {detail}\n"

    if not log_path.exists():
        header = "# Log\n\n变更时间线。只追加，不重写。\n\n"
        write_file(log_path, header + entry)
    else:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)


def render_drift_check(
    root: TreeNode | None,
    active_leaves: list[tuple[TreeNode, list[TreeNode]]],
    outcome_nodes: list[TreeNode],
) -> list[str]:
    lines: list[str] = []
    if root is None:
        lines.append("- **WARNING**: 没有 root 节点，树还没初始化完成。先填 root-goal 再继续。")
        return lines

    root_summary = first_nonempty_line(root.summary)
    if not root_summary or root_summary == "写这里：这个项目最原始、最朴素的目标到底是什么。":
        lines.append("- **WARNING**: root-goal 的 Summary 还是模板占位符，没写真正的目标。")
        lines.append("  - **动作**: 立刻用 `upsert-node --node-id root-goal --summary \"...\"` 补上真实目标。")
        return lines

    lines.append(f"- Root goal: {root_summary}")

    if not active_leaves:
        lines.append("- **WARNING**: 没有任何 active 叶子分支。项目是不是已经结束了？如果没有，应该从 root-goal 长出新分支。")
        return lines

    for node, branch in active_leaves:
        branch_text = " -> ".join(item.title for item in branch)
        leaf_summary = first_nonempty_line(node.summary)
        lines.append(f"- Active branch: `{branch_text}`")
        if leaf_summary:
            lines.append(f"  - doing: {leaf_summary}")
        else:
            lines.append(f"  - **WARNING**: 这个活跃分支没有 Summary，不清楚在做什么。补上。")

    total_nodes = len(active_leaves) + len(outcome_nodes)
    if total_nodes > 0 and len(active_leaves) == 1 and not outcome_nodes:
        pass
    elif len(active_leaves) > 3:
        lines.append(f"- **NOTICE**: 有 {len(active_leaves)} 条活跃分支同时在推进，考虑收敛或 park 一些。")

    lines.extend([
        "",
        "偏离自查：",
        "- 你当前在做的事，能从上面某条 active branch 的 path 追溯到 root goal 吗？",
        "- 如果不能 → 要么建新 branch，要么你在偏离。",
        "- 如果能但方向变了 → 更新对应节点的 Summary，或建 decision/question 子节点。",
    ])
    return lines


def render_extraction_checklist() -> list[str]:
    return [
        "每轮对话结束前，对照这个 checklist 决定是否要写节点：",
        "",
        "| 信号 | 动作 |",
        "|---|---|",
        "| 用户说了一个新想法/新方向 | `upsert-node --kind idea` 或 `--kind branch` |",
        "| 用户明确拍板了某个方案 | `upsert-node --kind decision --status accepted` |",
        "| 用户明确否决了某个方案 | `upsert-node --status rejected` |",
        '| 用户说"先不做这个" | `upsert-node --status parked` |',
        "| 讨论里出现了未解决的问题 | `upsert-node --kind question` |",
        "| 实现方案跟之前讨论的不一样 | 更新对应节点的 Summary，或建新 branch |",
        "| 目标本身变了 | 更新 `root-goal` 的 Summary，并建 decision 记录变更原因 |",
        "",
        "如果一轮对话结束，上面一条都没命中 → 不需要写节点，只需 `capture-session`。",
        "如果连 session 都不值得写（纯闲聊或极小改动）→ 跳过。",
    ]


def render_context_pack(project_root: Path, nodes: list[TreeNode], sessions: list[SessionNote], discussion_dir: str = DEFAULT_DIR) -> str:
    validate_nodes(nodes)
    roots = [node for node in nodes if not node.parent]
    root = roots[0] if roots else None
    outcome_nodes = sorted(
        [node for node in nodes if node.status in {"accepted", "parked", "rejected"}],
        key=lambda item: (item.updated, item.title.lower()),
        reverse=True,
    )
    recent_sessions = sorted(sessions, key=lambda item: item.date, reverse=True)[:5]

    lines = [
        "# AI Context Pack",
        "",
        "给下一轮人和 AI 的自动恢复入口。",
        "",
        "## Project",
        "",
        f"- root: `{project_root}`",
        f"- source of truth: `{discussion_dir}/nodes/*.md`",
        f"- timeline: `{discussion_dir}/{LOG_NOTE_NAME}`",
        f"- first read: this file (`{discussion_dir}/{CONTEXT_NOTE_NAME}`)",
        "",
        "## Root Goal",
        "",
    ]

    if root is None:
        lines.append("- 尚未建立 root 节点")
    else:
        lines.append(f"- [[{root.relative_path[:-3]}|{root.title}]]")
        if first_nonempty_line(root.summary):
            lines.append(f"  - summary: {first_nonempty_line(root.summary)}")

    lines.extend(["", "## Active Leaf Branches", ""])
    active_leaves = active_leaf_paths(nodes)
    if not active_leaves:
        lines.append("- 暂无 active 叶子分支")
    else:
        for node, branch in active_leaves:
            branch_text = " -> ".join(item.title for item in branch)
            lines.append(f"- [[{node.relative_path[:-3]}|{node.title}]]")
            lines.append(f"  - path: `{branch_text}`")
            summary = first_nonempty_line(node.summary)
            if summary:
                lines.append(f"  - summary: {summary}")

    lines.extend(["", "## Settled Outcomes", ""])
    if not outcome_nodes:
        lines.append("- 暂无已收敛结果")
    else:
        for node in outcome_nodes[:8]:
            lines.append(f"- {status_icon(node.status)} [[{node.relative_path[:-3]}|{node.title}]]")
            summary = first_nonempty_line(node.summary)
            if summary:
                lines.append(f"  - summary: {summary}")

    lines.extend(["", "## Recent Sessions", ""])
    if not recent_sessions:
        lines.append("- 暂无 session 记录")
    else:
        for session in recent_sessions:
            lines.append(f"- [[{session.relative_path[:-3]}|{session.title}]] (`{session.date}`)")
            summary = first_nonempty_line(session.summary)
            if summary:
                lines.append(f"  - summary: {summary}")
            if session.related_nodes:
                lines.append(f"  - related nodes: `{', '.join(session.related_nodes)}`")

    lines.extend(["", "## Drift Check", ""])
    lines.extend(render_drift_check(root, active_leaves, outcome_nodes))

    lines.extend(["", "## Node Extraction Checklist", ""])
    lines.extend(render_extraction_checklist())

    lines.extend(
        [
            "",
            "## Resume Protocol",
            "",
            "1. 先读 root 和 active leaf branches。",
            "2. 检查 Drift Check section，如果有偏离警告，先确认再继续。",
            "3. 只钻进当前相关节点，不要把整棵树全读一遍。",
            "4. 如果讨论里出现新方向、拍板或废弃，立刻更新对应节点。",
            "5. 一轮工作结束时，用 `capture-session` 自动写回本轮变化。",
            "",
        ]
    )
    return "\n".join(lines)


def layout_canvas(nodes: list[TreeNode]) -> dict[str, Any]:
    validate_nodes(nodes)
    children = build_children(nodes)
    positions: dict[str, tuple[int, int]] = {}
    counters: dict[int, int] = defaultdict(int)

    def walk(node: TreeNode, depth: int) -> None:
        row = counters[depth]
        counters[depth] += 1
        positions[node.id] = (depth * 420, row * 220)
        for child in children.get(node.id, []):
            walk(child, depth + 1)

    for root in children[""]:
        walk(root, 0)

    canvas_nodes = []
    for node in nodes:
        x, y = positions[node.id]
        canvas_nodes.append(
            {
                "id": node.id,
                "type": "file",
                "file": node.relative_path,
                "x": x,
                "y": y,
                "width": 320,
                "height": 180,
                "color": "1" if node.status == "active" else "2" if node.status == "accepted" else "4" if node.status == "parked" else "6",
            }
        )

    canvas_edges = []
    for node in nodes:
        if not node.parent:
            continue
        canvas_edges.append(
            {
                "id": f"{node.parent}__{node.id}",
                "fromNode": node.parent,
                "fromSide": "right",
                "toNode": node.id,
                "toSide": "left",
            }
        )

    return {"nodes": canvas_nodes, "edges": canvas_edges}


def rebuild_views(discussion_root: Path, project_root: Path, discussion_dir: str = DEFAULT_DIR, project_name: str = "") -> None:
    nodes = load_nodes(discussion_root)
    sessions = load_sessions(discussion_root)
    name = project_name or project_root.name
    write_file(
        discussion_root / "tree.md",
        render_human_tree(name, project_root, nodes, sessions, discussion_root),
    )
    write_file(
        discussion_root / "tree.canvas",
        json.dumps(layout_canvas(nodes), ensure_ascii=False, indent=2) + "\n",
    )
    write_file(discussion_root / CONTEXT_NOTE_NAME, render_context_pack(project_root, nodes, sessions, discussion_dir))
    # Ensure log exists (never overwrite)
    log_path = discussion_root / LOG_NOTE_NAME
    if not log_path.exists():
        write_file(log_path, "# Log\n\n变更时间线。只追加，不重写。\n\n")



def ensure_gitignore(project_root: Path, discussion_dir: str) -> None:
    """Append the discussion dir to .gitignore if not already there."""
    gitignore = project_root / ".gitignore"
    entry = f"{discussion_dir}/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry in content.splitlines():
            return
        if not content.endswith("\n"):
            content += "\n"
        content += f"\n# discussion tree (auto-maintained by tree-of-discussion skill)\n{entry}\n"
        gitignore.write_text(content, encoding="utf-8")
    else:
        gitignore.write_text(f"# discussion tree (auto-maintained by tree-of-discussion skill)\n{entry}\n", encoding="utf-8")


def ensure_tree(project_root: Path, discussion_dir: str, project_name: str) -> tuple[Path, bool]:
    discussion_root = project_root / discussion_dir
    nodes_dir = discussion_root / "nodes"
    sessions_dir = discussion_root / "sessions"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    created = False
    root_path = nodes_dir / ROOT_NOTE_NAME
    if not root_path.exists():
        write_file(root_path, root_note(project_name))
        created = True

    ensure_gitignore(project_root, discussion_dir)
    rebuild_views(discussion_root, project_root, discussion_dir, project_name)
    if created:
        append_log(discussion_root, "ensure (init)", f"Created discussion tree for {project_name}")
    return discussion_root, created


def init_tree(project_root: Path, discussion_dir: str, project_name: str) -> Path:
    discussion_root, _ = ensure_tree(project_root, discussion_dir, project_name)
    return discussion_root


def ensure_parent_exists(nodes_dir: Path, parent: str) -> None:
    if not parent:
        return
    if not (nodes_dir / f"{parent}.md").exists():
        raise ValueError(f"Parent node does not exist: {parent}")


def session_link_for_node(session_path: Path) -> str:
    return f"[[../sessions/{session_path.stem}]]"


def update_node_file(
    *,
    discussion_root: Path,
    node_id: str,
    title: str | None = None,
    parent: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    summary: str | None = None,
    why: str | None = None,
    next_items: list[str] | None = None,
    related_session_link: str | None = None,
    expect_updated: str | None = None,
) -> Path:
    nodes_dir = discussion_root / "nodes"
    path = nodes_dir / f"{node_id}.md"
    today = now_date()
    now_ts = now_datetime()
    discovered_order: list[str] = []

    if path.exists():
        meta, discovered_order, sections = load_node_document(path)
        # Optimistic lock: warn if the file was modified since the caller last saw it
        if expect_updated is not None:
            actual_updated = str(meta.get("updated", "")).strip()
            if actual_updated and actual_updated != expect_updated.strip():
                import sys
                print(
                    f"WARNING: node '{node_id}' was updated by another session "
                    f"(expected updated={expect_updated}, actual={actual_updated}). "
                    f"Proceeding — review the node for conflicting edits.",
                    file=sys.stderr,
                )
    else:
        initial_title = (title or node_id).strip() or node_id
        initial_parent = "" if node_id == "root-goal" else (parent or "root-goal").strip()
        if node_id != "root-goal":
            ensure_parent_exists(nodes_dir, initial_parent)
        meta = {
            "id": node_id,
            "title": initial_title,
            "parent": initial_parent,
            "kind": "root" if node_id == "root-goal" else (kind or "idea").strip(),
            "status": (status or "active").strip(),
            "created": today,
            "updated": now_ts,
        }
        sections = {section: "" for section in NODE_SECTION_ORDER}

    meta["id"] = node_id
    meta.setdefault("created", today)
    meta["updated"] = now_ts

    if title is not None and title.strip():
        meta["title"] = title.strip()
    else:
        meta.setdefault("title", node_id)

    if node_id == "root-goal":
        meta["parent"] = ""
        meta["kind"] = "root"
    else:
        candidate_parent = parent.strip() if parent is not None else str(meta.get("parent", "")).strip()
        candidate_parent = candidate_parent or "root-goal"
        ensure_parent_exists(nodes_dir, candidate_parent)
        meta["parent"] = candidate_parent
        if kind is not None and kind.strip():
            meta["kind"] = kind.strip()
        else:
            meta.setdefault("kind", "idea")

    if status is not None and status.strip():
        meta["status"] = status.strip()
    else:
        meta.setdefault("status", "active")

    sections.setdefault("Summary", "")
    sections.setdefault("Why this branch exists", "")
    sections.setdefault("Next", "")
    sections.setdefault("Related sessions", "")

    if summary is not None:
        sections["Summary"] = summary.strip()
    if why is not None:
        sections["Why this branch exists"] = why.strip()
    if next_items:
        sections["Next"] = merge_bullets(sections.get("Next", ""), next_items)
    if related_session_link:
        sections["Related sessions"] = merge_bullets(sections.get("Related sessions", ""), [related_session_link])

    write_file(path, render_node_document(meta, sections, discovered_order))
    return path


def upsert_node(
    project_root: Path,
    discussion_dir: str,
    project_name: str,
    node_id: str | None,
    title: str | None,
    parent: str | None,
    kind: str | None,
    status: str | None,
    summary: str | None,
    why: str | None,
    next_items: list[str],
) -> Path:
    discussion_root, _ = ensure_tree(project_root, discussion_dir, project_name)
    resolved_id = (node_id or "").strip() or slugify(title or "")
    if not resolved_id:
        raise ValueError("Either --node-id or --title is required")
    node_path = discussion_root / "nodes" / f"{resolved_id}.md"
    is_new = not node_path.exists()

    # Capture old state before writing
    old_summary = ""
    old_status = ""
    old_kind = ""
    old_updated = ""
    if not is_new:
        raw = node_path.read_text(encoding="utf-8")
        old_meta, old_body = parse_frontmatter(raw)
        _, old_sections = parse_sections(old_body)
        old_summary = old_sections.get("Summary", "").strip()
        old_status = str(old_meta.get("status", "")).strip()
        old_kind = str(old_meta.get("kind", "")).strip()
        old_updated = str(old_meta.get("updated", "")).strip()

    path = update_node_file(
        discussion_root=discussion_root,
        node_id=resolved_id,
        title=title,
        parent=parent,
        kind=kind,
        status=status,
        summary=summary,
        why=why,
        next_items=next_items,
        expect_updated=old_updated if old_updated else None,
    )
    rebuild_views(discussion_root, project_root, discussion_dir, project_name)

    # Build log detail with before → after diffs
    log_action = "create" if is_new else "update"
    diffs: list[str] = []
    if is_new:
        diffs.append(title or resolved_id)
    else:
        if status and status.strip() and status.strip() != old_status:
            diffs.append(f"status: {old_status} → {status.strip()}")
        if kind and kind.strip() and kind.strip() != old_kind:
            diffs.append(f"kind: {old_kind} → {kind.strip()}")
        if summary is not None:
            new_s = summary.strip()
            if new_s != old_summary:
                old_short = (old_summary[:40] + "...") if len(old_summary) > 40 else old_summary
                new_short = (new_s[:40] + "...") if len(new_s) > 40 else new_s
                diffs.append(f'summary: "{old_short}" → "{new_short}"')
    detail = f"{resolved_id}: {'; '.join(diffs)}" if diffs else f"{resolved_id}: {title or resolved_id}"
    append_log(discussion_root, f"upsert-node ({log_action})", detail)
    return path


def unique_session_path(sessions_dir: Path, title: str) -> Path:
    base = f"{now_date()}-{slugify(title)}"
    candidate = sessions_dir / f"{base}.md"
    counter = 2
    while candidate.exists():
        candidate = sessions_dir / f"{base}-{counter}.md"
        counter += 1
    return candidate


def capture_session(
    project_root: Path,
    discussion_dir: str,
    project_name: str,
    title: str | None,
    summary: str,
    related_nodes: list[str],
    changes: list[str],
    follow_ups: list[str],
) -> Path:
    discussion_root, _ = ensure_tree(project_root, discussion_dir, project_name)
    sessions_dir = discussion_root / "sessions"
    normalized_nodes = dedupe_keep_order(related_nodes or ["root-goal"])
    nodes_dir = discussion_root / "nodes"
    for node_id in normalized_nodes:
        if not (nodes_dir / f"{node_id}.md").exists():
            raise ValueError(f"Related node does not exist: {node_id}")

    timestamp = now_datetime()
    session_title = title.strip() if title and title.strip() else f"Session: {timestamp}"
    session_path = unique_session_path(sessions_dir, session_title)
    write_file(
        session_path,
        session_note(
            title=session_title,
            timestamp=timestamp,
            related_nodes=normalized_nodes,
            summary=summary,
            changes=changes,
            follow_ups=follow_ups,
        ),
    )

    session_link = session_link_for_node(session_path)
    for node_id in normalized_nodes:
        update_node_file(
            discussion_root=discussion_root,
            node_id=node_id,
            related_session_link=session_link,
        )

    rebuild_views(discussion_root, project_root, discussion_dir, project_name)
    append_log(discussion_root, "capture-session", f"{session_title} (nodes: {', '.join(normalized_nodes)})")
    return session_path


def render_context_stdout(discussion_root: Path) -> str:
    path = discussion_root / CONTEXT_NOTE_NAME
    return path.read_text(encoding="utf-8")


def add_root_safety_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-skill-project",
        action="store_true",
        help="Allow writing into a directory that looks like a skill project root",
    )
    parser.add_argument(
        "--allow-workspace-root",
        action="store_true",
        help="Allow writing into a workspace-like root with multiple child projects",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize and automatically maintain a Markdown discussion tree."
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a discussion tree")
    init_parser.add_argument("--root", required=True, help="Target project root")
    init_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    init_parser.add_argument("--project-name", default="", help="Optional project name override")
    add_root_safety_args(init_parser)

    ensure_parser = subparsers.add_parser("ensure", help="Ensure the discussion tree exists and is up to date")
    ensure_parser.add_argument("--root", required=True, help="Target project root")
    ensure_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    ensure_parser.add_argument("--project-name", default="", help="Optional project name override")
    add_root_safety_args(ensure_parser)

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild tree views")
    rebuild_parser.add_argument("--root", required=True, help="Target project root")
    rebuild_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    add_root_safety_args(rebuild_parser)

    add_parser = subparsers.add_parser("add-node", help="Add a node and rebuild views")
    add_parser.add_argument("--root", required=True, help="Target project root")
    add_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    add_parser.add_argument("--title", required=True, help="Node title")
    add_parser.add_argument("--parent", required=True, help="Parent node id")
    add_parser.add_argument("--kind", default="idea", help="Node kind")
    add_parser.add_argument("--status", default="active", help="Node status")
    add_root_safety_args(add_parser)

    upsert_parser = subparsers.add_parser("upsert-node", help="Create or update a node automatically")
    upsert_parser.add_argument("--root", required=True, help="Target project root")
    upsert_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    upsert_parser.add_argument("--project-name", default="", help="Optional project name override")
    upsert_parser.add_argument("--node-id", default="", help="Explicit node id; falls back to slugified title")
    upsert_parser.add_argument("--title", default="", help="Node title")
    upsert_parser.add_argument("--parent", default="", help="Parent node id; defaults to root-goal for new nodes")
    upsert_parser.add_argument("--kind", default="", help="Node kind")
    upsert_parser.add_argument("--status", default="", help="Node status")
    upsert_parser.add_argument("--summary", default=None, help="Replace the Summary section")
    upsert_parser.add_argument("--why", default=None, help="Replace the Why this branch exists section")
    upsert_parser.add_argument("--next", action="append", default=[], help="Append an item under Next")
    add_root_safety_args(upsert_parser)

    session_parser = subparsers.add_parser("capture-session", help="Write one discussion session back into the tree")
    session_parser.add_argument("--root", required=True, help="Target project root")
    session_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    session_parser.add_argument("--project-name", default="", help="Optional project name override")
    session_parser.add_argument("--title", default="", help="Session title")
    session_parser.add_argument("--summary", required=True, help="Session summary")
    session_parser.add_argument("--node", action="append", default=[], help="Touched node id; can be repeated")
    session_parser.add_argument("--change", action="append", default=[], help="What changed in the tree; can be repeated")
    session_parser.add_argument("--follow-up", action="append", default=[], help="Next follow-up; can be repeated")
    add_root_safety_args(session_parser)

    context_parser = subparsers.add_parser("context", help="Refresh and optionally print the AI context pack")
    context_parser.add_argument("--root", required=True, help="Target project root")
    context_parser.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    context_parser.add_argument("--project-name", default="", help="Optional project name override")
    context_parser.add_argument("--stdout", action="store_true", help="Print the context pack content")
    add_root_safety_args(context_parser)

    return parser


def parse_args() -> argparse.Namespace:
    import sys

    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-"):
        return build_parser().parse_args(argv)
    compatibility = argparse.ArgumentParser(
        description="Backward-compatible init mode for the discussion tree bootstrap."
    )
    compatibility.add_argument("--root", required=True, help="Target project root")
    compatibility.add_argument("--dir", default=DEFAULT_DIR, help="Discussion directory name")
    compatibility.add_argument("--project-name", default="", help="Optional project name override")
    add_root_safety_args(compatibility)
    args = compatibility.parse_args(argv)
    args.command = "init"
    return args


def main() -> None:
    args = parse_args()
    project_root = Path(args.root).expanduser().resolve()
    validate_target_root(
        project_root,
        allow_skill_project=getattr(args, "allow_skill_project", False),
        allow_workspace_root=getattr(args, "allow_workspace_root", False),
    )
    project_root.mkdir(parents=True, exist_ok=True)
    project_name = getattr(args, "project_name", "").strip() or project_root.name

    if args.command == "init":
        discussion_root = init_tree(project_root, args.dir, project_name)
        print(f"Initialized discussion tree at: {discussion_root}")
        print(f"Read context.md first. tree.md for human overview.")
        return

    if args.command == "ensure":
        discussion_root, created = ensure_tree(project_root, args.dir, project_name)
        if created:
            print(f"Created discussion tree at: {discussion_root}")
        else:
            print(f"Discussion tree is ready at: {discussion_root}")
        print(f"Context pack: {discussion_root / CONTEXT_NOTE_NAME}")
        return

    if args.command == "rebuild":
        discussion_root = project_root / args.dir
        rebuild_views(discussion_root, project_root, args.dir)
        print(f"Rebuilt discussion tree views at: {discussion_root}")
        print(f"Context pack: {discussion_root / CONTEXT_NOTE_NAME}")
        return

    if args.command == "add-node":
        path = upsert_node(
            project_root=project_root,
            discussion_dir=args.dir,
            project_name=project_name,
            node_id=None,
            title=args.title,
            parent=args.parent,
            kind=args.kind,
            status=args.status,
            summary=None,
            why=None,
            next_items=[],
        )
        print(f"Created node: {path}")
        return

    if args.command == "upsert-node":
        path = upsert_node(
            project_root=project_root,
            discussion_dir=args.dir,
            project_name=project_name,
            node_id=args.node_id,
            title=args.title,
            parent=args.parent,
            kind=args.kind,
            status=args.status,
            summary=args.summary,
            why=args.why,
            next_items=args.next,
        )
        print(f"Upserted node: {path}")
        return

    if args.command == "capture-session":
        path = capture_session(
            project_root=project_root,
            discussion_dir=args.dir,
            project_name=project_name,
            title=args.title,
            summary=args.summary,
            related_nodes=args.node,
            changes=args.change,
            follow_ups=args.follow_up,
        )
        print(f"Captured session: {path}")
        return

    if args.command == "context":
        discussion_root, _ = ensure_tree(project_root, args.dir, project_name)
        print(f"Context pack ready at: {discussion_root / CONTEXT_NOTE_NAME}")
        if args.stdout:
            print()
            print(render_context_stdout(discussion_root))
        return

    raise SystemExit("Unknown command")


if __name__ == "__main__":
    main()
