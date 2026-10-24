"use strict";

// ---------------- 工具 ----------------

const $ = (sel, root = document) => root.querySelector(sel);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function icon(path) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.innerHTML = path;
  return svg;
}

const ICONS = {
  close: '<path d="M5 5l10 10M15 5 5 15"/>',
  copy: '<rect x="7" y="7" width="9.5" height="9.5" rx="2"/><path d="M13 4.5V4a1.5 1.5 0 0 0-1.5-1.5h-7A1.5 1.5 0 0 0 3 4v7a1.5 1.5 0 0 0 1.5 1.5H5"/>',
  download: '<path d="M10 3.5v9M6 9l4 4 4-4M4 16.5h12"/>',
  refresh: '<path d="M16 10a6 6 0 1 1-1.8-4.3M16 3.5v3.2h-3.2"/>',
  trash: '<path d="M4 6h12M8 6V4.5h4V6M6 6l.7 10h6.6L14 6"/>',
  doc: '<path d="M6 2.5h5.5L15 6v11.5H6z"/><path d="M11 2.5V6h4"/>',
};

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch("/api" + path, {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("；");
    throw new ApiError(msg || `请求失败（${res.status}）`, res.status);
  }
  return data;
}

let toastTimer;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

function formatTime(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

function hostOf(url) {
  try { return new URL(url).host; } catch { return url; }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // 部分 WebView 不开放剪贴板 API，退回到 execCommand
    const ta = el("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  toast("已复制");
}

function downloadFile(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------- 状态 ----------------

const state = {
  presets: null,
  settings: null,
  companies: {},    // 名称 -> 切片数
  current: null,    // 当前企业；null 表示首页
  docs: [],         // 输入框中待提交的文本资料
  mode: "add",      // 企业页输入框模式：add 补充资料 / search 检索资料
  busy: false,
};

const main = $("#main");
const thread = $("#thread");
const scroller = $("#scroll");
const cCompany = $("#c-company");
const cInput = $("#c-input");
const cSend = $("#c-send");

function scrollToBottom() {
  requestAnimationFrame(() => scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" }));
}

// ---------------- 侧边栏 ----------------

async function loadCompanies() {
  try {
    state.companies = await api("/companies");
  } catch (e) {
    state.companies = {};
    if (e.status !== 400) toast(e.message); // 400 表示尚未设置向量化服务
  }
  renderCompanies();
}

function renderCompanies() {
  const list = $("#company-list");
  list.replaceChildren();
  const names = Object.keys(state.companies);
  $("#history-empty").hidden = names.length > 0;
  for (const name of names) {
    const li = el("li", { class: name === state.current ? "active" : "", title: name, onclick: () => openCompany(name) },
      el("span", { class: "name" }, name),
      el("span", { class: "count" }, `${state.companies[name]} 段`),
      el("button", {
        class: "icon-btn del", title: "删除", "aria-label": `删除 ${name}`,
        onclick: (e) => { e.stopPropagation(); deleteCompany(name); },
      }, icon(ICONS.trash)),
    );
    list.append(li);
  }
}

async function deleteCompany(name) {
  if (!confirm(`删除「${name}」的全部资料和画像？此操作无法撤销。`)) return;
  try {
    await api(`/companies/${encodeURIComponent(name)}`, { method: "DELETE" });
    toast("已删除");
    if (state.current === name) goHome();
    await loadCompanies();
  } catch (e) {
    toast(e.message);
  }
}

function updateModelBadge() {
  const llm = state.settings?.llm;
  $("#model-name").textContent = llm?.has_api_key ? llm.model : "未设置 API Key";
}

// ---------------- 视图切换 ----------------

function setTopbar(title, actions = []) {
  $("#topbar-title").textContent = title || "";
  $("#topbar-actions").replaceChildren(...actions);
}

function goHome() {
  state.current = null;
  state.docs = [];
  main.classList.add("home");
  thread.replaceChildren();
  setTopbar("");
  cCompany.value = "";
  cInput.value = "";
  renderAttachments();
  updateComposer();
  renderCompanies();
  cCompany.focus();
}

function enterCompany(name) {
  state.current = name;
  main.classList.remove("home");
  setTopbar(name, [
    el("button", { class: "icon-btn", title: "重新生成画像", "aria-label": "重新生成画像", onclick: () => regenerate() }, icon(ICONS.refresh)),
  ]);
  renderCompanies();
  updateComposer();
}

async function openCompany(name) {
  if (state.busy) return toast("请等待当前任务完成");
  enterCompany(name);
  thread.replaceChildren();
  state.docs = [];
  renderAttachments();
  try {
    const profile = await api(`/profile/${encodeURIComponent(name)}`);
    thread.append(renderProfile(profile));
  } catch (e) {
    if (e.status !== 404) return thread.append(notice(e.message));
    const count = state.companies[name];
    thread.append(el("div", { class: "empty-state" },
      el("h2", {}, "还没有生成画像"),
      el("p", {}, count ? `已入库 ${count} 段资料。` : "", "可以直接生成，也可以先在下方补充网址或文本资料。"),
      el("button", { class: "btn primary", onclick: () => regenerate() }, "生成画像"),
    ));
  }
  scroller.scrollTop = 0;
}

// ---------------- 输入框 ----------------

function updateComposer() {
  const home = state.current === null;
  const search = !home && state.mode === "search";
  cInput.placeholder = home
    ? "粘贴官网或新闻网址，每行一个"
    : search ? "在已入库资料中检索，例如：海外市场" : "补充网址（每行一个），完成后自动重新生成画像";
  $("#c-attach").hidden = search;
  $("#c-crawl-chip").hidden = search;
  $("#c-lang").hidden = search;
  for (const b of document.querySelectorAll("#c-mode button")) b.classList.toggle("active", b.dataset.mode === state.mode);
  autoGrow();
  updateSendState();
}

function updateSendState() {
  const hasContent = cInput.value.trim() || state.docs.length;
  const ok = state.current === null ? cCompany.value.trim() && hasContent : (state.mode === "search" ? cInput.value.trim() : hasContent);
  cSend.disabled = state.busy || !ok;
}

function autoGrow() {
  cInput.style.height = "auto";
  cInput.style.height = Math.min(cInput.scrollHeight, 220) + "px";
}

function renderAttachments() {
  const box = $("#attachments");
  box.replaceChildren(...state.docs.map((doc, i) => el("div", { class: "attachment", title: doc.title || doc.text.slice(0, 80) },
    icon(ICONS.doc),
    el("div", { class: "a-text" },
      el("div", { class: "a-title" }, doc.title || "未命名文本"),
      el("div", { class: "a-meta" }, `${doc.text.length.toLocaleString()} 字`),
    ),
    el("button", { class: "icon-btn", type: "button", "aria-label": "移除", onclick: () => { state.docs.splice(i, 1); renderAttachments(); updateSendState(); } }, icon(ICONS.close)),
  )));
}

function parseUrls(text) {
  return text.split(/[\s,，]+/).map((s) => s.trim()).filter(Boolean)
    .map((s) => (/^https?:\/\//i.test(s) ? s : `https://${s}`));
}

async function submit() {
  if (cSend.disabled) return;
  if (state.current === null) return startResearch();
  if (state.mode === "search") return runSearch();
  return addMaterials();
}

// ---------------- 任务：研究 / 补充 / 检索 ----------------

function userMessage(text, sub) {
  return el("div", { class: "msg-user" }, el("div", { class: "bubble" }, text, sub ? el("span", { class: "sub" }, sub) : null));
}

function settingsLink() {
  return el("a", { href: "#", onclick: (e) => { e.preventDefault(); openSettings(); } }, "打开设置");
}

/** 步骤失败时的说明；设置类问题（HTTP 400）附带“打开设置”入口。 */
function errorDetail(e) {
  return e.status === 400 ? el("span", {}, e.message, " ", settingsLink()) : e.message;
}

function notice(message) {
  const box = el("div", { class: "notice" }, message);
  if (/设置/.test(message)) {
    box.append(" ", settingsLink());
  }
  return box;
}

class Steps {
  constructor() { this.node = el("ul", { class: "steps" }); }
  add(text) {
    const li = el("li", { class: "running" }, el("span", { class: "dot" }), el("span", {}, el("span", { class: "label" }, text)));
    this.node.append(li);
    scrollToBottom();
    return {
      done: (label, detail) => this._finish(li, "done", label, detail),
      fail: (label, detail) => this._finish(li, "error", label, detail),
    };
  }
  _finish(li, cls, label, detail) {
    li.className = cls;
    if (label) $(".label", li).textContent = label;
    if (detail) $(".label", li).parentNode.append(el("span", { class: "detail" }, detail));
  }
}

function describeMaterials(urls, docs) {
  const parts = [];
  if (urls.length) parts.push(`${urls.length} 个网址`);
  if (docs.length) parts.push(`${docs.length} 段文本`);
  return parts.join(" · ");
}

function failureList(failures) {
  if (!failures.length) return null;
  return el("span", {}, `${failures.length} 个网址未能抓取：`,
    el("ul", {}, failures.map((f) => el("li", {}, `${f.url}（${f.error}）`))));
}

async function runIngest(steps, company, urls, docs, crawl) {
  const step = steps.add(urls.length ? `正在抓取网页并整理资料…` : "正在整理资料…");
  try {
    const res = await api("/ingest", { method: "POST", body: { company, urls, crawl, documents: docs } });
    if (!res.documents) {
      step.fail("没有获取到可用资料", failureList(res.failures));
      return null;
    }
    step.done(`已入库 ${res.documents} 份资料，切分为 ${res.chunks} 段`, failureList(res.failures));
    return res;
  } catch (e) {
    step.fail("资料入库失败", errorDetail(e));
    return null;
  }
}

async function runProfile(steps, company) {
  const step = steps.add("正在检索资料并生成画像，通常需要几十秒…");
  try {
    const profile = await api("/profile", { method: "POST", body: { company, language: $("#c-lang").value } });
    step.done("画像已生成");
    return profile;
  } catch (e) {
    step.fail("画像生成失败", errorDetail(e));
    return null;
  }
}

async function withBusy(fn) {
  state.busy = true;
  updateSendState();
  try { await fn(); } finally {
    state.busy = false;
    updateSendState();
  }
}

async function startResearch() {
  const company = cCompany.value.trim();
  const urls = parseUrls(cInput.value);
  const docs = state.docs.slice();
  const crawl = $("#c-crawl").checked;

  enterCompany(company);
  thread.replaceChildren(userMessage(`研究「${company}」`, describeMaterials(urls, docs)));
  cInput.value = "";
  state.docs = [];
  renderAttachments();
  autoGrow();

  await withBusy(async () => {
    const steps = new Steps();
    thread.append(steps.node);
    const ingested = await runIngest(steps, company, urls, docs, crawl);
    await loadCompanies();
    if (!ingested && !state.companies[company]) return;
    const profile = await runProfile(steps, company);
    if (profile) thread.append(renderProfile(profile));
    scrollToBottom();
  });
}

async function addMaterials() {
  const company = state.current;
  const urls = parseUrls(cInput.value);
  const docs = state.docs.slice();
  thread.append(userMessage("补充资料", describeMaterials(urls, docs)));
  cInput.value = "";
  state.docs = [];
  renderAttachments();
  autoGrow();

  await withBusy(async () => {
    const steps = new Steps();
    thread.append(steps.node);
    const ingested = await runIngest(steps, company, urls, docs, $("#c-crawl").checked);
    await loadCompanies();
    if (!ingested) return;
    const profile = await runProfile(steps, company);
    if (profile) thread.append(renderProfile(profile));
    scrollToBottom();
  });
}

async function regenerate() {
  if (state.busy) return toast("请等待当前任务完成");
  const company = state.current;
  if ($(".empty-state", thread)) thread.replaceChildren();
  thread.append(userMessage("重新生成画像"));
  await withBusy(async () => {
    const steps = new Steps();
    thread.append(steps.node);
    const profile = await runProfile(steps, company);
    if (profile) thread.append(renderProfile(profile));
    scrollToBottom();
  });
}

async function runSearch() {
  const query = cInput.value.trim();
  const company = state.current;
  thread.append(userMessage(query));
  cInput.value = "";
  autoGrow();
  await withBusy(async () => {
    try {
      const hits = await api("/search", { method: "POST", body: { company, query, top_k: 5 } });
      thread.append(renderHits(hits));
    } catch (e) {
      thread.append(notice(e.message));
    }
    scrollToBottom();
  });
}

function renderHits(hits) {
  if (!hits.length) return el("p", { class: "hint" }, "没有找到相关内容。");
  return el("div", { class: "hits" }, el("div", { class: "hits-title" }, `找到 ${hits.length} 段相关资料`), hits.map((h) => el("div", { class: "hit" },
    el("div", { class: "hit-meta" },
      el("a", { href: h.chunk.url, target: "_blank", rel: "noopener" }, h.chunk.title || hostOf(h.chunk.url)),
      el("span", {}, `相似度 ${(1 - h.distance).toFixed(2)}`),
    ),
    el("p", { class: "hit-text" }, h.chunk.text),
  )));
}

// ---------------- 画像渲染 ----------------

const SECTIONS = [
  ["business_lines", "业务线", "Business Lines"],
  ["product_categories", "产品类别", "Product Categories"],
  ["target_markets", "目标市场", "Target Markets"],
];

/** 按首次出现顺序给来源编号，同一画像内相同来源共用一个序号。 */
function numberSources(profile) {
  const order = new Map();
  const visit = (cites) => cites.forEach((c) => { if (!order.has(c.source_id)) order.set(c.source_id, { n: order.size + 1, ...c }); });
  visit(profile.summary_citations);
  for (const [key] of SECTIONS) profile[key].forEach((item) => visit(item.citations));
  return order;
}

let docSeq = 0;

function renderProfile(profile) {
  const sources = numberSources(profile);
  const docId = `doc${++docSeq}`;
  const sup = (cites) => cites.map((c) => {
    const s = sources.get(c.source_id);
    return el("sup", {}, el("a", {
      href: `#${docId}-src-${s.n}`, title: `${s.title}\n${s.snippet.slice(0, 160)}`,
      onclick: (e) => {
        e.preventDefault();
        const target = document.getElementById(`${docId}-src-${s.n}`);
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.remove("flash"); void target.offsetWidth; target.classList.add("flash");
      },
    }, s.n));
  });

  const doc = el("article", { class: "doc" },
    el("h1", {}, profile.company),
    el("div", { class: "meta" }, `${formatTime(profile.generated_at)} · ${profile.model} · 引用 ${sources.size} 处资料`),
    el("p", { class: "lead" }, profile.summary, sup(profile.summary_citations)),
  );

  for (const [key, zh] of SECTIONS) {
    const items = profile[key];
    doc.append(el("h2", {}, zh, el("span", { class: "count" }, items.length || "")));
    if (!items.length) doc.append(el("p", { class: "none" }, "资料中没有相关信息"));
    for (const item of items) {
      doc.append(el("div", { class: "item" }, el("h3", {}, item.name), el("p", {}, item.description, sup(item.citations))));
    }
  }

  doc.append(el("section", { class: "sources" },
    el("h2", {}, "来源"),
    el("ol", {}, [...sources.values()].map((s) => el("li", { id: `${docId}-src-${s.n}` },
      el("span", { class: "n" }, s.n),
      el("div", { class: "s-body" },
        /^https?:/i.test(s.url)
          ? el("a", { class: "s-title", href: s.url, target: "_blank", rel: "noopener" }, s.title || hostOf(s.url))
          : el("span", { class: "s-title" }, s.title || s.url),
        /^https?:/i.test(s.url) ? el("span", { class: "s-url" }, s.url) : el("span", { class: "s-url" }, "手动添加的文本资料"),
        el("details", {}, el("summary", {}, "引用原文"), el("blockquote", {}, s.snippet)),
      ),
    ))),
  ));

  if (profile.warnings.length) {
    doc.append(el("details", { class: "warnings" },
      el("summary", {}, `已自动剔除 ${profile.warnings.length} 处无法核实的内容`),
      el("ul", {}, profile.warnings.map((w) => el("li", {}, w))),
    ));
  }

  const md = () => profileMarkdown(profile, sources);
  const fileBase = `${profile.company}-企业画像`;
  doc.append(el("div", { class: "doc-actions" },
    el("button", { class: "icon-btn", onclick: () => copyText(md()) }, icon(ICONS.copy), "复制"),
    el("button", { class: "icon-btn", onclick: () => downloadFile(`${fileBase}.md`, md(), "text/markdown") }, icon(ICONS.download), "导出 Markdown"),
    el("button", { class: "icon-btn", onclick: () => downloadFile(`${fileBase}.json`, JSON.stringify(profile, null, 2), "application/json") }, icon(ICONS.download), "导出 JSON"),
  ));
  return doc;
}

function profileMarkdown(profile, sources) {
  const refs = (cites) => cites.map((c) => `[${sources.get(c.source_id).n}]`).join("");
  const lines = [`# ${profile.company}`, "", `${profile.summary}${refs(profile.summary_citations)}`, ""];
  for (const [key, zh] of SECTIONS) {
    lines.push(`## ${zh}`, "");
    if (!profile[key].length) lines.push("资料中没有相关信息", "");
    for (const item of profile[key]) lines.push(`- **${item.name}**：${item.description}${refs(item.citations)}`);
    lines.push("");
  }
  lines.push("## 来源", "");
  for (const s of sources.values()) lines.push(/^https?:/i.test(s.url) ? `${s.n}. [${s.title || s.url}](${s.url})` : `${s.n}. ${s.title || "手动添加的文本资料"}`);
  lines.push("", `> 生成时间：${formatTime(profile.generated_at)} · 模型：${profile.model}`);
  return lines.join("\n");
}

// ---------------- 文本资料对话框 ----------------

function openDocDialog() {
  for (const id of ["doc-title", "doc-url", "doc-text"]) $(`#${id}`).value = "";
  $("#doc-type").value = "press_release";
  $("#dlg-doc").showModal();
  $("#doc-title").focus();
}

$("#btn-doc-ok").addEventListener("click", () => {
  const text = $("#doc-text").value.trim();
  if (!text) return $("#doc-text").focus();
  const title = $("#doc-title").value.trim();
  state.docs.push({
    title,
    // 未填网址时生成唯一标识，避免同名文本互相覆盖
    url: $("#doc-url").value.trim() || `paste://${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    source_type: $("#doc-type").value,
    text,
  });
  $("#dlg-doc").close();
  renderAttachments();
  updateSendState();
  cInput.focus();
});

// ---------------- 设置 ----------------

const settingsUI = {
  llm: { preset: $("#llm-preset"), baseUrl: $("#llm-base-url"), model: $("#llm-model"), key: $("#llm-key"), models: $("#llm-models"), link: $("#llm-key-link"), check: $("#llm-check") },
  embedding: { preset: $("#emb-preset"), baseUrl: $("#emb-base-url"), model: $("#emb-model"), key: $("#emb-key"), models: $("#emb-models"), link: $("#emb-key-link"), check: $("#emb-check"), batch: $("#emb-batch") },
};

function fillPresetOptions(kind) {
  const ui = settingsUI[kind];
  ui.preset.replaceChildren(...Object.entries(state.presets[kind]).map(([id, p]) => el("option", { value: id }, p.label)));
}

function applyPreset(kind, presetId, saved) {
  const ui = settingsUI[kind];
  const preset = state.presets[kind][presetId];
  const sameAsSaved = saved && saved.preset === presetId;
  ui.preset.value = presetId;
  ui.baseUrl.value = sameAsSaved ? saved.base_url : preset.base_url;
  ui.model.value = sameAsSaved ? saved.model : (preset.models[0] || "");
  ui.models.replaceChildren(...preset.models.map((m) => el("option", { value: m })));
  ui.key.value = "";
  ui.key.placeholder = sameAsSaved && saved.has_api_key ? `已保存 ${saved.api_key_hint}（留空保持不变）` : "粘贴 API Key";
  ui.link.hidden = !preset.key_url;
  if (preset.key_url) ui.link.href = preset.key_url;
  ui.check.textContent = "";
  ui.check.className = "check-result";
  if (kind === "llm") {
    $("#llm-base-url-field").hidden = preset.provider === "anthropic";
  } else {
    $("#emb-api-fields").hidden = preset.provider === "local";
    ui.batch.value = sameAsSaved ? saved.batch_size : 10;
  }
}

function readSettingsForm() {
  const read = (kind) => {
    const ui = settingsUI[kind];
    const preset = state.presets[kind][ui.preset.value];
    return {
      preset: ui.preset.value,
      provider: preset.provider,
      api_key: ui.key.value.trim(),
      base_url: ui.baseUrl.value.trim(),
      model: ui.model.value.trim(),
    };
  };
  return { llm: read("llm"), embedding: { ...read("embedding"), batch_size: Number(settingsUI.embedding.batch.value) || 10 } };
}

function openSettings(firstRun = false) {
  $("#settings-intro").textContent = firstRun
    ? "欢迎使用 Seek。开始之前，请选择你自己的大模型和向量化服务并填写 API Key。密钥只保存在这台电脑上。"
    : "选择你自己的 API 服务商并填写密钥。密钥只保存在这台电脑上。";
  applyPreset("llm", state.settings.llm.preset, state.settings.llm);
  applyPreset("embedding", state.settings.embedding.preset, state.settings.embedding);
  $("#dlg-settings").showModal();
}

for (const kind of ["llm", "embedding"]) {
  settingsUI[kind].preset.addEventListener("change", (e) => applyPreset(kind, e.target.value, state.settings[kind]));
}

$("#btn-test-settings").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = "测试中…";
  for (const kind of ["llm", "embedding"]) {
    settingsUI[kind].check.className = "check-result";
    settingsUI[kind].check.textContent = "正在连接…";
  }
  try {
    const res = await api("/settings/test", { method: "POST", body: readSettingsForm() });
    for (const kind of ["llm", "embedding"]) {
      const r = res[kind];
      settingsUI[kind].check.className = `check-result ${r.ok ? "ok" : "err"}`;
      settingsUI[kind].check.textContent = (r.ok ? "✓ " : "✕ ") + r.message;
    }
  } catch (err) {
    settingsUI.llm.check.className = "check-result err";
    settingsUI.llm.check.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "测试连接";
  }
});

$("#btn-save-settings").addEventListener("click", async () => {
  try {
    state.settings = await api("/settings", { method: "PUT", body: readSettingsForm() });
    $("#dlg-settings").close();
    updateModelBadge();
    toast("设置已保存");
    await loadCompanies();
    if (state.current) openCompany(state.current);
  } catch (e) {
    toast(e.message);
  }
});

// ---------------- 事件绑定 ----------------

$("#btn-new").addEventListener("click", () => { if (!state.busy) goHome(); });
$("#btn-settings").addEventListener("click", () => openSettings());
$("#btn-collapse").addEventListener("click", () => $("#app").classList.add("collapsed"));
$("#btn-expand").addEventListener("click", () => $("#app").classList.remove("collapsed"));
$("#c-attach").addEventListener("click", openDocDialog);
cSend.addEventListener("click", submit);

for (const b of document.querySelectorAll("#c-mode button")) {
  b.addEventListener("click", () => { state.mode = b.dataset.mode; updateComposer(); cInput.focus(); });
}

cCompany.addEventListener("input", updateSendState);
cCompany.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); cInput.focus(); }
});
cInput.addEventListener("input", () => { autoGrow(); updateSendState(); });
cInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.isComposing) return;
  // 检索模式回车发送；网址输入需要换行，用 Ctrl/⌘ + Enter 发送
  if ((state.current !== null && state.mode === "search" && !e.shiftKey) || e.ctrlKey || e.metaKey) {
    e.preventDefault();
    submit();
  }
});

// ---------------- 启动 ----------------

(async function init() {
  try {
    [state.presets, state.settings] = await Promise.all([api("/presets"), api("/settings")]);
  } catch (e) {
    thread.append(notice(`无法连接本地服务：${e.message}`));
    return;
  }
  if (window.innerWidth < 720) $("#app").classList.add("collapsed");
  fillPresetOptions("llm");
  fillPresetOptions("embedding");
  updateModelBadge();
  goHome();
  await loadCompanies();
  const { llm, embedding } = state.settings;
  if (!llm.has_api_key || (embedding.provider === "api" && !embedding.has_api_key)) openSettings(true);
})();
