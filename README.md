# tree-of-discussion

AI-maintained discussion tree for long-running projects.

Tracks goals, directions, decisions, and open questions across sessions. Lets both humans and AI restore context cheaply.

## What it generates

```
project/.discussion/
├── tree.md       # Human-readable overview
├── context.md    # AI context recovery + drift check
├── log.md        # Append-only changelog (before → after)
├── nodes/        # One file per direction / decision / question
└── sessions/     # One file per discussion round
```

Hidden directory, auto-added to `.gitignore`.

## Quick start

```bash
# Init
python3 scripts/init_discussion_tree.py ensure --root /path/to/project

# Set the real goal
python3 scripts/init_discussion_tree.py upsert-node \
  --root /path/to/project \
  --node-id root-goal \
  --summary "Build a lightweight full-stack todo app"

# Add a key direction
python3 scripts/init_discussion_tree.py upsert-node \
  --root /path/to/project \
  --node-id auth-choice \
  --title "Auth approach" \
  --parent root-goal \
  --kind question \
  --summary "JWT vs session — undecided."

# End of session
python3 scripts/init_discussion_tree.py capture-session \
  --root /path/to/project \
  --summary "Settled on tech stack, auth still open" \
  --node root-goal --node auth-choice \
  --change "Added auth question node" \
  --follow-up "Compare JWT vs session complexity"

# Next session — restore context
python3 scripts/init_discussion_tree.py context \
  --root /path/to/project --stdout
```

## When to write a node

| Signal | Action |
|---|---|
| New direction | `upsert-node --kind branch` |
| New idea | `upsert-node --kind idea` |
| Decision made | `upsert-node --kind decision --status accepted` |
| Rejected | `upsert-node --status rejected` |
| Parked | `upsert-node --status parked` |
| Open question | `upsert-node --kind question` |
| Goal changed | Update `root-goal` + add a decision explaining why |

Nothing happened → don't write.

## Node model

Each node is a `.md` file with frontmatter:

- `id`, `title`, `parent`, `kind`, `status`, `created`, `updated`

**kind**: `root` / `goal` / `idea` / `branch` / `decision` / `question`

**status**: `active` / `accepted` / `parked` / `rejected`

Body sections: `Summary`, `Why this branch exists`, `Next`, `Related sessions`

## Commands

| Command | Purpose |
|---|---|
| `ensure` | Init or repair the tree |
| `upsert-node` | Create or update a node |
| `capture-session` | Record a discussion round |
| `context` | Refresh context.md (`--stdout` to print) |
| `rebuild` | Rebuild all views from source data |

## Changelog format

`log.md` records diffs, not just operations:

```
[2026-04-15 10:00] upsert-node (update) | root-goal: summary: "monitoring dashboard" → "full observability platform"
[2026-04-15 10:05] upsert-node (update) | auth-choice: status: active → accepted
```

## Obsidian (optional)

Nodes and sessions already contain `[[wikilinks]]`. Open `.discussion/` as an Obsidian vault to get Graph View, backlinks, and quick navigation for free.

## License

MIT
