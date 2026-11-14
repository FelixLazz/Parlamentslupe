"use strict";

const $ = (id) => document.getElementById(id);
const labels = { yes: "Ja", no: "Nein", abstain: "Enthaltung", no_show: "Nichtteilnahme", unknown: "Unbekannt" };
const outcomes = { accepted: "angenommen", rejected: "abgelehnt", unknown: "unbekannt" };
const format = new Intl.NumberFormat("de-DE");
const state = { catalog: null, report: null, view: "polls", online: null, busy: false, page: 0, request: 0, comparison: null, programBusy: false, programRequest: 0, disabledBefore: null };
const PAGE_SIZE = 8;
const WEB_API_VERSION = 1;
state.choices = null;
state.prepared = new Set();
state.activePollIds = null;

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

function feedback(message = "", kind = "") {
  $("feedback").hidden = !message;
  $("feedback").className = `feedback ${kind}`;
  $("feedback").textContent = message;
  $("feedback").setAttribute("role", kind === "error" ? "alert" : "status");
}

function safeLink(url, text, className = "") {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) return el("span", className, text);
    const link = el("a", className, text);
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  } catch {
    return el("span", className, "Quelle nicht verlinkt");
  }
}

function dateLabel(value) {
  if (!value) return "Datum nicht bekannt";
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString("de-DE");
}

async function api(path, payload) {
  const options = payload ? {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-ParteiHack-Token": state.catalog.token },
    body: JSON.stringify(payload),
  } : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || `Anfrage fehlgeschlagen (${response.status}).`);
    error.code = data.code;
    error.status = response.status;
    throw error;
  }
  return data;
}

function options(select, items, placeholder, preferred = "", autoSelect = true) {
  select.replaceChildren(new Option(placeholder, ""));
  for (const item of items) select.add(new Option(item.short_name || item.label, item.id));
  if (items.some((item) => String(item.id) === String(preferred))) select.value = preferred;
  else if (items.length && autoSelect) select.value = items[0].id;
  select.disabled = !items.length;
}

function selectedPeriod() {
  return state.catalog?.periods.find((item) => String(item.id) === $("period").value);
}

function selectedProgram() {
  return (state.choices?.programs || state.report?.programs || []).find((item) => String(item.id) === $("program").value);
}

function controls() {
  $("load-parliaments").disabled = state.busy;
  $("load-periods").disabled = state.busy || !$("parliament").value;
  $("load-fractions").disabled = state.busy || !$("period").value;
  $("investigate").disabled = state.busy || !$("fraction").value || !chosenPollIds().length;
  $("local-investigate").disabled = state.busy || !$("fraction").value;
  $("all-polls").disabled = state.busy || !state.choices?.coverage.poll_list_complete_against_api;
  $("export").disabled = state.busy || !state.report;
  const noProgram = state.busy || state.programBusy || !selectedProgram() || !state.report;
  $("load-program").disabled = noProgram;
  $("compare-program").disabled = noProgram;
  $("start-comparison").disabled = noProgram;
  $("complete-comparison").disabled = noProgram;
  $("enrich-evidence").disabled = noProgram || !state.report?.coverage.local_polls;
  $("export-comparison").disabled = state.busy || !state.comparison;
  $("load-programs").disabled = state.busy || !state.report;
  for (const id of ["parliament", "period", "fraction", "program"]) {
    $(id).disabled = state.busy || $(id).options.length <= 1;
  }
}

function setBusy(value) {
  state.busy = value;
  if (value) {
    state.disabledBefore = new Map();
    for (const field of document.querySelectorAll("main input, main select, main button")) {
      state.disabledBefore.set(field, field.disabled);
      field.disabled = true;
    }
  } else {
    for (const [field, disabled] of state.disabledBefore || []) {
      if (field.isConnected) field.disabled = disabled;
    }
    state.disabledBefore = null;
    controls();
  }
}

function clearProgramResults() {
  state.programRequest++;
  state.comparison = null;
  $("program-results").replaceChildren();
  $("comparison-results").replaceChildren(el("p", "fine-print", "Noch kein Vergleich für diese Auswahl erstellt."));
}

function updateProgramStatus() {
  const program = selectedProgram();
  $("program-status").textContent = program ?
    (program.local_document_present ? "Original-PDF lokal vorhanden. Prüfsumme und Text werden beim Öffnen erneut geprüft." :
      "Bisher nur Metadaten lokal. Die ausgewählte Original-PDF kann nach Bestätigung geladen und extrahiert werden.") :
    (state.choices?.programs.length ? "Optional ein Programm ausdrücklich auswählen. Fraktion und Wahlpartei sind getrennte Auswahlen." :
      "Ohne Programm werden nur Abstimmungen untersucht. Auswahldaten oben freigeben, um Programm-Metadaten zu ergänzen.");
  $("compare-selection").textContent = program ?
    `${program.label} · Wahlpartei: ${program.party?.label || "unbekannt"} ↔ ${$("fraction").selectedOptions[0]?.textContent || "Fraktion wählen"} · ${selectedPeriod()?.label}` :
    "Wähle oben in „Deine Untersuchung“ ein Programm zur Wahlperiode.";
  controls();
}

function fillFractions(preferred = "") {
  const fractions = state.catalog.fractions.filter((item) => String(item.legislature?.id) === $("period").value);
  options($("fraction"), fractions, fractions.length ? "Fraktion auswählen …" : ($("period").value ? "Keine Fraktionen lokal – online laden" : "Zuerst Wahlperiode wählen"), preferred, false);
  controls();
}

function fillPeriods(preferred = "") {
  const periods = state.catalog.periods.filter((item) => String(item.parliament?.id) === $("parliament").value);
  // Einen vorhandenen Datenbestand zeigen, nicht stillschweigend eine leere neuere Periode.
  const withFractions = periods.find((period) => state.catalog.fractions.some((fraction) => fraction.legislature?.id === period.id));
  options($("period"), periods, periods.length ? "Wahlperiode auswählen …" : "Keine Wahlperioden lokal – online laden", preferred || withFractions?.id);
  fillFractions();
}

function checkWebVersion(catalog) {
  if (catalog.web_api_version !== WEB_API_VERSION) {
    const error = new Error("Oberfläche und Webserver haben unterschiedliche Versionsstände. Den laufenden Webserver im Terminal mit Strg+C beenden, mit „uv run parteihack web“ neu starten und diese Seite neu laden. Lokale Daten bleiben erhalten.");
    error.code = "web_version_mismatch";
    throw error;
  }
}

async function loadCatalog(preserve = true, preparedCatalog = null) {
  const previous = preserve ? [$("parliament").value, $("period").value, $("fraction").value] : [];
  const catalog = preparedCatalog ?
    { ...preparedCatalog, token: state.catalog.token, web_api_version: state.catalog.web_api_version } : await api("/api/catalog");
  checkWebVersion(catalog);
  state.catalog = catalog;
  const withPeriods = state.catalog.parliaments.find((parliament) =>
    state.catalog.periods.some((period) => period.parliament?.id === parliament.id &&
      state.catalog.fractions.some((fraction) => fraction.legislature?.id === period.id)));
  options($("parliament"), state.catalog.parliaments, state.catalog.parliaments.length ? "Parlament auswählen …" : "Keine Parlamente lokal – online laden", previous[0] || withPeriods?.id);
  // Der erste Ladebutton muss auch mit leerer Datenbank nutzbar bleiben.
  fillPeriods(previous[1]);
  if (previous[2]) fillFractions(previous[2]);
}

function invalidate(keepChoices = false) {
  state.request += 1;
  state.report = null;
  state.page = 0;
  state.activePollIds = null;
  $("analysis").hidden = true;
  $("empty-state").hidden = false;
  clearProgramResults();
  if (!keepChoices) {
    state.choices = null;
    fillProgramOptions([]);
    renderPollPicker();
  }
  updateProgramStatus();
  feedback("Auswahl geändert. Alles auswählen und anschließend gemeinsam laden.");
  controls();
}

function chosenPollIds() {
  if ($("all-polls").checked) return (state.choices?.polls || []).map(poll => poll.id);
  return [...$("poll-options").querySelectorAll("input:checked")].map(input => Number(input.value));
}

function fillProgramOptions(programs) {
  const previous = $("program").value;
  $("program").replaceChildren(new Option("Ohne Programm – nur Abstimmungen", ""));
  for (const program of programs) $("program").add(new Option(`${program.party?.label || "Wahlpartei unbekannt"} · ${program.label}${program.local_document_present ? " · PDF lokal" : ""}`, program.id));
  if (programs.some(program => String(program.id) === previous)) $("program").value = previous;
  $("program").disabled = state.busy || !programs.length;
}

function updatePollSummary() {
  const ids = chosenPollIds();
  $("poll-selection-summary").textContent = $("all-polls").checked ?
    `Alle ${ids.length} Abstimmungen ausgewählt` : `${ids.length} Abstimmungen ausgewählt`;
  const search = $("poll-search").value.trim().toLocaleLowerCase("de");
  for (const label of $("poll-options").children) {
    label.hidden = !label.textContent.toLocaleLowerCase("de").includes(search);
    label.querySelector("input").disabled = state.busy || $("all-polls").checked;
  }
  controls();
}

function renderPollPicker(selected = [], all = false) {
  $("poll-options").replaceChildren();
  const complete = Boolean(state.choices?.coverage.poll_list_complete_against_api);
  $("all-polls").checked = all && complete;
  for (const poll of state.choices?.polls || []) {
    const label = el("label", "checkbox-label");
    const checkbox = el("input");
    checkbox.type = "checkbox";
    checkbox.value = poll.id;
    checkbox.checked = selected.includes(poll.id);
    checkbox.addEventListener("change", () => { invalidate(true); updatePollSummary(); });
    label.append(checkbox, el("span", "", `${dateLabel(poll.date)} · ${poll.label}${poll.complete_against_api ? " · Stimmen lokal vollständig" : ""}`));
    $("poll-options").append(label);
  }
  $("choices-status").textContent = state.choices ?
    `${state.choices.polls.length} lokale Titel · ${complete ? "Titelliste API-vollständig" : "Titelliste noch unvollständig – Auswahldaten ergänzen"}. Einzelstimmen erst beim gemeinsamen Start.` :
    "Wahlperiode wählen. Titel werden vor den Einzelstimmen geladen.";
  updatePollSummary();
}

async function loadChoices(preparedChoices = null) {
  if (!$("period").value) return;
  const samePeriod = String(state.choices?.period.id) === $("period").value;
  const selected = samePeriod ? chosenPollIds() : [];
  const all = samePeriod && $("all-polls").checked;
  state.choices = preparedChoices || await api("/api/choices?period=" + $("period").value);
  fillProgramOptions(state.choices.programs);
  renderPollPicker(selected, all);
  updateProgramStatus();
}

async function prepareSelection() {
  if (state.busy) return;
  setBusy(true);
  let notice = "";
  let preparedChoices = null;
  try {
    if ($("auto-choices").checked) {
      feedback("Auswahldaten werden ergänzt – noch keine Einzelstimmen oder PDFs. API-Cache und mindestens 2,1 Sekunden Requestabstand …", "busy");
      if (!state.prepared.has("parliaments")) {
        const catalog = await api("/api/refresh", { scope: "parliaments", confirm_online: true });
        state.prepared.add("parliaments");
        await loadCatalog(true, catalog);
      }
      const parliament = $("parliament").value;
      if (parliament && !state.prepared.has(`periods:${parliament}`)) {
        const catalog = await api("/api/refresh", { scope: "periods", parent: Number(parliament), confirm_online: true });
        state.prepared.add(`periods:${parliament}`);
        await loadCatalog(true, catalog);
      }
      const period = $("period").value;
      if (period && !state.prepared.has(`selection:${period}`)) {
        const result = await api("/api/prepare", { period: Number(period), confirm_online: true });
        state.prepared.add(`selection:${period}`);
        await loadCatalog(true, result.catalog);
        preparedChoices = result.choices;
        notice = result.notice || "";
      }
    }
    await loadChoices(preparedChoices);
    feedback(`${notice ? notice + " " : ""}Fraktion, optional Programm und Abstimmungen auswählen. Danach einmal gemeinsam laden.`);
  } catch (error) {
    // Erfolgreiche Teilschritte bleiben lokal erhalten; kein automatischer Neuversuch.
    try { await loadCatalog(); await loadChoices(); } catch { /* Ursprünglichen Fehler zeigen. */ }
    feedback(error.message, "error");
  } finally {
    setBusy(false);
    updatePollSummary();
  }
}

function switchView(view) {
  state.view = view;
  for (const name of ["polls", "programs", "compare", "method"]) $("view-" + name).hidden = name !== view;
  for (const button of document.querySelectorAll("[data-view]")) {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (button.classList.contains("tab")) button.setAttribute("aria-pressed", String(active));
    else if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  $("breadcrumb-current").textContent = { polls: "Übersicht", programs: "Wahlprogramme", compare: "Vergleich", method: "Methodik & Quellen" }[view];
}

function querySelection(extra = {}) {
  return new URLSearchParams({ period: $("period").value, fraction: $("fraction").value,
    ...(state.activePollIds?.length ? { polls: state.activePollIds.join(",") } : {}), ...extra });
}

async function investigate() {
  if (!$("fraction").value) return;
  const request = ++state.request;
  const query = querySelection({ search: $("search").value, since: $("since").value, until: $("until").value });
  feedback("Lokale Daten werden ausgewertet …", "busy");
  $("analysis").setAttribute("aria-busy", "true");
  try {
    const report = await api("/api/analysis?" + query);
    if (request !== state.request) return;
    state.report = report;
    state.page = 0;
    renderReport();
    feedback();
  } catch (error) {
    if (request !== state.request) return;
    state.report = null;
    clearProgramResults();
    updateProgramStatus();
    $("analysis").hidden = true;
    $("empty-state").hidden = false;
    feedback(error.message, "error");
  } finally {
    if (request === state.request) {
      $("analysis").setAttribute("aria-busy", "false");
      controls();
    }
  }
}

function stack(counts) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 6");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", Object.entries(labels).map(([key, label]) => `${label}: ${counts[key] || 0}`).join(", "));
  svg.classList.add("vote-stack");
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  let offset = 0;
  for (const key of Object.keys(labels)) {
    const width = total ? (counts[key] || 0) / total * 100 : 0;
    const rect = document.createElementNS(svg.namespaceURI, "rect");
    rect.setAttribute("x", offset);
    rect.setAttribute("y", "0");
    rect.setAttribute("width", width);
    rect.setAttribute("height", "6");
    rect.classList.add(key);
    svg.append(rect);
    offset += width;
  }
  return svg;
}

function renderDistribution(counts) {
  const root = $("distribution");
  root.replaceChildren();
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  for (const [key, label] of Object.entries(labels)) {
    const count = counts[key] || 0;
    if (key === "unknown" && !count) continue;
    const row = el("div", "distribution-row");
    const heading = el("div");
    const name = el("span", "legend-label");
    name.append(el("span", `legend-dot ${key}`), document.createTextNode(label));
    const value = el("span", "legend-count", format.format(count) + " ");
    value.append(el("span", "legend-percent", total ? `${Math.round(count / total * 100)} %` : "–"));
    heading.append(name, value);
    const meter = el("meter", key);
    meter.min = 0;
    meter.max = total || 1;
    meter.value = count;
    meter.setAttribute("aria-label", `${label}: ${count}`);
    row.append(heading, meter);
    root.append(row);
  }
}

function renderReport() {
  const report = state.report;
  const coverage = report.coverage;
  $("analysis").hidden = false;
  $("empty-state").hidden = true;
  $("analysis-title").textContent = report.fraction.short_name || report.fraction.label;
  $("analysis-title").title = report.period.label;
  $("coverage-badge").textContent = coverage.poll_list_complete_against_api ? "Abstimmungsliste API-vollständig" : "Stichprobe · begrenzte Daten";
  $("coverage-badge").className = "badge " + (coverage.poll_list_complete_against_api ? "green" : "amber");
  $("stat-polls").textContent = format.format(coverage.local_polls);
  $("stat-available").textContent = coverage.available_api_polls == null ? "/ API-Umfang unbekannt" : `/ ${format.format(coverage.available_api_polls)} laut API`;
  $("stat-complete").textContent = format.format(coverage.filtered_polls_with_complete_votes);
  $("stat-filtered").textContent = `/ ${format.format(coverage.filtered_polls)} Polls`;
  $("stat-votes").textContent = format.format(Object.values(report.vote_totals).reduce((a, b) => a + b, 0));
  $("coverage-notice").textContent = coverage.poll_list_complete_against_api ?
    "Technische Abdeckung der API-Liste belegt, nicht gegen alle amtlichen Abstimmungen geprüft. Fehlende Fraktionsstimmen bleiben fehlende Daten." :
    "Die lokale Abstimmungsliste ist nicht als vollständig belegt. Eine technische Stichprobe ist nicht repräsentativ. Fehlende Stimmen sind keine Nichtteilnahmen.";
  $("distribution-fraction").textContent = `${report.fraction.short_name || report.fraction.label} · gefilterte Abstimmungen`;
  $("result-count").textContent = format.format(report.polls.length);
  renderDistribution(report.vote_totals);
  renderPolls();
  if (state.choices) state.choices.programs = report.programs;
  fillProgramOptions(report.programs);
  updateProgramStatus();
}

function renderPolls() {
  const polls = state.report.polls;
  $("poll-list").replaceChildren();
  if (!polls.length) $("poll-list").append(el("p", "no-results", "Keine lokalen Abstimmungen für diese Filter. Filter zurücksetzen oder bewusst Daten importieren."));
  for (const poll of polls.slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE)) {
    const row = el("article", "poll-row");
    const meta = el("div", "poll-meta");
    meta.append(el("span", "", dateLabel(poll.date)), el("span", "", `Poll ${poll.id}`));
    if (poll.accepted === true || poll.accepted === false) meta.append(el("span", "badge " + (poll.accepted ? "green" : "amber"), poll.accepted ? "Vorlage angenommen" : "Vorlage abgelehnt"));
    const title = el("button", "poll-title", poll.label);
    title.type = "button";
    title.addEventListener("click", () => showPoll(poll.id));
    const bottom = el("div", "poll-bottom");
    const preview = el("div", "vote-preview");
    preview.append(stack(poll.votes), el("p", "vote-caption", poll.fraction_votes ?
      `${format.format(poll.fraction_votes)} Fraktionsstimmen · ${poll.complete_against_api ? "Poll-Stimmenimport API-vollständig" : "Stimmenimport unvollständig / ungeprüft"}` :
      "Keine lokalen Stimmen dieser Fraktion · keine Nichtteilnahme ableitbar"));
    bottom.append(preview, safeLink(poll.public_url || poll.source_url, "Originalquelle ↗", "poll-source"));
    row.append(meta, title, bottom);
    $("poll-list").append(row);
  }
  $("pagination").hidden = polls.length <= PAGE_SIZE;
  $("page-label").textContent = `Seite ${state.page + 1} von ${Math.max(1, Math.ceil(polls.length / PAGE_SIZE))}`;
  $("prev-page").disabled = state.page === 0;
  $("next-page").disabled = (state.page + 1) * PAGE_SIZE >= polls.length;
}

async function showPoll(pollId) {
  const request = state.request;
  $("detail-title").textContent = "Abstimmung wird geladen …";
  $("poll-detail").replaceChildren();
  $("poll-dialog").showModal();
  try {
    const data = await api("/api/poll?" + querySelection({ poll: pollId }));
    if (request !== state.request) return;
    $("detail-title").textContent = data.poll.label;
    const meta = el("div", "detail-meta");
    meta.append(el("span", "", dateLabel(data.poll.field_poll_date)),
      safeLink(data.poll.abgeordnetenwatch_url || data.poll.api_url, "Originalquelle ↗"));
    const count = data.coverage;
    const summary = el("p", "fine-print", `${format.format(count.local_votes)} lokale Stimmen insgesamt · ${count.complete_against_api ? "gegen API-Anzahl geprüft" : "API-Abdeckung nicht vollständig belegt"}. Fraktion: ${state.report.fraction.label}`);
    const voteFilter = el("label", "detail-vote-filter", "Stimmen filtern");
    const select = el("select");
    select.add(new Option("Alle Stimmwerte", ""));
    for (const [key, label] of Object.entries(labels)) select.add(new Option(label, key));
    voteFilter.append(select);
    const container = el("div", "detail-vote-scroll");
    const renderVotes = () => {
      container.replaceChildren();
      const votes = data.votes.filter((vote) => !select.value || (labels[vote.vote] ? vote.vote : "unknown") === select.value);
      if (!votes.length) {
        container.append(el("p", "detail-empty", "Keine lokalen Einzelstimmen für diese Auswahl. Daraus ist keine Nichtteilnahme ableitbar."));
        return;
      }
      const table = el("table", "detail-votes");
      const head = el("thead");
      const header = el("tr");
      for (const text of ["Abgeordnete Person", "Stimme", "Beleg"]) {
        const th = el("th", "", text);
        th.scope = "col";
        header.append(th);
      }
      head.append(header);
      const body = el("tbody");
      for (const vote of votes) {
        const row = el("tr");
        const source = el("td");
        source.append(safeLink(vote.source_url, "API ↗"));
        row.append(el("td", "", vote.politician || `Mandat ${vote.mandate_id ?? "unbekannt"}`), el("td", "", labels[vote.vote] || "Unbekannt"), source);
        body.append(row);
      }
      table.append(head, body);
      container.append(table);
    };
    select.addEventListener("change", renderVotes);
    renderVotes();
    $("poll-detail").append(meta, el("p", "detail-description", data.description || "Keine lokale Beschreibung vorhanden."), summary, voteFilter, container);
  } catch (error) {
    $("detail-title").textContent = "Abstimmung nicht verfügbar";
    $("poll-detail").append(el("p", "feedback error", error.message));
  }
}

function openOnline(scope) {
  const program = selectedProgram();
  if (["program", "compare", "evidence"].includes(scope) && !program) return;
  const descriptions = {
    run: `„${selectedPeriod()?.label}“ · „${$("fraction").selectedOptions[0]?.textContent}“: ${chosenPollIds().length} ${$("all-polls").checked ? "Abstimmungen (bewusst alle)" : "ausgewählte Abstimmungen"}. Nur fehlende/unvollständige Einzelstimmen werden geladen, einschließlich historischer Mandate. ${program ? `Zusätzlich nur das gewählte Programm „${program.label}“ bei Bedarf herunterladen und direkt vergleichen. PDF-Quelle: ${program.file || "kein PDF-Link vorhanden"}.` : "Kein Programm gewählt: nur Abstimmungen untersuchen."} Größere Importe können lange dauern; der API-Anbieter empfiehlt 22–6 Uhr. Kein Erfüllungsurteil.`,
    parliaments: "Die Liste der verfügbaren Parlamente wird von abgeordnetenwatch geladen. Darunter befinden sich Bundestag und die von der API angebotenen Landesparlamente. Es werden keine Abstimmungen importiert.",
    periods: `Wahl- und Legislaturperioden für „${$("parliament").selectedOptions[0]?.textContent}“ laden. In der Auswahl werden nur Legislaturperioden angeboten.`,
    fractions: `Fraktionen für „${selectedPeriod()?.label}“ laden. Es werden keine Einzelstimmen importiert.`,
    programs: `Programm-Metadaten zur vorhergehenden Wahl von „${selectedPeriod()?.label}“ laden. Keine Mandate, Stimmen oder PDF-Sammeldownloads.`,
    program: `Nur das ausgewählte Programm „${program?.label}“ wird bei Bedarf aus der in der API verlinkten PDF geladen, lokal archiviert und als Text extrahiert. Quelle: ${program?.file || "Kein PDF-Link in der API vorhanden"}. Bereits vorhandene Quellen werden genutzt.`,
    compare: `Programm „${program?.label}“ mit der Fraktion „${state.report?.fraction.label}“ vergleichen. Fehlt die Original-PDF, wird nur dieses ausgewählte Programm geladen und lokal extrahiert. Quelle: ${program?.file || "Kein PDF-Link in der API vorhanden"}. Keine automatische Richtungs- oder Erfüllungsbewertung.`,
    evidence: "Zu höchstens fünf lokalen Abstimmungen werden relevante Themen-/Ausschussdaten und insgesamt höchstens drei verlinkte amtliche Bundestagsbelege ergänzt. Keine freie Websuche, keine neuen Stimmenimporte und kein Urteil über Erfüllung. Nicht unterstützte Landesquellen bleiben ausdrücklich offen. Bereits archivierte Belege werden genutzt.",
    import: `Begrenzte Stichprobe für „${selectedPeriod()?.label}“ importieren. Es werden Stimmen des gesamten Parlaments geladen; die Auswertung filtert anschließend deine Fraktion.`,
  };
  state.online = scope;
  $("online-description").textContent = descriptions[scope];
  $("online-heading").textContent = { run: "Gewählte Daten gemeinsam laden", import: "Bewusst eine Stichprobe importieren", program: "Programm laden und Text extrahieren", compare: "Daten laden & Vergleich erstellen" }[scope] || "Stammdaten online laden";
  // Stimmen werden über die sichtbare Titelauswahl geladen, nicht als spätere Stichprobe.
  $("compare-votes-option").hidden = true;
  $("compare-load-votes").checked = false;
  $("import-options").hidden = scope !== "import";
  $("online-dialog").showModal();
}

async function confirmOnline() {
  if (state.busy || !state.online) return;
  const scope = state.online;
  state.online = null;
  const payload = { confirm_online: true };
  if (scope === "run") {
    payload.period = Number($("period").value);
    payload.fraction = Number($("fraction").value);
    payload.program = $("program").value ? Number($("program").value) : null;
    payload.all_polls = $("all-polls").checked;
    if (!payload.all_polls) payload.poll_ids = chosenPollIds();
  } else if (["program", "compare", "evidence"].includes(scope)) {
    payload.period = Number($("period").value);
    payload.fraction = Number($("fraction").value);
    payload.program = Number($("program").value);
    if (["compare", "evidence"].includes(scope) && state.activePollIds?.length) payload.poll_ids = state.activePollIds;
    if (scope === "evidence") {
      payload.max_polls = 5;
      payload.max_documents = 3;
    }
    if (scope === "compare") {
      payload.load_votes = $("compare-load-votes").checked;
      payload.max_polls = Number($("max-polls").value);
    }
  } else if (scope === "import") {
    payload.period = Number($("period").value);
    payload.max_polls = Number($("max-polls").value);
  } else {
    payload.scope = scope;
    if (scope === "periods") payload.parent = Number($("parliament").value);
    if (scope === "fractions") payload.parent = Number($("period").value);
    if (scope === "programs") payload.parent = Number($("period").value);
  }
  $("online-dialog").close();
  setBusy(true);
  feedback(["program", "compare"].includes(scope) ?
    "Ausgewählte Quelle wird bei Bedarf geladen, lokal extrahiert und geprüft. Bitte warten …" :
    "Online-Abruf läuft. API-Requests erfolgen sequenziell mit mindestens 2,1 Sekunden Abstand. Bitte warten …", "busy");
  try {
    const path = ["program", "compare", "evidence", "run"].includes(scope) ? `/api/${scope}` : (scope === "import" ? "/api/import" : "/api/refresh");
    const result = await api(path, payload);
    if (scope === "run") {
      state.activePollIds = result.selected_poll_ids;
      state.report = result.analysis;
      state.page = 0;
      clearProgramResults();
      renderReport();
      const currentPolls = new Map(result.analysis.polls.map(poll => [poll.id, poll]));
      for (const poll of state.choices?.polls || []) {
        if (currentPolls.has(poll.id)) poll.complete_against_api = currentPolls.get(poll.id).complete_against_api;
      }
      renderPollPicker(result.selected_poll_ids, payload.all_polls);
      if (result.comparison) renderComparison(result.comparison);
      else switchView("polls");
      feedback(`${result.selected_poll_ids.length} Abstimmungen untersucht, ${result.reused_polls} vollständige Stimmenimporte wiederverwendet.${result.comparison ? " Programm geladen und Vergleich erstellt." : ""}`);
      return;
    }
    await loadCatalog();
    await loadChoices();
    if ($("fraction").value) await investigate();
    if (scope === "program") renderProgram(result);
    if (["compare", "evidence"].includes(scope)) renderComparison(result);
    feedback(scope === "program" ? "Original-PDF vorhanden, Text erfolgreich extrahiert. Du kannst jetzt den Vergleich starten." :
      scope === "evidence" ? `Belegrecherche abgeschlossen: ${result.enrichment.documents_downloaded} neue, ${result.enrichment.documents_cached} archivierte Belege. ${result.enrichment.errors.length} Abruffehler; Details im JSON. Kein gefundener Beleg bedeutet nicht, dass es keine amtliche Quelle gibt.` :
      scope === "compare" ? "Vergleich erstellt. Zitatvorschläge und dokumentierte Fraktionsstimmen stehen nebeneinander; Datenlücken bleiben sichtbar." :
      scope === "import" ? "Stichprobe importiert. Die Auswertung zeigt die lokal vorhandenen Daten." :
      scope === "programs" ? "Programmliste abgefragt. Falls die Quelle keine Programme anbietet, bleibt die Liste leer." :
      "Stammdaten geladen. Wähle den nächsten Schritt deiner Untersuchung.");
  } catch (error) {
    // Ein fehlgeschlagener Import kann bereits gespeicherte Teilergebnisse enthalten.
    try { await loadCatalog(); await loadChoices(); } catch { /* Ursprünglichen Fehler beibehalten. */ }
    feedback(`${error.message} Bereits gespeicherte Teildaten bleiben erhalten. Untersuchung bei Bedarf erneut starten.`, "error");
    if (["program", "compare"].includes(scope)) {
      const root = scope === "program" ? $("program-results") : $("comparison-results");
      root.replaceChildren(el("p", "feedback error", error.message));
    }
  } finally {
    setBusy(false);
    updatePollSummary();
  }
}

async function loadProgram(page = 1) {
  const request = state.request;
  const programId = $("program").value;
  if (!selectedProgram() || state.programBusy || state.busy) return;
  const programRequest = ++state.programRequest;
  state.programBusy = true;
  $("program-results").replaceChildren(el("p", "fine-print", "Original-PDF wird lokal geprüft, Textstellen werden gesucht …"));
  controls();
  try {
    const data = await api("/api/program?" + querySelection({ program: programId, page }));
    if (request !== state.request || programRequest !== state.programRequest) return;
    renderProgram(data);
  } catch (error) {
    if (request !== state.request || programRequest !== state.programRequest) return;
    $("program-results").replaceChildren(el("p", error.code === "program_missing" ? "fine-print" : "feedback error", error.message));
    if (error.code === "program_missing") openOnline("program");
  } finally {
    state.programBusy = false;
    controls();
  }
}

function renderProgram(data) {
  const root = $("program-results");
  root.replaceChildren();
  const program = selectedProgram();
  if (program) program.local_document_present = true;
  updateProgramStatus();
  const info = el("div", "program-evidence");
  info.append(el("h3", "", data.program.label),
    el("p", "fine-print", `${data.pdf_pages} PDF-Seiten · ${format.format(data.text_characters)} Textzeichen extrahiert · Quelle lokal archiviert am ${dateLabel(data.imported_at)}`),
    el("span", "digest", `SHA-256: ${data.sha256}`), safeLink(data.source_url, "Originalprogramm ↗"));
  if (data.origin === "local_file") info.append(el("p", "fine-print", "Lokale PDF zugeordnet; Identität mit der API-Datei nicht unabhängig verifiziert."));
  const navigation = el("div", "program-pagination");
  const previous = el("button", "secondary-button compact", "← Vorherige Seite");
  previous.type = "button";
  previous.disabled = data.page <= 1;
  previous.addEventListener("click", () => loadProgram(data.page - 1));
  const pageLabel = el("label", "", "PDF-Seite");
  const pages = el("select");
  for (let i = 1; i <= data.pdf_pages; i++) pages.add(new Option(`${i} / ${data.pdf_pages}`, i));
  pages.value = data.page;
  pages.addEventListener("change", () => loadProgram(Number(pages.value)));
  pageLabel.append(pages);
  const next = el("button", "secondary-button compact", "Nächste Seite →");
  next.type = "button";
  next.disabled = data.page >= data.pdf_pages;
  next.addEventListener("click", () => loadProgram(data.page + 1));
  navigation.append(previous, pageLabel, next);
  root.append(info, navigation);
  for (const page of data.pages) {
    const article = el("article", "program-page");
    article.append(el("h3", "", `PDF-Seite ${page.number}`), el("p", "", page.text || "Auf dieser PDF-Seite wurde kein Text erkannt."));
    root.append(article);
  }
}

async function startComparison() {
  if (!selectedProgram() || state.programBusy || state.busy) return;
  switchView("compare");
  const request = state.request;
  const programRequest = ++state.programRequest;
  state.programBusy = true;
  controls();
  $("comparison-results").replaceChildren(el("p", "fine-print", "Programm und Fraktionsstimmen werden lokal gegenübergestellt …"));
  try {
    const data = await api("/api/compare?" + querySelection({ program: $("program").value }));
    if (request !== state.request || programRequest !== state.programRequest) return;
    renderComparison(data);
  } catch (error) {
    if (request !== state.request || programRequest !== state.programRequest) return;
    state.comparison = null;
    $("comparison-results").replaceChildren(el("p", error.code === "program_missing" ? "fine-print" : "feedback error", error.message));
    if (error.code === "program_missing") openOnline(chosenPollIds().length ? "run" : "compare");
  } finally {
    state.programBusy = false;
    controls();
  }
}

function renderProgramAnalysis(report) {
  const section = el("details", "program-page");
  section.append(el("summary", "", "Programm genauer untersuchen"));
  const analysis = report.program_analysis;
  const features = analysis.candidate_feature_counts;
  section.append(el("p", "", `${analysis.candidate_count} ungeprüfte Kandidaten · ${features.quantities} mit Mengenangaben · ${features.years} mit Jahreszahlen · ${features.conditions} mit Bedingungen im Zitat · ${analysis.candidates_with_context_conditions} mit Bedingungen im Satzkontext.`),
    el("p", "fine-print", `${analysis.pages_with_text} von ${analysis.pdf_pages} PDF-Seiten mit Text. Die Satzheuristik kann Zusagen übersehen oder Kontextpassagen einschließen. Jahreszahlen können historische Bezüge sein. Die Merkmalsgruppen überschneiden sich.`));
  const searchLabel = el("label", "", "Programmkandidaten durchsuchen");
  const search = el("input");
  search.type = "search";
  search.placeholder = "Begriff, Zahl oder Jahr";
  searchLabel.append(search);
  const filterLabel = el("label", "", "Prüfmerkmal");
  const filter = el("select");
  for (const [value, label] of Object.entries({ all: "Alle Kandidaten", quantities: "Mit Mengenangaben", years: "Mit Jahreszahlen", conditions: "Mit Bedingungen im Zitat oder Kontext", unmatched: "Ohne lokalen Top-Treffer" })) {
    const option = el("option", "", label);
    option.value = value;
    filter.append(option);
  }
  filterLabel.append(filter);
  const controls = el("div", "program-inventory-controls");
  controls.append(searchLabel, filterLabel);
  const status = el("p", "fine-print");
  status.setAttribute("role", "status");
  const entries = el("div");
  const more = el("button", "secondary-button", "Weitere Kandidaten anzeigen");
  more.type = "button";
  let limit = 20;
  const polls = new Map(report.polls.map(poll => [poll.id, poll]));
  function renderEntries() {
    const query = search.value.trim().toLocaleLowerCase("de");
    const candidates = report.promise_candidates.filter(candidate => {
      const fields = candidate.statement_features;
      const text = `${candidate.quote} ${candidate.context_before} ${candidate.context_after}`;
      const matchesText = text.toLocaleLowerCase("de").includes(query);
      let matchesFeature = true;
      if (filter.value === "unmatched") matchesFeature = !candidate.matched_poll_ids.length;
      else if (filter.value === "conditions") matchesFeature = Boolean(fields.conditions.length || candidate.context_features.conditions.length);
      else if (filter.value !== "all") matchesFeature = Boolean(fields[filter.value].length);
      return matchesText && matchesFeature;
    });
    entries.replaceChildren();
    for (const candidate of candidates.slice(0, limit)) {
      const entry = el("article", "program-inventory-entry");
      entry.append(el("h4", "", `PDF-Seite ${candidate.page} · ungeprüft`), el("blockquote", "", candidate.quote));
      const fields = candidate.statement_features;
      const annotations = [];
      for (const [key, label] of Object.entries({ quantities: "Mengenangaben", years: "Jahreszahlen", conditions: "Bedingungen", negations: "Verneinungen" })) {
        if (fields[key].length) annotations.push(`${label}: ${fields[key].join(", ")}`);
      }
      if (annotations.length) entry.append(el("p", "fine-print", annotations.join(" · ")));
      const context = el("details", "fine-print");
      context.append(el("summary", "", "Satzkontext anzeigen"), el("p", "", candidate.context_before || "Kein vorheriger Satz auf dieser PDF-Seite."), el("p", "", candidate.context_after || "Kein nachfolgender Satz auf dieser PDF-Seite."));
      entry.append(context);
      if (candidate.matched_poll_ids.length) {
        const links = el("p", "fine-print", "Lokale Top-Treffer · ");
        for (const id of candidate.matched_poll_ids) {
          const poll = polls.get(id);
          if (poll) links.append(safeLink(poll.source_url, poll.title), document.createTextNode(" · "));
        }
        entry.append(links);
      } else entry.append(el("p", "fine-print", "Kein Treffer unter den angezeigten Top-Zuordnungen. Die Prüfung parlamentarischer Vorgänge bleibt offen."));
      entries.append(entry);
    }
    status.textContent = `${Math.min(limit, candidates.length)} von ${candidates.length} Kandidaten angezeigt`;
    more.hidden = candidates.length <= limit;
  }
  for (const control of [search, filter]) control.addEventListener("input", () => { limit = 20; renderEntries(); });
  more.addEventListener("click", () => { limit += 20; renderEntries(); });
  section.append(controls, status, entries, more);
  section.addEventListener("toggle", () => { if (section.open && !entries.childElementCount) renderEntries(); });
  return section;
}

function renderComparison(report) {
  state.comparison = report;
  switchView("compare");
  const root = $("comparison-results");
  root.replaceChildren();
  const summary = el("div", "comparison-summary");
  const coverage = report.coverage;
  summary.append(el("h3", "", `${report.fraction.label} ↔ ${report.program.label}`),
    el("p", "", `${coverage.reported_polls} Abstimmungen im Vergleich · ${coverage.local_polls} lokale Titel / ${coverage.available_api_polls ?? "unbekannt"} laut API · ${coverage.polls_with_complete_votes} mit vollständigem Stimmenimport · ${report.polls_with_text_matches} mit Worttreffern`),
    el("p", "", `${report.program.pdf_pages} PDF-Seiten · ${coverage.complete_against_api ? "Technische API-Abdeckung belegt" : "Datenbasis unvollständig / Stichprobe"}`),
    el("span", "digest", `Programm-SHA-256: ${report.program.sha256}`),
    safeLink(report.program.source_url, "Originalprogramm ↗"));
  root.append(summary);
  if (report.quality_summary) {
    const quality = report.quality_summary;
    summary.append(el("p", "fine-print", `Qualitätsprüfung: ${quality.polls_with_blocking_data_issues} Polls mit Datenproblemen · ${quality.polls_with_uncheckable_membership_history} mit nicht vollständig prüfbarer Fraktionshistorie · ${quality.polls_with_official_sources} mit amtlichen Belegen · ${quality.polls_with_matching_official_aggregates} mit passenden amtlichen Summen · ${quality.polls_with_official_conflicts} Summenkonflikte.`),
      el("p", "fine-print", `API-Ergebnis: ${quality.polls_accepted_by_api} angenommen · ${quality.polls_rejected_by_api} abgelehnt · ${quality.polls_outcome_unknown} unbekannt. Das ist keine Umsetzungsbewertung.`),
      el("p", "fine-print", `${quality.promise_candidates} ungeprüfte Versprechenskandidaten im gesamten Programm, ${quality.candidates_without_retrieved_poll} ohne lokalen Top-Treffer. Das sind keine unerfüllten Versprechen und kein gültiger Score-Nenner.`));
  }
  const warnings = el("ul", "comparison-warnings");
  for (const warning of report.warnings) warnings.append(el("li", "", warning));
  root.append(warnings);
  if (report.program_analysis) root.append(renderProgramAnalysis(report));
  if (!report.polls.length) root.append(el("p", "comparison-empty", "Noch keine Abstimmungen im Vergleich. Oben die gewünschten Titel auswählen und „Auswahl laden & untersuchen“ verwenden."));
  for (const poll of report.polls) {
    const article = el("article", "comparison-poll");
    const meta = el("div", "poll-meta", `${dateLabel(poll.date)} · Poll ${poll.id}`);
    meta.append(safeLink(poll.source_url, "Abstimmungsquelle ↗", "poll-source"));
    article.append(meta, el("h3", "", poll.title));
    const columns = el("div", "comparison-columns");
    const passages = el("div");
    passages.append(el("h4", "", "PROGRAMMTEXT · UNGEPRÜFTE VORSCHLÄGE"));
    if (!poll.program_matches.length) passages.append(el("p", "comparison-empty", "Keine ausreichend ähnlichen Wörter gefunden. Das belegt weder ein fehlendes Versprechen noch einen Widerspruch."));
    for (const match of poll.program_matches) {
      const quote = el("blockquote", "", match.quote);
      quote.append(el("p", "", `PDF-Seite ${match.page} · Ungeprüft · Suchwörter: ${match.matched_terms.join(", ")}`));
      passages.append(quote);
      if (match.context_before || match.context_after) {
        const context = el("details", "fine-print");
        context.append(el("summary", "", "Satzkontext der Originalseite anzeigen"),
          el("p", "", match.context_before || "Kein vorheriger Satz auf dieser Seite."),
          el("p", "", match.context_after || "Kein nachfolgender Satz auf dieser Seite."));
        passages.append(context);
      }
      if (match.review_flags?.length) passages.append(el("p", "fine-print", `Prüfhinweise: ${match.review_flags.join(", ")}. Keine automatische Interpretation von Bedingungen oder Verneinungen.`));
    }
    const votes = el("div", "comparison-votes");
    votes.append(el("h4", "", "DOKUMENTIERTE FRAKTIONSSTIMMEN"),
      el("span", "badge comparison-badge " + (poll.all_votes_complete_against_api ? "green" : "amber"), poll.all_votes_complete_against_api ? "Poll-Stimmenimport API-vollständig" : "Stimmenimport unvollständig / ungeprüft"),
      stack(poll.votes),
      el("p", "vote-caption", Object.entries(labels).map(([key, label]) => `${format.format(poll.votes[key] || 0)} ${label}`).join(" · ")),
      el("p", "fine-print", poll.fraction_votes ? "Richtung und Erfüllung nicht bewertet. Dafür sind eine belegte Zuordnung und explizite Prüfung notwendig." : "Keine lokalen Stimmen dieser Fraktion. Fehlende Daten sind keine Nichtteilnahme."));
    if (poll.vote_diagnostics) {
      const diagnostics = poll.vote_diagnostics;
      votes.append(el("p", "fine-print", `${diagnostics.blocking_issue_count} blockierende Datenprobleme · ${diagnostics.membership_history_checked} Fraktionsverläufe geprüft · ${diagnostics.membership_history_uncheckable} nicht prüfbar.`));
      if ("decisive_share_of_recorded_members" in diagnostics) {
        const share = value => value == null ? "nicht berechenbar" : `${format.format(value * 100)} %`;
        votes.append(el("p", "fine-print", `Ja/Nein an allen dokumentierten Fraktionseinträgen: ${share(diagnostics.decisive_share_of_recorded_members)} · Teilnahme einschließlich Enthaltungen: ${share(diagnostics.participation_share_of_recorded_members)} · Anteil der Ja-/Nein-Mehrheitsrichtung an allen Einträgen: ${share(diagnostics.majority_share_of_recorded_members)}. Nenner: ${diagnostics.selected_fraction_events} lokale Einträge einschließlich Nichtteilnahme und unbekannter Werte.`));
      }
      if (diagnostics.dissenting_votes.length) votes.append(el("p", "fine-print", "Abweichende Ja-/Nein-Stimmen: " + diagnostics.dissenting_votes.map(item => `${item.politician || `Mandat ${item.mandate_id}`}: ${labels[item.vote]}`).join("; ")));
      for (const issue of diagnostics.issues.slice(0, 5)) votes.append(el("p", "fine-print", `Datenhinweis: ${issue.code}`));
    }
    if (poll.quality) votes.append(el("p", "fine-print", `API-Ergebnis: ${outcomes[poll.quality.api_outcome] || poll.quality.api_outcome}. Keine Umsetzungs- oder Erfüllungsaussage.`));
    if (poll.procedure_context?.flags.length) votes.append(el("p", "fine-print", `Vorgangsprüfung: ${poll.procedure_context.flags.join(", ")}.`));
    for (const source of poll.official_sources || []) {
      const evidence = el("div", "program-evidence");
      evidence.append(el("h4", "", source.title), safeLink(source.url, "Amtliches Original ↗"),
        el("span", "digest", `SHA-256: ${source.sha256}`),
        el("p", "fine-print", "Kontextquelle. Die Identität der konkreten Abstimmungsfassung ist nicht automatisch geprüft."));
      votes.append(evidence);
    }
    if (poll.official_crosscheck && poll.official_crosscheck.status !== "not_checked") votes.append(el("p", "fine-print", `Amtlicher Summenabgleich: ${poll.official_crosscheck.status}. Keine Einzelstimmen- oder Erfüllungsprüfung.`));
    columns.append(passages, votes);
    article.append(columns);
    root.append(article);
  }
  controls();
}

function downloadJSON(data, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = el("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

$("parliament").addEventListener("change", () => { invalidate(); fillPeriods(); prepareSelection(); });
$("period").addEventListener("change", () => { invalidate(); fillFractions(); prepareSelection(); });
$("fraction").addEventListener("change", () => { invalidate(true); controls(); });
$("auto-choices").addEventListener("change", prepareSelection);
$("all-polls").addEventListener("change", () => { invalidate(true); updatePollSummary(); });
$("poll-search").addEventListener("input", updatePollSummary);
$("selection-form").addEventListener("submit", (event) => { event.preventDefault(); if (!state.busy && chosenPollIds().length) openOnline("run"); });
$("local-investigate").addEventListener("click", () => { state.activePollIds = chosenPollIds().length ? chosenPollIds() : null; investigate(); });
$("filter-form").addEventListener("submit", (event) => { event.preventDefault(); investigate(); });
$("reset-filters").addEventListener("click", () => {
  for (const id of ["search", "since", "until"]) $(id).value = "";
  investigate();
});
$("prev-page").addEventListener("click", () => { state.page--; renderPolls(); });
$("next-page").addEventListener("click", () => { state.page++; renderPolls(); });
for (const button of document.querySelectorAll("[data-view]")) button.addEventListener("click", () => switchView(button.dataset.view));
for (const button of document.querySelectorAll("[data-close]")) button.addEventListener("click", () => $(button.dataset.close).close());
for (const scope of ["parliaments", "periods", "fractions", "programs"]) $("load-" + scope).addEventListener("click", () => openOnline(scope));
$("open-import").addEventListener("click", () => { $("poll-picker").open = true; $("poll-selection-summary").focus(); feedback("Oben Abstimmungen wählen und „Auswahl laden & untersuchen“ starten."); });
$("confirm-online").addEventListener("click", confirmOnline);
$("program").addEventListener("change", () => { clearProgramResults(); updateProgramStatus(); });
$("load-program").addEventListener("click", () => loadProgram());
$("program-form").addEventListener("submit", (event) => { event.preventDefault(); startComparison(); });
$("choose-program").addEventListener("click", () => { $("program").focus(); $("program").scrollIntoView({ block: "center" }); });
$("start-comparison").addEventListener("click", startComparison);
$("complete-comparison").addEventListener("click", () => { if (chosenPollIds().length) openOnline("run"); else { $("poll-picker").open = true; $("poll-selection-summary").focus(); } });
$("enrich-evidence").addEventListener("click", () => openOnline("evidence"));
$("compare-load-votes").addEventListener("change", () => { $("import-options").hidden = !$("compare-load-votes").checked; });
$("export-comparison").addEventListener("click", () => {
  if (state.comparison) downloadJSON(state.comparison, `parteihack-vergleich-${state.comparison.period.id}-${state.comparison.fraction.id}-${state.comparison.program.id}.json`);
});
$("export").addEventListener("click", () => {
  if (!state.report) return;
  downloadJSON(state.report, `parteihack-${state.report.period.id}-${state.report.fraction.id}.json`);
});

loadCatalog(false).then(async () => {
  await loadChoices();
  feedback("Alles oben auswählen. Fehlende Auswahldaten lassen sich einmalig freigeben; Stimmen und Programm erst anschließend gemeinsam laden.");
}).catch((error) => {
  if (error.code === "web_version_mismatch") setBusy(true);
  feedback(error.code === "web_version_mismatch" ? error.message :
    `Lokaler Datenbestand nicht erreichbar: ${error.message}`, "error");
});
