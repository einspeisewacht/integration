/*
 * Einspeisewacht card: feed-in remuneration under negative prices at a
 * glance – whether the current quarter hour is remunerated, the windows
 * without remuneration today and tomorrow, the calendar year and the last
 * twelve months – without extra cards from HACS. Served and registered by
 * the integration itself (cards.py, frontend_resource.py).
 *
 *   type: custom:einspeisewacht-card
 *   device_id: <optional: the only Einspeisewacht device otherwise>
 *   sections: [now, year, months]         (optional; default: all)
 *   title: …                              (optional; a single space hides the heading)
 *
 * The card finds its entities by device and translation key (entity
 * registry), so the language of Home Assistant and renamed entity ids do
 * not matter; states are formatted by Home Assistant. The totals count from
 * setup, so year and months come from their long-term statistics (asked
 * once when the page opens, at most hourly after), imported history
 * included. Windows and repair issues come from the websocket command
 * "einspeisewacht/card". Figures above are the calendar year, the chart
 * shows the last twelve months (rule of all Wacht cards).
 */

// The integration loads the file with "?v=<version>" (cards.py).
const CARD_VERSION = new URL(import.meta.url).searchParams.get("v") || "dev";
const DOMAIN = "einspeisewacht";
const SECTIONS = ["now", "year", "months"];
// Repair issues of an entry (runtime.ISSUES).
const ISSUES = ["smard_failed", "price_missing", "meter_unit", "meter_missing", "rule_changed", "own_entity", "statistics_outdated"];
const DOCS = "https://github.com/einspeisewacht/integration#karte";

const TEXT = {
  de: {
    title: "Einspeisung",
    describe: "Vergütung jetzt, Zeitfenster ohne Vergütung heute und morgen, Erlös und Entgangenes im Jahr und die letzten 12 Monate.",
    noDevice: "Kein Einspeisewacht-Gerät gefunden.",
    nothing: "Keine Daten für diese Karte.",
    sections: { now: "Jetzt", year: "Jahr", months: "Monate" },
    issues: {
      smard_failed: "SMARD.de nicht erreichbar",
      price_missing: "Kein Preis für die laufende Viertelstunde",
      meter_unit: "Einheit des Zählers nicht unterstützt",
      meter_missing: "Einspeisezähler fehlt",
      rule_changed: "Summen teils nach alter Regel",
      own_entity: "Sensor von Einspeisewacht als Quelle",
      statistics_outdated: "Statistik mit altem Satz",
    },
    issueText: "Reparaturhinweis – zum Öffnen tippen",
    paidNow: "Jetzt vergütet",
    unpaidNow: "Jetzt keine Vergütung",
    noPriceNow: "Kein Preis für die laufende Viertelstunde",
    today: "Heute",
    tomorrow: "Morgen",
    noWindows: "keine negativen Preise",
    notYet: "Preise kommen gegen 13 Uhr",
    stillPaid: "noch vergütet",
    lost: "Entgangen",
    lostShadow: "Entgangen bei greifender Regel",
    revenue: "Erlös",
    unpaidShare: (p) => `${p} % unvergütet`,
    unpaidShareShadow: (p) => `${p} % wären unvergütet`,
    since: (m) => `Statistik ab ${m}`,
    quarters: "Ohne Vergütung",
    quartersShadow: "Ohne Vergütung bei greifender Regel",
    catchUp: "Nachholung",
    until: "Vergütung bis",
    shadowNote: "Die Regel greift noch nicht: Die Werte zeigen, was bei greifender Regel unvergütet wäre.",
    unaffected: "Negative Preise kosten diese Anlage keine Vergütung.",
    noStatistics: "Noch keine Statistik.",
    paid: "vergütet",
    unpaid: "unvergütet",
    unpaidShadow: "unvergütet bei greifender Regel",
    monthsCaption: "kWh · Anteil unvergütet in % (letzte 12 Monate)",
    editor: { device_id: "Anlage", title: "Überschrift (ein Leerzeichen blendet sie aus)", sections: "Abschnitte (leer: alle)" },
  },
  en: {
    title: "Feed-in",
    describe: "Remuneration now, windows without remuneration today and tomorrow, revenue and losses in the year and the last 12 months.",
    noDevice: "No Einspeisewacht device found.",
    nothing: "No data for this card.",
    sections: { now: "Now", year: "Year", months: "Months" },
    issues: {
      smard_failed: "SMARD.de unreachable",
      price_missing: "No price for the current quarter hour",
      meter_unit: "Meter unit not supported",
      meter_missing: "Feed-in meter missing",
      rule_changed: "Totals partly follow the previous rule",
      own_entity: "Sensor of Einspeisewacht as a source",
      statistics_outdated: "Statistics with the old rate",
    },
    issueText: "Repair issue – tap to open",
    paidNow: "Remunerated now",
    unpaidNow: "No remuneration now",
    noPriceNow: "No price for the current quarter hour",
    today: "Today",
    tomorrow: "Tomorrow",
    noWindows: "no negative prices",
    notYet: "prices come at about 1 pm",
    stillPaid: "still remunerated",
    lost: "Lost",
    lostShadow: "Lost if the rule applied",
    revenue: "Revenue",
    unpaidShare: (p) => `${p} % not remunerated`,
    unpaidShareShadow: (p) => `${p} % would not be remunerated`,
    since: (m) => `statistics from ${m}`,
    quarters: "Not remunerated",
    quartersShadow: "Not remunerated if the rule applied",
    catchUp: "Extension",
    until: "Remunerated until",
    shadowNote: "The rule does not apply yet: the figures show what would not be remunerated if it did.",
    unaffected: "Negative prices cost this plant no remuneration.",
    noStatistics: "No statistics yet.",
    paid: "remunerated",
    unpaid: "not remunerated",
    unpaidShadow: "not remunerated if the rule applied",
    monthsCaption: "kWh · share not remunerated in % (last 12 months)",
    editor: { device_id: "Plant", title: "Heading (a single space hides it)", sections: "Sections (empty: all)" },
  },
};

const ICON = "mdi:solar-power-variant";
// Month chart: drawing width in SVG units on wide cards, and the least on
// narrow ones (card width in between: drawn at that width, see _chartWidth).
const CHART_WIDTH = 560;
const CHART_MIN_WIDTH = 280;
// Brand green (docs/BRAND.md) and the magenta of the README's chart.
const COLORS = { paid: "#008351", unpaid: "#E6007E" };

const STYLE = `
  :host { display: block; }
  ha-card { padding: 16px; height: 100%; box-sizing: border-box; }
  .head { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; font-size: 16px; font-weight: 500;
    color: var(--primary-text-color); }
  .head ha-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
  section + section, .issues + section { margin-top: 16px; }
  .sub { font-size: 13px; font-weight: 500; color: var(--secondary-text-color); margin: 0 0 6px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 6px 4px; border-radius: 8px; cursor: pointer; }
  .row:hover, .tile:hover, .hero .link:hover, .chart:hover, .days:hover { background: var(--secondary-background-color); }
  .dot { flex: none; width: 12px; height: 12px; border-radius: 50%; background: var(--disabled-color, #bdbdbd); }
  .dot.paid { background: ${COLORS.paid}; }
  .dot.unpaid { background: ${COLORS.unpaid}; }
  .dot.issue { background: var(--warning-color, #ff9800); }
  .row .name { font-weight: 500; color: var(--primary-text-color); }
  .row .text { font-size: 13px; color: var(--secondary-text-color); }
  .days { display: grid; grid-template-columns: auto 1fr; gap: 2px 12px; padding: 6px 4px; border-radius: 8px;
    cursor: pointer; font-size: 14px; color: var(--primary-text-color); }
  .days .day { color: var(--secondary-text-color); }
  .days .past { opacity: 0.5; }
  .days .quiet { color: var(--secondary-text-color); }
  .hero { border: 1px solid var(--divider-color); border-radius: 12px; padding: 8px 12px; margin-bottom: 8px; }
  .hero .label { font-size: 12px; color: var(--secondary-text-color); }
  .hero .line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; }
  .hero .link { cursor: pointer; border-radius: 6px; padding: 0 4px; margin: 0 -4px; }
  .hero .big { font-size: 28px; font-weight: 500; color: var(--primary-text-color); }
  .hero .small { font-size: 14px; color: var(--primary-text-color); }
  .hero .small b { font-weight: 400; color: var(--secondary-text-color); }
  .hero .extra { font-size: 12px; color: var(--secondary-text-color); }
  .split { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin: 6px 0 2px;
    background: var(--divider-color); }
  .split .paid { background: ${COLORS.paid}; }
  .split .unpaid { background: ${COLORS.unpaid}; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
  .tile { border: 1px solid var(--divider-color); border-radius: 12px; padding: 8px 12px; cursor: pointer; min-width: 0; }
  .tile .label { font-size: 12px; color: var(--secondary-text-color); }
  /* "42 Volllast-Viertelstunden": wrap rather than cut. */
  .tile .value { font-size: 16px; font-weight: 500; color: var(--primary-text-color); overflow-wrap: anywhere; }
  .tile .extra { font-size: 12px; color: var(--secondary-text-color); }
  .note { font-size: 13px; color: var(--secondary-text-color); margin: 0 0 8px; }
  .chart { border-radius: 8px; cursor: pointer; min-width: 0; }
  .chart svg { max-width: 900px; margin: 0 auto; }
  .chart .caption { font-size: 13px; font-weight: 500; color: var(--primary-text-color); margin-bottom: 4px; }
  svg { width: 100%; height: auto; display: block; overflow: visible; }
  svg text { font-size: 10px; fill: var(--secondary-text-color); }
  svg .axis { stroke: var(--divider-color); stroke-width: 1; }
  svg .year { stroke: var(--secondary-text-color); stroke-width: 1; }
  svg rect.before { opacity: 0.4; }
  .legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--secondary-text-color); margin-top: 4px; }
  .legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    margin-right: 4px; vertical-align: -1px; background: var(--c); }
  .empty { color: var(--secondary-text-color); font-size: 14px; }
`;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/** A round axis step (1, 2 or 5 times a power of ten) of at least `raw`. */
function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw - 1e-9);
}

/** Decimals that show an axis step exactly. */
function stepDigits(step) {
  return Math.max(0, -Math.floor(Math.log10(step) + 1e-9));
}

// {device id: {translation key: entity id}} of Einspeisewacht's plants,
// computed once per registry object.
const INDEX = new WeakMap();
function index(hass) {
  const entities = hass.entities || {};
  let found = INDEX.get(entities);
  if (!found) {
    found = {};
    for (const entry of Object.values(entities)) {
      if (entry.platform === DOMAIN && entry.device_id && entry.translation_key) {
        (found[entry.device_id] ||= {})[entry.translation_key] = entry.entity_id;
      }
    }
    INDEX.set(entities, found);
  }
  return found;
}

function plants(hass) {
  return Object.keys(index(hass));
}

// Cards on the page: re-rendered when data they wait for arrive.
const CARDS = new Set();
function renderAll() {
  for (const card of CARDS) {
    card._states = null;
    card._render();
  }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") renderAll();
});

const RETRY_MS = 30 * 1000;

/** Ask `request` again when it is older than `maxAge` (or failed RETRY_MS
 * ago) or `stamp` changed; never while the page is hidden. Shared by all
 * cards on the page; the value stays while a new one is asked. */
function cached(store, key, stamp, maxAge, request) {
  const known = store.get(key);
  const age = known ? Date.now() - known.at : Infinity;
  const fresh = known && (known.failed ? age < RETRY_MS : known.stamp === stamp && age < maxAge);
  if (!fresh && !known?.loading && document.visibilityState !== "hidden") {
    store.set(key, { ...known, loading: true });
    request()
      .then((value) => store.set(key, { value, stamp, at: Date.now() }))
      .catch(() => store.set(key, { value: known?.value, failed: true, stamp, at: Date.now() }))
      .finally(renderAll);
  }
  return store.get(key)?.value;
}

// Windows and repair issues per device: asked again when the remuneration
// or the calendar changed (a new quarter hour, new prices) and every 10 min.
const LIVE = new Map();
const LIVE_MS = 10 * 60 * 1000;
// Monthly statistics per set of entities: hourly is enough for months.
const STATS = new Map();
const STATS_MS = 60 * 60 * 1000;

// The totals whose monthly statistics the card reads.
const TOTALS = ["energy_paid", "energy_unpaid", "revenue", "revenue_lost", "shadow_energy_unpaid", "shadow_revenue_lost"];

class EinspeisewachtCard extends HTMLElement {
  connectedCallback() {
    CARDS.add(this);
    // The month chart is drawn in the card's width: redraw when it changes
    // (phone turned, sidebar opened, section resized).
    this._resize ||= new ResizeObserver(() => {
      if (this._drawnWidth !== undefined && this._chartWidth() !== this._drawnWidth) {
        this._states = null;
        this._render();
      }
    });
    this._resize.observe(this);
  }

  disconnectedCallback() {
    CARDS.delete(this);
    this._resize?.disconnect();
  }

  /** Width of the month chart in SVG units: the card's inner width, at most
   * CHART_WIDTH. Drawn in about real pixels, its 10 px text stays readable
   * on a phone instead of shrinking with a scaled-down drawing. */
  _chartWidth() {
    const inner = this.clientWidth - 32; // ha-card padding
    if (!(inner > 0)) return CHART_WIDTH;
    return Math.max(CHART_MIN_WIDTH, Math.min(CHART_WIDTH, Math.round(inner / 10) * 10));
  }

  setConfig(config) {
    if (config.sections !== undefined && !Array.isArray(config.sections)) {
      throw new Error("sections must be a list");
    }
    this._config = { ...config };
    this._states = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Render only when one of the card's entities (state objects are
    // replaced on every change) or the language changed.
    const ids = this._watched();
    const states = ids.map((id) => hass.states[id]);
    if (this._states && states.length === this._states.length && states.every((s, i) => s === this._states[i])
      && this._lang === hass.locale?.language) {
      return;
    }
    this._states = states;
    this._lang = hass.locale?.language;
    this._render();
  }

  getCardSize() {
    return 3 * Math.max(1, this._sections().length);
  }

  getGridOptions() {
    // Sections view: 12 columns are the section's full width.
    return { columns: "full", min_columns: 6 };
  }

  static getConfigElement() {
    return document.createElement("einspeisewacht-card-editor");
  }

  static getStubConfig(hass) {
    const devices = plants(hass);
    return devices.length > 1 ? { device_id: devices[0] } : {};
  }

  _sections() {
    const wanted = this._config?.sections;
    return Array.isArray(wanted) && wanted.length ? SECTIONS.filter((s) => wanted.includes(s)) : SECTIONS;
  }

  _deviceId() {
    return this._config?.device_id || plants(this._hass)[0];
  }

  _watched() {
    if (!this._hass || !this._config) return [];
    const deviceId = this._deviceId();
    return deviceId ? Object.values(index(this._hass)[deviceId] || {}) : [];
  }

  _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return TEXT[lang] || TEXT.en;
  }

  /** Locale for numbers as the user's number format says (HA's mapping). */
  _numberLocale() {
    const locale = this._hass?.locale || {};
    return {
      comma_decimal: ["en-US", "en"],
      decimal_comma: ["de", "es", "it"],
      space_comma: ["fr", "sv", "cs"],
      system: undefined,
    }[locale.number_format] ?? locale.language ?? "en";
  }

  _num(value, digits) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "–";
    return new Intl.NumberFormat(this._numberLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value));
  }

  _money(value) {
    return `${this._num(value, 2)} €`;
  }

  _stateOf(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _state(key) {
    return this._stateOf(this._entities[key]);
  }

  _known(state) {
    return Boolean(state) && !["unknown", "unavailable"].includes(state.state);
  }

  _format(state) {
    if (!this._known(state)) return "–";
    return this._hass.formatEntityState ? this._hass.formatEntityState(state)
      : `${state.state} ${state.attributes.unit_of_measurement || ""}`.trim();
  }

  /** "what if" figures: the rule does not apply today, the shadow totals
   * say what it would cost. */
  _shadow() {
    return Boolean(this._entities.shadow_energy_unpaid) && this._state("active_rule")?.attributes?.applies_today === false;
  }

  /** Negative prices never cost this plant remuneration ("not affected"). */
  _unaffected() {
    return !this._entities.catch_up && !this._entities.shadow_energy_unpaid;
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (event) => {
        const path = event.composedPath();
        const repairs = path.find((el) => el.dataset && el.dataset.repairs !== undefined);
        if (repairs) {
          history.pushState(null, "", "/config/repairs");
          window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
          return;
        }
        const target = path.find((el) => el.dataset && el.dataset.entity);
        if (target) {
          this.dispatchEvent(new CustomEvent("hass-more-info", {
            detail: { entityId: target.dataset.entity }, bubbles: true, composed: true,
          }));
        }
      });
    }
    const t = this._t();
    const deviceId = this._deviceId();
    this._entities = (deviceId && index(this._hass)[deviceId]) || {};
    let body;
    if (!Object.keys(this._entities).length) {
      body = `<div class="empty">${escapeHtml(t.noDevice)}</div>`;
    } else {
      const sections = this._sections();
      // Windows and repair issues: one request per device, again when the
      // remuneration or the calendar changed.
      const stamp = [this._state("remunerated")?.last_changed, this._state("unpaid_windows")?.last_updated].join("|");
      const live = cached(LIVE, deviceId, stamp, LIVE_MS,
        () => this._hass.callWS({ type: `${DOMAIN}/card`, device_id: deviceId }));
      const months = sections.some((s) => s === "year" || s === "months") ? this._monthData() : undefined;
      const single = sections.length === 1;
      body = this._issues(t, live) + (sections
        .map((section) => {
          const inner = this[`_${section}`](t, section === "now" ? live : months);
          if (!inner) return "";
          return single ? inner : `<section><div class="sub">${escapeHtml(t.sections[section])}</div>${inner}</section>`;
        })
        .filter(Boolean)
        .join("") || `<div class="empty">${escapeHtml(t.nothing)}</div>`);
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${this._heading(t, deviceId)}${body}</ha-card>`;
  }

  _heading(t, deviceId) {
    const title = this._config.title === undefined ? undefined : String(this._config.title);
    if (title !== undefined && title !== "" && title.trim() === "") return "";
    const device = this._hass.devices?.[deviceId];
    const text = title || device?.name_by_user || device?.name || t.title;
    return `<div class="head"><ha-icon icon="${ICON}"></ha-icon>${escapeHtml(text)}</div>`;
  }

  /** Open repair issues of the plant, orange; a tap leads to Repairs. */
  _issues(t, live) {
    const rows = (live?.issues || []).filter((key) => ISSUES.includes(key)).map((key) =>
      `<div class="row" data-repairs><div class="dot issue"></div><div>`
      + `<div class="name">${escapeHtml(t.issues[key])}</div>`
      + `<div class="text">${escapeHtml(t.issueText)}</div></div></div>`);
    return rows.length ? `<div class="issues">${rows.join("")}</div>` : "";
  }

  // ---- Now ------------------------------------------------------------------

  _now(t, live) {
    const state = this._state("remunerated");
    let row = "";
    if (state) {
      const known = this._known(state);
      const paid = state.state === "on";
      const cls = !known ? "" : paid ? "paid" : "unpaid";
      const name = !known ? t.noPriceNow : paid ? t.paidNow : t.unpaidNow;
      row = `<div class="row" data-entity="${escapeHtml(this._entities.remunerated)}"><div class="dot ${cls}"></div>`
        + `<div class="name">${escapeHtml(name)}</div></div>`;
    }
    return row + this._days(t, live);
  }

  /** Today and tomorrow: the windows with negative prices. */
  _days(t, live) {
    if (!live?.days) return live === undefined ? `<div class="empty">…</div>` : "";
    const lang = this._hass.locale?.language || "en";
    // Clock as the user's profile says: 24, 12 or that of the language.
    const format = this._hass.locale?.time_format;
    const cycle = format === "24" ? { hourCycle: "h23" } : format === "12" ? { hour12: true } : {};
    const time = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit", timeZone: this._hass.config?.time_zone, ...cycle });
    const now = Date.now();
    const lines = live.days.map((day, i) => {
      let text;
      if (!day.known) text = `<span class="quiet">${escapeHtml(i === 0 ? "–" : t.notYet)}</span>`;
      else if (!day.windows.length) text = `<span class="quiet">${escapeHtml(t.noWindows)}</span>`;
      else {
        text = day.windows.map((w) => {
          const span = `${time.format(new Date(w.start))}–${time.format(new Date(w.end))}${w.paid ? ` (${t.stillPaid})` : ""}`;
          return `<span${new Date(w.end).getTime() <= now ? ' class="past"' : ""}>${escapeHtml(span)}</span>`;
        }).join(", ");
      }
      return `<div class="day">${escapeHtml(i === 0 ? t.today : t.tomorrow)}</div><div>${text}</div>`;
    });
    const calendar = this._entities.unpaid_windows;
    return `<div class="days"${calendar ? ` data-entity="${escapeHtml(calendar)}"` : ""}>${lines.join("")}</div>`;
  }

  // ---- Statistics -----------------------------------------------------------

  _monthKey(time) {
    const parts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", timeZone: this._hass.config?.time_zone })
      .formatToParts(new Date(time));
    const get = (type) => parts.find((p) => p.type === type).value;
    return `${get("year")}-${get("month")}`;
  }

  /** Keys of the twelve months up to `last` ("2026-11"), oldest first. */
  _monthsUpTo(last) {
    const [year, month] = last.split("-").map(Number);
    const keys = [];
    for (let i = 11; i >= 0; i--) {
      const total = year * 12 + (month - 1) - i;
      keys.push(`${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`);
    }
    return keys;
  }

  /** The last twelve months from the long-term statistics of the totals
   * (the recorder cuts months in the server's time zone): kWh and € paid
   * and unpaid, with the shadow totals when the rule does not apply yet.
   * undefined while loading, null without statistics. */
  _monthData() {
    const ids = TOTALS.map((key) => this._entities[key]).filter(Boolean);
    if (!ids.length) return null;
    const rows = cached(STATS, ids.join(","), undefined, STATS_MS, () => this._hass.callWS({
      type: "recorder/statistics_during_period",
      // 13 months back: the twelve shown start in the server's time zone.
      start_time: new Date(Date.now() - 400 * 86400000).toISOString(),
      statistic_ids: ids,
      period: "month",
      types: ["change"],
      units: { energy: "kWh" },
    }));
    if (rows === undefined) return undefined;
    const byMonth = new Map();
    let any = false;
    for (const key of TOTALS) {
      for (const row of rows?.[this._entities[key]] || []) {
        const month = this._monthKey(row.start);
        const m = byMonth.get(month) || {};
        m[key] = (m[key] || 0) + (row.change || 0);
        byMonth.set(month, m);
        any = true;
      }
    }
    if (!any) return null;
    const shadow = this._shadow();
    return this._monthsUpTo(this._monthKey(Date.now())).map((key) => {
      const m = byMonth.get(key);
      if (!m) return { key, has: false, paid: 0, unpaid: 0, revenue: 0, lost: 0 };
      const unpaid = Math.max(0, (shadow ? m.shadow_energy_unpaid : m.energy_unpaid) || 0);
      const lost = Math.max(0, (shadow ? m.shadow_revenue_lost : m.revenue_lost) || 0);
      // Without the rule the shadow energy is booked as paid: the bars split
      // it off, the revenue stays what was really paid.
      const paid = Math.max(0, (m.energy_paid || 0) - (shadow ? unpaid : 0));
      return { key, has: true, paid, unpaid, revenue: m.revenue || 0, lost };
    });
  }

  _monthLabel(key, style = "short") {
    const [year, month] = key.split("-").map(Number);
    // Mid-month at noon UTC: the same month in every time zone.
    const date = new Date(Date.UTC(year, month - 1, 15, 12));
    return date.toLocaleDateString(this._hass.locale?.language || "en", { month: style, timeZone: "UTC" });
  }

  // ---- Year -----------------------------------------------------------------

  /** The calendar year: lost revenue large, revenue and the unpaid share
   * beside it, then quarter hours, extension and end of remuneration. */
  _year(t, months) {
    const shadow = this._shadow();
    const unaffected = this._unaffected();
    const note = shadow ? t.shadowNote : unaffected ? t.unaffected : "";
    const tiles = this._grid([
      unaffected ? "" : this._tile(shadow ? "shadow_negative_quarter_hours" : "negative_quarter_hours", shadow ? t.quartersShadow : t.quarters),
      this._tile("catch_up", t.catchUp),
      this._tile("remunerated_until", t.until),
    ]);
    return `${note ? `<div class="note">${escapeHtml(note)}</div>` : ""}${this._hero(t, months, shadow, unaffected)}${tiles}`;
  }

  _hero(t, months, shadow, unaffected) {
    if (months === undefined) return `<div class="empty">…</div>`;
    if (months === null) return `<div class="empty">${escapeHtml(t.noStatistics)}</div>`;
    const year = this._monthKey(Date.now()).slice(0, 4);
    const inYear = months.filter((m) => m.key.startsWith(year));
    const sum = (field) => inYear.reduce((s, m) => s + m[field], 0);
    const paid = sum("paid");
    const unpaid = sum("unpaid");
    const share = paid + unpaid > 0 ? (100 * unpaid) / (paid + unpaid) : 0;
    // The statistics start this year (setup without imported history).
    const first = months.find((m) => m.has);
    const since = first && first.key.startsWith(year) && !first.key.endsWith("-01") && !months.some((m) => m.has && m.key < first.key)
      ? t.since(this._monthLabel(first.key, "long")) : "";
    const link = (key, label, value, cls) => {
      const id = this._entities[key];
      if (!id) return "";
      return `<span class="link ${cls}" data-entity="${escapeHtml(id)}">`
        + `${label ? `<b>${escapeHtml(label)}</b> ` : ""}${escapeHtml(value)}</span>`;
    };
    let line;
    if (unaffected) {
      line = link("revenue", "", this._money(sum("revenue")), "big");
    } else {
      line = link(shadow ? "shadow_revenue_lost" : "revenue_lost", "", this._money(sum("lost")), "big")
        + link("revenue", t.revenue, this._money(sum("revenue")), "small")
        + `<span class="small">${escapeHtml((shadow ? t.unpaidShareShadow : t.unpaidShare)(this._num(share, 0)))}</span>`;
    }
    const label = unaffected ? `${t.revenue} · ${year}` : `${shadow ? t.lostShadow : t.lost} · ${year}`;
    const split = unaffected || paid + unpaid <= 0 ? ""
      : `<div class="split"><div class="paid" style="width:${(100 - share).toFixed(1)}%"></div>`
        + `<div class="unpaid" style="width:${share.toFixed(1)}%"></div></div>`;
    return `<div class="hero"><div class="label">${escapeHtml(label)}</div><div class="line">${line}</div>${split}`
      + `${since ? `<div class="extra">${escapeHtml(since)}</div>` : ""}</div>`;
  }

  _grid(tiles) {
    const shown = tiles.filter(Boolean);
    return shown.length ? `<div class="grid">${shown.join("")}</div>` : "";
  }

  _tile(key, label) {
    const state = this._state(key);
    if (!state) return "";
    return `<div class="tile" data-entity="${escapeHtml(this._entities[key])}"><div class="label">${escapeHtml(label)}</div>`
      + `<div class="value">${escapeHtml(this._format(state))}</div></div>`;
  }

  // ---- Months -------------------------------------------------------------

  _months(t, months) {
    if (months === undefined) return `<div class="empty">…</div>`;
    if (months === null) return `<div class="empty">${escapeHtml(t.noStatistics)}</div>`;
    return this._monthChart(t, months);
  }

  /** Feed-in per month, paid and unpaid stacked, the unpaid share above.
   * Months of the calendar year (as the figures above) in full colour, the
   * months before paler, a thin line at 1 January. */
  _monthChart(t, months) {
    const W = this._chartWidth();
    this._drawnWidth = W;
    const H = 200;
    const L = 38;
    const B = 22;
    const T = 24;
    const high = Math.max(1, ...months.map((m) => m.paid + m.unpaid));
    const step = niceStep(high / 4);
    const y1 = Math.ceil(high / step) * step;
    const y = (v) => T + (1 - v / y1) * (H - B - T);
    const slot = (W - L - 6) / months.length;
    const bar = Math.max(4, slot * 0.6);
    let grid = "";
    for (let v = 0; v <= y1 + step / 2; v += step) {
      grid += `<line class="axis" x1="${L}" x2="${W - 6}" y1="${y(v)}" y2="${y(v)}" stroke-dasharray="2 3"/>`
        + `<text x="${L - 4}" y="${y(v) + 3}" text-anchor="end">${this._num(v, stepDigits(step))}</text>`;
    }
    // The figures above are the calendar year: months before it paler.
    const year = months.at(-1).key.slice(0, 4);
    const first = months.findIndex((m) => m.key.startsWith(year));
    let bars = "";
    if (first > 0) {
      const xd = (L + first * slot).toFixed(1);
      bars += `<line class="year" x1="${xd}" x2="${xd}" y1="4" y2="${H - B}"/>`
        + `<text x="${(L + first * slot + 4).toFixed(1)}" y="12">${escapeHtml(year)}</text>`;
    }
    const names = { paid: t.paid, unpaid: this._shadow() ? t.unpaidShadow : t.unpaid };
    months.forEach((m, i) => {
      const label = this._monthLabel(m.key);
      const before = first > 0 && i < first;
      const x = L + i * slot + slot / 2;
      let base = 0;
      for (const key of ["paid", "unpaid"]) {
        const v = m[key];
        if (!(v > 0)) continue;
        bars += `<rect x="${(x - bar / 2).toFixed(1)}" y="${y(base + v).toFixed(1)}" width="${bar.toFixed(1)}" height="${(y(base) - y(base + v)).toFixed(1)}" fill="${COLORS[key]}"${before ? ' class="before"' : ""}>`
          + `<title>${escapeHtml(label)} · ${escapeHtml(names[key])}: ${this._num(v, 0)} kWh</title></rect>`;
        base += v;
      }
      if (m.unpaid > 0 && base > 0) {
        bars += `<text x="${x.toFixed(1)}" y="${(y(base) - 3).toFixed(1)}" text-anchor="middle">${this._num((100 * m.unpaid) / base, 0)}</text>`;
      }
      bars += `<text x="${x.toFixed(1)}" y="${H - 6}" text-anchor="middle">${escapeHtml(label)}</text>`;
    });
    const legend = Object.keys(names).map((k) => `<span style="--c:${COLORS[k]}">${escapeHtml(names[k])}</span>`).join("");
    const target = this._shadow() ? this._entities.shadow_energy_unpaid : this._entities.energy_unpaid;
    return `<div class="chart"${target ? ` data-entity="${escapeHtml(target)}"` : ""}><div class="caption">${escapeHtml(t.monthsCaption)}</div>`
      + `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(t.sections.months)}">${grid}${bars}</svg>`
      + `<div class="legend">${legend}</div></div>`;
  }
}

class EinspeisewachtCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    const lang = (this._hass.locale?.language || "en").slice(0, 2);
    const texts = TEXT[lang] || TEXT.en;
    const devices = plants(this._hass).map((id) => {
      const entry = this._hass.devices?.[id];
      return { value: id, label: entry?.name_by_user || entry?.name || id };
    });
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (event) => {
        const value = { ...event.detail.value };
        for (const key of Object.keys(value)) {
          if (value[key] === "" || value[key] === null || (Array.isArray(value[key]) && !value[key].length)) delete value[key];
        }
        this._config = { type: this._config.type, ...value };
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.computeLabel = (schema) => texts.editor[schema.name] || schema.name;
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "device_id", selector: { select: { mode: "dropdown", options: devices } } },
      { name: "title", selector: { text: {} } },
      {
        name: "sections",
        selector: { select: { multiple: true, options: SECTIONS.map((s) => ({ value: s, label: texts.sections[s] })) } },
      },
    ];
  }
}

if (!customElements.get("einspeisewacht-card")) {
  customElements.define("einspeisewacht-card-editor", EinspeisewachtCardEditor);
  customElements.define("einspeisewacht-card", EinspeisewachtCard);
  window.customCards = window.customCards || [];
  const texts = TEXT[(navigator.language || "en").slice(0, 2)] || TEXT.en;
  window.customCards.push({
    type: "einspeisewacht-card",
    name: "Einspeisewacht",
    description: texts.describe,
    preview: true,
    documentationURL: DOCS,
  });
  console.info(`%c EINSPEISEWACHT %c ${CARD_VERSION} `, "color:#fff;background:#008351", "color:#008351");
}
