# Feature: Extension architecture

**Source:** [`atlas_os/extensions/`](../../atlas_os/extensions/) ·
**CLI:** `atlas extensions list`, `atlas extensions info <name>`

Atlas OS is split into a **lean core** and **optional, domain-specific
extensions**. The core is everything that makes the system a personal AI OS over
a markdown vault: vault parsing, git sync, the RAG indexer, the CLI, the
dashboard, and the audit trail. Everything domain-specific — trading briefings,
voice/TTS, the job tracker — lives in an *extension* that plugs into the core
through one small contract.

The rule the architecture enforces: **the core never imports a domain module.**
It discovers and loads them at startup through the `AtlasExtension` interface, so
the core stays decoupled, the base install stays slim, and anyone can ship a new
extension — bundled or third-party — without touching core code.

---

## The contract — `AtlasExtension`

Every extension is a subclass of
[`AtlasExtension`](../../atlas_os/extensions/base.py). The only required surface
is its identity; every hook has a no-op default, so a minimal extension is a few
lines:

```python
from atlas_os.extensions.base import AtlasExtension


class HelloExtension(AtlasExtension):
    @property
    def name(self) -> str:
        return "hello"

    @property
    def description(self) -> str:
        return "A tiny example extension."
```

The full surface:

| Member | Required | Purpose |
|---|---|---|
| `name` | ✅ | Stable lowercase slug; the key for `atlas extensions info <name>` and de-duplication. |
| `description` | ✅ | One-line summary shown in `atlas extensions list`. |
| `version` | — | Version string (defaults to `"0.0.0"`). |
| `register_commands(cli)` | — | Add subcommands to the `atlas` Typer app (`@cli.command()` or `cli.add_typer(...)`). |
| `register_skills()` | — | Return scheduled-task skill definitions as plain dicts. |
| `register_schedules()` | — | Return cron-like schedule definitions as plain dicts. |
| `on_load()` / `on_unload()` | — | Lifecycle hooks run when the extension is loaded / unloaded. |

Skills and schedules are returned as **plain dicts**, not typed objects, so the
core can list them without importing the extension's types — keeping the
decoupling intact.

---

## Discovery and loading

[`atlas_os/extensions/__init__.py`](../../atlas_os/extensions/__init__.py) merges
two discovery channels, in priority order:

1. **Entry points** — any installed package that registers a class under the
   `atlas_os.extensions` entry-point group. This is how third-party extensions
   ship, and how the bundled ones are found once Atlas OS is installed. Declared
   in [`pyproject.toml`](../../pyproject.toml):

   ```toml
   [project.entry-points."atlas_os.extensions"]
   trading = "atlas_os.extensions.trading:TradingExtension"
   voice   = "atlas_os.extensions.voice:VoiceExtension"
   jobs    = "atlas_os.extensions.jobs:JobsExtension"
   ```

2. **Built-ins** — a registry (`BUILTIN_EXTENSIONS`) of the vendored modules, so
   a bare source checkout discovers them even without installed entry-point
   metadata.

An entry point **overrides** a built-in of the same name, so you can shadow a
bundled extension with your own.

Loading is **fault-tolerant**. An extension whose import raises — a missing
optional dependency, a syntax error in a third-party package — is skipped and its
error recorded, never crashing the `atlas` CLI. The CLI wires it all up at the
end of [`cli.py`](../../atlas_os/cli.py): after every core command is defined,
`load_all_extensions(app)` registers each extension's commands onto the app, so
extension subcommands are present whenever `atlas` runs.

### Public API

```python
from atlas_os import extensions

extensions.list_extensions()      # every discovered extension (loaded or not)
extensions.load_extension("trading")   # load + cache one, returns the instance
extensions.load_all_extensions(app)    # load all, register commands onto `app`
extensions.get_extension("trading")    # an already-loaded instance
extensions.loaded_extensions()         # all currently-loaded instances
extensions.unload_extension("trading") # unload + run its on_unload hook
extensions.discovery_errors()          # {name: error} for anything that failed
```

---

## The bundled extensions

| Extension | Status | Extra | Commands |
|---|---|---|---|
| `trading` | working | `atlas-os[trading]` | `atlas trading` — market-research briefings into the vault. |
| `voice` | stub | `atlas-os[voice]` | `atlas voice say`, `atlas voice status` — TTS (placeholder). |
| `jobs` | stub | `atlas-os[jobs]` | `atlas jobs list`, `atlas jobs add` — application tracker (placeholder). |

Each declares its heavier dependencies as an **opt-in extra**, so the core
install stays slim and you only pull in what you use:

```bash
pip install 'atlas-os[trading]'   # adds yfinance for the trading extension
```

The `trading` extension is the reference example of a real domain module: it was
moved out of the core CLI into `atlas_os/extensions/trading/` in v3.0, so
`atlas trading` is now contributed by the extension rather than the core.

---

## Inspecting extensions

```bash
# What's installed, and did it load cleanly?
atlas extensions list

# One extension's metadata, skills, and schedules
atlas extensions info trading
```

`list` shows each discovered extension, its source (`built-in` or `entry-point`),
and — for anything that failed to load — the recorded error. `info` loads the
named extension on demand and prints its version, description, the skills it
contributes, and its schedules.

---

## Writing your own extension

1. Subclass `AtlasExtension` (see the minimal example above) and implement
   `register_commands` to add your CLI surface.
2. Register it under the `atlas_os.extensions` entry-point group in your
   package's `pyproject.toml`, pointing at `your_pkg.module:YourExtension`.
3. `pip install` your package into the same environment as Atlas OS. It is
   discovered and loaded automatically the next time `atlas` runs — no core
   changes required.

Because discovery is fault-tolerant, a bug in your extension degrades to "skipped
with an error in `atlas extensions list`" rather than breaking the whole CLI.

---

See also: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §12 for where extensions
sit in the overall design, and [`docs/CLI-REFERENCE.md`](../CLI-REFERENCE.md) for
the `atlas extensions` command reference.
