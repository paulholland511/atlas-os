# Eidetic OS — Obsidian Plugin

A lightweight Obsidian plugin that connects to your locally-running **Eidetic OS**
API server, letting you search your memory index, browse extracted facts, extract
facts from the current note, and view vault/RAG stats — all without leaving
Obsidian.

Nothing leaves your machine: every request goes to the localhost server you point
the plugin at (default `http://localhost:8501`).

## What it does

- **Command palette — _Eidetic: Search memory_** — opens a search modal over the
  RAG index (hybrid / vector / keyword modes). Click a result to open the file.
- **Command palette — _Eidetic: Show facts_** — opens the facts sidebar; browse or
  search your stored facts.
- **Command palette — _Eidetic: Extract facts from note_** — extracts facts from the
  active note (preview, or store them — see settings).
- **Command palette — _Eidetic: System stats_** — vault / RAG / fact counts and the
  last-embed time.
- **Ribbon icon** (brain) — opens the search modal.
- **Status bar** — shows connection status (connected / offline) and the active
  fact count; click to re-check.
- **Settings tab** — server URL, store-on-extract toggle, poll interval, and a
  "Test connection" button.

## Prerequisites

1. **Eidetic OS** installed with the dashboard extra (provides Flask):

   ```bash
   pip install 'eidetic-os[dashboard]'
   ```

2. **Start the API server** the plugin talks to:

   ```bash
   eidetic serve              # binds http://localhost:8501 by default
   eidetic serve --port 8888  # or pick another port
   ```

   Set `VAULT_PATH` to your vault so the server reads the right index/facts.

## Building the plugin

The plugin is shipped as TypeScript source; build the bundled `main.js` with:

```bash
cd obsidian-plugin
npm install
npm run build        # one-off production build → main.js
# or: npm run dev    # watch mode while developing
```

This produces `main.js` alongside `manifest.json` and `styles.css`.

## Installing into your vault

Copy the three built artifacts into a plugin folder inside your vault:

```bash
VAULT=~/Documents/Obsidian/Atlas        # your vault
DEST="$VAULT/.obsidian/plugins/eidetic-os"
mkdir -p "$DEST"
cp manifest.json main.js styles.css "$DEST/"
```

Then in Obsidian: **Settings → Community plugins → Reload**, and enable
**Eidetic OS**. (Community plugins must be enabled — turn off Restricted/Safe
mode.)

## Configuration

Open **Settings → Eidetic OS**:

- **Server URL** — where `eidetic serve` is listening (default
  `http://localhost:8501`).
- **Store facts on extract** — when on, _Extract facts from note_ ingests the
  facts into the fact store (deduplicated); when off, it only previews them.
- **Status poll interval** — how often the status bar re-checks the connection.
- **Test connection** — pings `/api/health`.

## API endpoints used

The plugin talks to these endpoints on the Eidetic OS server (see
[`eidetic_os/plugin_server.py`](../eidetic_os/plugin_server.py)):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + version |
| GET | `/api/search?q=&limit=&mode=` | RAG search |
| GET | `/api/facts?category=&limit=` | List facts |
| GET | `/api/facts/search?q=&limit=` | Semantic fact search |
| GET | `/api/stats` | Vault / vector / fact stats |
| POST | `/api/facts/extract` | Extract (and optionally store) facts |

## Troubleshooting

- **Status bar says "offline"** — the server isn't reachable. Confirm
  `eidetic serve` is running and the **Server URL** matches its host/port.
- **Search returns an error** — the RAG index may be empty. Build it with
  `eidetic embed --full`. `keyword` mode also needs an existing index (it runs
  BM25 over the indexed chunks).
- **Clicking a result does nothing** — the result's file path must exist in the
  currently-open vault; the plugin opens files by their vault-relative path.
