# Feature: Knowledge Graph

**Source:** [`scripts/build_graph.py`](../../scripts/build_graph.py) ·
**CLI:** `atlas graph` · **Output:** `$RAG_DIR/graph.json`

Atlas OS derives a **wikilink graph** from your notes — who links to whom — so
you (and the dashboard, and agents) can surface backlinks and "related notes".
It is rebuilt automatically after every `atlas embed --full`/`--incremental`, or
on demand with `atlas graph`.

---

## How it works

### 1. Discovery

`os.walk` over `VAULT_PATH`, pruning
`SKIP_DIRS = {.obsidian, .git, .rag, .claude, node_modules, .schemas}`, collecting
every `.md` file (sorted). Each becomes a **node** (its vault-relative path,
e.g. `wiki/foo.md`).

### 2. Wikilink extraction

Links are matched with the regex `\[\[([^\]]+)\]\]`. Each captured target is
normalised:

- alias stripped — `[[note|Display]]` → `note`
- heading stripped — `[[note#Section]]` → `note`

(both orders are handled, e.g. `[[note#h|alias]]` → `note`).

### 3. Link resolution

A file index maps **two lowercased keys** to each file:

- its **basename** without extension (`foo`), and
- its **full relative path** without extension (`wiki/foo`).

`resolve_link()` tries the normalised target against the index (matching either
form), then falls back to the target's basename. Unresolved links are **silently
dropped** — no edge, no phantom node.

### 4. Edges

For each note, resolved targets become directed edges `{source, target}`,
deduplicated per source, with self-links excluded.

---

## Output: `graph.json`

Exactly four top-level keys (written atomically, compact JSON):

| Key | Shape | Meaning |
|---|---|---|
| `nodes` | `list[str]` | every `.md` file's relative path |
| `edges` | `list[{source, target}]` | directed wikilinks (resolved only) |
| `adjacency` | `dict[path, list[path]]` | outbound links per source (only sources with edges) |
| `backlinks` | `dict[path, list[path]]` | inbound links per target (only targets with edges) |

```json
{
  "nodes": ["wiki/index.md", "research/rag.md", "research/embeddings.md"],
  "edges": [
    {"source": "research/rag.md", "target": "research/embeddings.md"}
  ],
  "adjacency": {"research/rag.md": ["research/embeddings.md"]},
  "backlinks": {"research/embeddings.md": ["research/rag.md"]}
}
```

Nodes are plain strings (not objects); edges carry no weight or type.

### Stats

`build_graph()` returns `(graph, stats)`. The `stats` dict:

- `total_nodes`, `total_edges`
- `avg_connections` — `edges / nodes`
- `most_connected` — top 10 `(node, out_degree)` by **outbound** link count

`atlas embed --full` prints e.g. `Graph: 412 nodes, 1,083 edges`.

---

## Orphans & unresolved links

- **Orphan notes** (no links in or out) still appear in `nodes`, but not in
  `adjacency`/`backlinks`.
- **Unresolved links** (target file doesn't exist) are dropped silently — useful
  if you write `[[future note]]` placeholders; they simply won't form edges until
  the target exists.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_PATH` | — (**required**) | vault to scan |
| `RAG_DIR` | `$VAULT_PATH/.rag` | where `graph.json` is written |

`graph.json` is **git-ignored** — derived data, rebuilt from the vault.

## Usage

```bash
atlas graph                       # rebuild just the graph (writes graph.json)
atlas graph --open                # build, then open the interactive viewer in a browser
atlas embed --full                # also rebuilds the graph at the end
python3 scripts/build_graph.py    # direct invocation
```

`--open` accepts `--host` / `--port` (where to serve, default `127.0.0.1:8501`)
and `--no-build` (serve without rebuilding `graph.json` first). It needs the
dashboard extra (`pip install 'atlas-os[dashboard]'`).

---

## Visual viewer

The [dashboard](dashboard.md) ships an interactive **D3 force-directed viewer** at
`/graph` (open it directly with `atlas graph --open`). It is served by two routes:

- **`GET /graph`** — the page itself ([`templates/graph.html`](../../atlas_os/dashboard/templates/graph.html)),
  a self-contained template with inline CSS/JS; D3 is loaded from a CDN.
- **`GET /api/graph`** — the graph as JSON, built by `data.graph_data()`. Rather
  than read `graph.json`, this **scans the vault live** (the same wikilink logic
  as `build_graph.py`) so the view is always current without a prior
  `atlas graph` run. Each node carries a `type`, link `degree`, and in/out counts;
  edges are `{source, target}` id pairs; a `types` colour legend and summary
  `stats` ride along. Huge vaults are capped to the most-connected nodes.

Nodes are **coloured by type** — derived from each note's path: session log,
source, skill, research, wiki, memory, or a plain note. The viewer supports
zoom/pan, dragging, a name search, per-type filter chips, and a click-through
detail panel listing a note's outbound links and backlinks.

See also: [rag-search.md](rag-search.md) · [dashboard.md](dashboard.md) ·
[`docs/SCRIPTS.md`](../SCRIPTS.md#build_graphpy)
