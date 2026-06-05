# Feature Deep-Dives

One document per feature, explaining **how it actually works** — the internals,
data formats, configuration, and edge cases — grounded in the source code. For
setup and the command reference, see [`docs/SETUP.md`](../SETUP.md) and
[`docs/SCRIPTS.md`](../SCRIPTS.md).

| Feature | Doc | Source | CLI |
|---|---|---|---|
| Knowledge vault & frontmatter schemas | [knowledge-vault.md](knowledge-vault.md) | `schemas/`, `templates/` | `atlas schemas`, `atlas init` |
| Session capture | [session-capture.md](session-capture.md) | `scripts/save_sessions.py` | `atlas session` |
| Local RAG search | [rag-search.md](rag-search.md) | `scripts/embed_vault.py` | `atlas embed` |
| Knowledge graph | [knowledge-graph.md](knowledge-graph.md) | `scripts/build_graph.py` | `atlas graph` |
| Git automation | [git-automation.md](git-automation.md) | `scripts/vault_commit.py`, `vault_changelog.py` | `atlas commit`, `atlas changelog` |
| Scheduled tasks & skills catalog | [skills-and-automation.md](skills-and-automation.md) | `skills/`, `atlas_os/_skills.py` | `atlas skills` |
| Skills marketplace / registry | [skills-marketplace.md](skills-marketplace.md) | `atlas_os/marketplace.py`, `skills/registry.json` | `atlas skills search`, `publish`, `registry` |
| Email reports | [email-reports.md](email-reports.md) | `scripts/send_email.py` | `atlas email` |
| Extension architecture | [extensions.md](extensions.md) | `atlas_os/extensions/` | `atlas extensions` |
| Trading research SDK *(optional extension)* | [trading-sdk.md](trading-sdk.md) | `atlas_os/extensions/trading/`, `scripts/trading_briefing.py` | `atlas trading` |
| Health check & dashboard | [health-and-dashboard.md](health-and-dashboard.md) | `scripts/health_check.py`, `templates/ops-dashboard.html` | `atlas health`, `atlas doctor` |
| Web dashboard | [dashboard.md](dashboard.md) | `atlas_os/dashboard/` | `atlas dashboard` |

## How the features fit together

```
          Cowork conversations + research ──(atlas session save)──┐
                                                                  ▼
              ┌──────────────── the vault (source of truth) ────────────────┐
              │  markdown notes · session logs · frontmatter · [[wikilinks]] │
              └───────┬───────────────┬───────────────┬───────────────┬─────┘
                      │               │               │               │
                 RAG search     knowledge graph   git automation   skills catalog
                (embed → vectors) (links → graph) (commit/changelog) (discoverable)
                      │               │               │               │
                      └───────────────┴───────┬───────┴───────────────┘
                                              │
                              scheduled skills orchestrate them,
                              email reports go out, health check
                              watches it all, the dashboard shows it
```

The vault is the source of truth; RAG, the graph, and git history are derived and
reproducible. **Session capture** feeds it from the other direction — folding your
Cowork conversations and research back into the vault as notes, so they're indexed
and searchable alongside everything else. Scheduled **skills** tie the pieces
together on a cadence; **email** delivers the results; the **health check** and
**dashboard** observe the whole system. The **trading SDK** is an optional
research workload that writes its briefings back into the vault.

See also: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) for the high-level design,
and [`docs/DATA-CLASSIFICATION.md`](../DATA-CLASSIFICATION.md) for what stays
local.
