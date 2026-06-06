/*
 * Eidetic OS — Obsidian plugin.
 *
 * A lightweight bridge between your Obsidian vault and a locally-running Eidetic
 * OS API server (`eidetic serve`, default http://localhost:8501). It lets you
 * search the RAG memory index, browse and search extracted facts, extract facts
 * from the current note, and read vault/RAG stats — all without leaving Obsidian.
 *
 * Nothing here phones home: every request goes to the localhost server you point
 * it at. Build with `npm run build` (see obsidian-plugin/README.md).
 */

import {
  App,
  ItemView,
  Modal,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  WorkspaceLeaf,
  TFile,
  setIcon,
  requestUrl,
} from "obsidian";

// ── Settings ─────────────────────────────────────────────────────────────────

interface EideticSettings {
  serverUrl: string;
  // How often (ms) the status bar re-checks the server connection.
  pollIntervalMs: number;
  // When extracting facts from a note, also store them in the fact DB.
  storeOnExtract: boolean;
}

const DEFAULT_SETTINGS: EideticSettings = {
  serverUrl: "http://localhost:8501",
  pollIntervalMs: 30000,
  storeOnExtract: false,
};

const FACTS_VIEW_TYPE = "eidetic-facts-view";

// ── API response shapes (mirrors eidetic_os/plugin_server.py) ─────────────────

interface SearchHit {
  file: string;
  heading?: string;
  score: number;
  snippet: string;
}

interface SearchResponse {
  ok: boolean;
  query: string;
  mode?: string;
  results?: SearchHit[];
  error?: string;
}

interface Fact {
  id: number;
  fact: string;
  source: string;
  category: string;
  confidence: number;
  access_count: number;
  active: boolean;
  score?: number;
}

interface FactsResponse {
  ok: boolean;
  count?: number;
  facts?: Fact[];
  results?: Fact[];
}

interface StatsResponse {
  ok: boolean;
  version: string;
  vectors: {
    available: boolean;
    chunk_count?: number;
    file_count?: number;
    backend?: string;
    last_embed?: { iso: string; age: string; stale: boolean } | null;
  };
  facts: {
    total?: number;
    active?: number;
    by_category?: Record<string, number>;
  };
}

interface HealthResponse {
  ok: boolean;
  service?: string;
  version?: string;
}

// ── Thin API client ───────────────────────────────────────────────────────────

class EideticClient {
  constructor(private getBaseUrl: () => string) {}

  private url(path: string): string {
    return this.getBaseUrl().replace(/\/+$/, "") + path;
  }

  // requestUrl avoids the renderer's CORS preflight and works on mobile.
  private async getJson<T>(path: string): Promise<T> {
    const resp = await requestUrl({ url: this.url(path), method: "GET" });
    return resp.json as T;
  }

  async health(): Promise<HealthResponse> {
    return this.getJson<HealthResponse>("/api/health");
  }

  async search(query: string, limit = 10, mode = "hybrid"): Promise<SearchResponse> {
    const q = encodeURIComponent(query);
    return this.getJson<SearchResponse>(
      `/api/search?q=${q}&limit=${limit}&mode=${mode}`
    );
  }

  async listFacts(category = "", limit = 50): Promise<FactsResponse> {
    const cat = category ? `&category=${encodeURIComponent(category)}` : "";
    return this.getJson<FactsResponse>(`/api/facts?limit=${limit}${cat}`);
  }

  async searchFacts(query: string, limit = 10): Promise<FactsResponse> {
    const q = encodeURIComponent(query);
    return this.getJson<FactsResponse>(`/api/facts/search?q=${q}&limit=${limit}`);
  }

  async stats(): Promise<StatsResponse> {
    return this.getJson<StatsResponse>("/api/stats");
  }

  async extract(
    text: string,
    source: string,
    store: boolean
  ): Promise<{ ok: boolean; stored: boolean; count?: number; tally?: Record<string, number>; facts?: Fact[]; error?: string }> {
    const resp = await requestUrl({
      url: this.url("/api/facts/extract"),
      method: "POST",
      contentType: "application/json",
      body: JSON.stringify({ text, source, store }),
      throw: false,
    });
    return resp.json;
  }
}

// ── Search modal ──────────────────────────────────────────────────────────────

class SearchModal extends Modal {
  private results: SearchHit[] = [];
  private mode = "hybrid";

  constructor(
    app: App,
    private client: EideticClient,
    private openFile: (path: string) => void
  ) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass("eidetic-search-modal");
    contentEl.createEl("h3", { text: "Search memory" });

    const controls = contentEl.createDiv({ cls: "eidetic-search-controls" });
    const input = controls.createEl("input", {
      type: "text",
      placeholder: "Search your vault's RAG index…",
      cls: "eidetic-search-input",
    });
    input.focus();

    const modeSelect = controls.createEl("select", { cls: "eidetic-mode-select" });
    for (const m of ["hybrid", "vector", "keyword"]) {
      const opt = modeSelect.createEl("option", { text: m, value: m });
      if (m === this.mode) opt.selected = true;
    }
    modeSelect.onchange = () => {
      this.mode = modeSelect.value;
    };

    const status = contentEl.createDiv({ cls: "eidetic-search-status" });
    const resultsEl = contentEl.createDiv({ cls: "eidetic-search-results" });

    let timer: number | null = null;
    const run = async () => {
      const query = input.value.trim();
      if (!query) {
        resultsEl.empty();
        status.setText("");
        return;
      }
      status.setText("Searching…");
      try {
        const resp = await this.client.search(query, 10, this.mode);
        if (!resp.ok) {
          status.setText(`Error: ${resp.error ?? "search failed"}`);
          resultsEl.empty();
          return;
        }
        this.results = resp.results ?? [];
        status.setText(`${this.results.length} result(s)`);
        this.renderResults(resultsEl);
      } catch (e) {
        status.setText(`Could not reach Eidetic OS server. Is \`eidetic serve\` running?`);
        resultsEl.empty();
      }
    };

    input.addEventListener("input", () => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(run, 250);
    });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        if (timer) window.clearTimeout(timer);
        void run();
      }
    });
    modeSelect.addEventListener("change", () => void run());
  }

  private renderResults(container: HTMLElement): void {
    container.empty();
    for (const hit of this.results) {
      const card = container.createDiv({ cls: "eidetic-result-card" });
      const header = card.createDiv({ cls: "eidetic-result-header" });
      header.createSpan({ cls: "eidetic-result-file", text: hit.file });
      header.createSpan({
        cls: "eidetic-result-score",
        text: hit.score.toFixed(3),
      });
      if (hit.heading) {
        card.createDiv({ cls: "eidetic-result-heading", text: hit.heading });
      }
      card.createDiv({ cls: "eidetic-result-snippet", text: hit.snippet });
      card.onclick = () => {
        this.openFile(hit.file);
        this.close();
      };
    }
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

// ── Facts sidebar view ────────────────────────────────────────────────────────

class FactsView extends ItemView {
  constructor(
    leaf: WorkspaceLeaf,
    private client: EideticClient
  ) {
    super(leaf);
  }

  getViewType(): string {
    return FACTS_VIEW_TYPE;
  }

  getDisplayText(): string {
    return "Eidetic facts";
  }

  getIcon(): string {
    return "brain";
  }

  async onOpen(): Promise<void> {
    await this.render();
  }

  async render(): Promise<void> {
    const root = this.contentEl;
    root.empty();
    root.addClass("eidetic-facts-view");

    const header = root.createDiv({ cls: "eidetic-facts-header" });
    header.createEl("h4", { text: "Memory facts" });
    const refresh = header.createEl("button", { text: "Refresh", cls: "eidetic-btn" });

    const searchRow = root.createDiv({ cls: "eidetic-facts-search" });
    const input = searchRow.createEl("input", {
      type: "text",
      placeholder: "Search facts…",
    });

    const list = root.createDiv({ cls: "eidetic-facts-list" });

    const load = async (query: string) => {
      list.empty();
      list.createDiv({ cls: "eidetic-muted", text: "Loading…" });
      try {
        const resp = query.trim()
          ? await this.client.searchFacts(query.trim(), 30)
          : await this.client.listFacts("", 50);
        const facts = resp.facts ?? resp.results ?? [];
        list.empty();
        if (facts.length === 0) {
          list.createDiv({ cls: "eidetic-muted", text: "No facts yet." });
          return;
        }
        for (const fact of facts) {
          this.renderFact(list, fact);
        }
      } catch (e) {
        list.empty();
        list.createDiv({
          cls: "eidetic-muted",
          text: "Could not reach Eidetic OS server. Is `eidetic serve` running?",
        });
      }
    };

    refresh.onclick = () => void load(input.value);
    let timer: number | null = null;
    input.addEventListener("input", () => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(() => void load(input.value), 250);
    });

    await load("");
  }

  private renderFact(container: HTMLElement, fact: Fact): void {
    const card = container.createDiv({ cls: "eidetic-fact-card" });
    card.createDiv({ cls: "eidetic-fact-text", text: fact.fact });
    const meta = card.createDiv({ cls: "eidetic-fact-meta" });
    meta.createSpan({ cls: `eidetic-tag eidetic-cat-${fact.category}`, text: fact.category });
    if (typeof fact.score === "number") {
      meta.createSpan({ cls: "eidetic-muted", text: `· ${fact.score.toFixed(3)}` });
    }
    meta.createSpan({
      cls: "eidetic-muted",
      text: `· conf ${fact.confidence.toFixed(2)}`,
    });
    if (fact.source) {
      meta.createSpan({ cls: "eidetic-muted", text: `· ${fact.source}` });
    }
  }

  async onClose(): Promise<void> {
    this.contentEl.empty();
  }
}

// ── Stats modal ───────────────────────────────────────────────────────────────

class StatsModal extends Modal {
  constructor(app: App, private client: EideticClient) {
    super(app);
  }

  async onOpen(): Promise<void> {
    const { contentEl } = this;
    contentEl.addClass("eidetic-stats-modal");
    contentEl.createEl("h3", { text: "Eidetic OS — system stats" });
    const body = contentEl.createDiv();
    body.setText("Loading…");
    try {
      const stats = await this.client.stats();
      body.empty();
      this.renderStats(body, stats);
    } catch (e) {
      body.setText("Could not reach Eidetic OS server. Is `eidetic serve` running?");
    }
  }

  private row(parent: HTMLElement, label: string, value: string): void {
    const r = parent.createDiv({ cls: "eidetic-stat-row" });
    r.createSpan({ cls: "eidetic-stat-label", text: label });
    r.createSpan({ cls: "eidetic-stat-value", text: value });
  }

  private renderStats(parent: HTMLElement, stats: StatsResponse): void {
    parent.createEl("h4", { text: "RAG index" });
    if (stats.vectors.available) {
      this.row(parent, "Chunks", String(stats.vectors.chunk_count ?? 0));
      this.row(parent, "Files", String(stats.vectors.file_count ?? 0));
      this.row(parent, "Backend", stats.vectors.backend ?? "—");
      if (stats.vectors.last_embed) {
        this.row(
          parent,
          "Last embed",
          `${stats.vectors.last_embed.iso} (${stats.vectors.last_embed.age} ago)`
        );
      }
    } else {
      this.row(parent, "Index", "not built — run `eidetic embed --full`");
    }

    parent.createEl("h4", { text: "Facts" });
    this.row(parent, "Active", String(stats.facts.active ?? 0));
    this.row(parent, "Total", String(stats.facts.total ?? 0));
    const byCat = stats.facts.by_category ?? {};
    for (const [cat, n] of Object.entries(byCat)) {
      this.row(parent, `· ${cat}`, String(n));
    }

    parent.createEl("h4", { text: "Server" });
    this.row(parent, "Version", stats.version);
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

// ── The plugin ────────────────────────────────────────────────────────────────

export default class EideticPlugin extends Plugin {
  settings!: EideticSettings;
  private client!: EideticClient;
  private statusBar!: HTMLElement;
  private pollTimer: number | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new EideticClient(() => this.settings.serverUrl);

    this.registerView(FACTS_VIEW_TYPE, (leaf) => new FactsView(leaf, this.client));

    // Ribbon — brain icon opens the search modal.
    this.addRibbonIcon("brain", "Eidetic: search memory", () => {
      this.openSearch();
    });

    // Status bar — connection + fact count, polled.
    this.statusBar = this.addStatusBarItem();
    this.statusBar.addClass("eidetic-status");
    this.statusBar.onClickEvent(() => this.refreshStatus());

    this.addCommand({
      id: "eidetic-search-memory",
      name: "Search memory",
      callback: () => this.openSearch(),
    });
    this.addCommand({
      id: "eidetic-show-facts",
      name: "Show facts",
      callback: () => this.activateFactsView(),
    });
    this.addCommand({
      id: "eidetic-extract-facts",
      name: "Extract facts from note",
      checkCallback: (checking) => {
        const file = this.app.workspace.getActiveFile();
        if (!file) return false;
        if (!checking) void this.extractFromActiveNote(file);
        return true;
      },
    });
    this.addCommand({
      id: "eidetic-system-stats",
      name: "System stats",
      callback: () => new StatsModal(this.app, this.client).open(),
    });

    this.addSettingTab(new EideticSettingTab(this.app, this));

    // Kick off the status poll once the workspace is ready.
    this.app.workspace.onLayoutReady(() => {
      void this.refreshStatus();
      this.startPolling();
    });
  }

  onunload(): void {
    this.stopPolling();
  }

  private openSearch(): void {
    new SearchModal(this.app, this.client, (path) => this.openFile(path)).open();
  }

  private openFile(path: string): void {
    const file = this.app.vault.getAbstractFileByPath(path);
    if (file instanceof TFile) {
      void this.app.workspace.getLeaf(false).openFile(file);
    } else {
      new Notice(`Eidetic: couldn't find "${path}" in this vault.`);
    }
  }

  async activateFactsView(): Promise<void> {
    const { workspace } = this.app;
    let leaf = workspace.getLeavesOfType(FACTS_VIEW_TYPE)[0];
    if (!leaf) {
      leaf = workspace.getRightLeaf(false)!;
      await leaf.setViewState({ type: FACTS_VIEW_TYPE, active: true });
    }
    workspace.revealLeaf(leaf);
    const view = leaf.view;
    if (view instanceof FactsView) await view.render();
  }

  private async extractFromActiveNote(file: TFile): Promise<void> {
    const text = await this.app.vault.read(file);
    new Notice("Eidetic: extracting facts…");
    try {
      const resp = await this.client.extract(text, file.path, this.settings.storeOnExtract);
      if (!resp.ok) {
        new Notice(`Eidetic: ${resp.error ?? "extraction failed"}`);
        return;
      }
      if (resp.stored) {
        const t = resp.tally ?? {};
        const inserted = t.inserted ?? 0;
        new Notice(
          `Eidetic: stored facts from "${file.basename}" (${inserted} new).`
        );
        await this.activateFactsView();
      } else {
        new Notice(
          `Eidetic: found ${resp.count ?? resp.facts?.length ?? 0} fact(s) in "${file.basename}".`
        );
      }
    } catch (e) {
      new Notice("Eidetic: could not reach the server. Is `eidetic serve` running?");
    }
  }

  // ── status bar ──────────────────────────────────────────────────────────────

  private startPolling(): void {
    this.stopPolling();
    this.pollTimer = window.setInterval(
      () => void this.refreshStatus(),
      Math.max(5000, this.settings.pollIntervalMs)
    );
    this.registerInterval(this.pollTimer);
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  async refreshStatus(): Promise<void> {
    this.statusBar.empty();
    const icon = this.statusBar.createSpan({ cls: "eidetic-status-icon" });
    setIcon(icon, "brain");
    try {
      await this.client.health();
      const stats = await this.client.stats();
      const active = stats.facts.active ?? 0;
      this.statusBar.addClass("eidetic-connected");
      this.statusBar.removeClass("eidetic-disconnected");
      this.statusBar.createSpan({ text: ` Eidetic · ${active} facts` });
      this.statusBar.ariaLabel = "Eidetic OS connected — click to refresh";
    } catch (e) {
      this.statusBar.addClass("eidetic-disconnected");
      this.statusBar.removeClass("eidetic-connected");
      this.statusBar.createSpan({ text: " Eidetic · offline" });
      this.statusBar.ariaLabel =
        "Eidetic OS server unreachable — run `eidetic serve`. Click to retry.";
    }
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }
}

// ── Settings tab ──────────────────────────────────────────────────────────────

class EideticSettingTab extends PluginSettingTab {
  constructor(app: App, private plugin: EideticPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Eidetic OS" });
    containerEl.createEl("p", {
      cls: "setting-item-description",
      text: "Connects to your local Eidetic OS API server. Start it with `eidetic serve`.",
    });

    new Setting(containerEl)
      .setName("Server URL")
      .setDesc("Base URL of the Eidetic OS API server (default http://localhost:8501).")
      .addText((text) =>
        text
          .setPlaceholder("http://localhost:8501")
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (value) => {
            this.plugin.settings.serverUrl = value.trim() || DEFAULT_SETTINGS.serverUrl;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Store facts on extract")
      .setDesc(
        "When extracting facts from a note, also ingest them into the fact store (deduplicated). Off = preview only."
      )
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.storeOnExtract)
          .onChange(async (value) => {
            this.plugin.settings.storeOnExtract = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Status poll interval (seconds)")
      .setDesc("How often the status bar re-checks the server connection.")
      .addText((text) =>
        text
          .setValue(String(Math.round(this.plugin.settings.pollIntervalMs / 1000)))
          .onChange(async (value) => {
            const secs = Number(value);
            if (Number.isFinite(secs) && secs >= 5) {
              this.plugin.settings.pollIntervalMs = secs * 1000;
              await this.plugin.saveSettings();
            }
          })
      );

    new Setting(containerEl)
      .setName("Test connection")
      .setDesc("Ping the server and report whether it is reachable.")
      .addButton((btn) =>
        btn.setButtonText("Test").onClick(async () => {
          try {
            const client = new EideticClient(() => this.plugin.settings.serverUrl);
            const health = await client.health();
            new Notice(
              health.ok
                ? `Eidetic OS connected (v${health.version ?? "?"}).`
                : "Eidetic OS responded but reported not-ok."
            );
          } catch (e) {
            new Notice("Could not reach Eidetic OS. Is `eidetic serve` running?");
          }
        })
      );
  }
}
