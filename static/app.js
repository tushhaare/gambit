// Gambit — poster & thumbnail studio (vanilla JS)
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const icon = (n) => `<svg class="ic"><use href="#i-${n}"/></svg>`;

let seriesList = [];
let current = null;
let logSince = 0;
let lastState = "idle";
let lastSig = "";
let sortable = null;

// ---------- helpers ----------
async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  if (r.status === 401) { window.location = "/login"; throw new Error("login"); }
  if (r.status === 403) { toast("Ye sirf admin kar sakta hai"); throw new Error("forbidden"); }
  if (!r.ok) {
    let t = await r.text();
    if (/^\s*<(!doctype|html)/i.test(t)) {
      const m = t.match(/<title>([^<]*)<\/title>/i);
      t = r.status === 524 || r.status === 504 ? "Link ne time-out kar diya (server ka jawab der se aaya). Dobara try karo."
        : r.status === 502 || r.status === 530 ? "Hub tak link nahi pahuncha — hub PC / run.bat chal raha hai?" : (m ? m[1] : "server error");
    }
    throw new Error(`${r.status}: ${t.slice(0, 300)}`);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2800);
}
const debounce = (fn, ms = 600) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };
const esc = s => (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const imgUrl = it => `/api/items/${it.id}/image?t=${encodeURIComponent(it.updated_at || "")}`;
const posterUrl = it => `/api/items/${it.id}/poster?t=${encodeURIComponent(it.updated_at || "")}`;
// chhoti preview images (tez loading) — full image sirf preview / "Open full size" mein
const thumbUrl = (it, s = 320, of = "image") => `/api/items/${it.id}/thumb?of=${of}&s=${s}&t=${encodeURIComponent((it.updated_at || "") + (of === "poster" ? "p" : ""))}`;
const shortTag = it => it.kind === "series" ? "S" : ((it.label.match(/EP\s*0*(\d+)/i) || [])[1] ? "EP" + it.label.match(/EP\s*0*(\d+)/i)[1].padStart(2, "0") : "EP");

// final file naming (backend jaisa hi)
const cleanName = t => (t || "").replace(/[\\/:*?"<>|]/g, " ").replace(/\s+/g, " ").replace(/^[\s.\-—–]+|[\s.\-—–]+$/g, "") || "Untitled";
const niceCase = t => { const l = t.replace(/[^A-Za-z]/g, ""); return l && l === l.toUpperCase() ? t.split(" ").map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(" ") : t; };
const episodeTitle = l => niceCase((l || "").replace(/^\s*(EP(ISODE)?\s*\d+)\s*[:\-—–|.]*\s*/i, "").replace(/^["“”\s]+|["“”\s]+$/g, ""));
const defaultFinal = it => it.kind === "series" ? cleanName(current.name) : cleanName(episodeTitle(it.label) || it.label);
const finalFiles = it => { const b = it.final_name && it.final_name.trim() ? cleanName(it.final_name) : defaultFinal(it); return it.kind === "series" ? [`${b}.webp`, `${b} (Series Thumbnail).webp`] : [`${b}.webp`]; };

function openModal(id) { $(id).classList.remove("hidden"); const f = $(id).querySelector("input:not([type=checkbox]),textarea,select"); f && setTimeout(() => f.focus(), 30); }
function closeModals() { $$(".modal").forEach(m => m.classList.add("hidden")); }
function confirmBox(text, { title = "Are you sure?", ok = "OK", danger = false } = {}) {
  return new Promise(res => {
    $("#cTitle").textContent = title; $("#cText").textContent = text;
    const yes = $("#cYes"); yes.textContent = ok;
    yes.className = "btn " + (danger ? "btn-stop" : "btn-primary");
    openModal("#confirmModal");
    const done = v => { $("#confirmModal").classList.add("hidden"); yes.onclick = $("#cNo").onclick = null; res(v); };
    yes.onclick = () => done(true); $("#cNo").onclick = () => done(false);
  });
}

// ---------- sidebar ----------
async function loadSeriesList() { seriesList = await api("GET", `/api/series${ws ? "?workspace=" + ws.id : ""}`); renderSeriesList(); const c = $("#sideCount"); if (c) c.textContent = seriesList.length || ""; }
function renderSeriesList() {
  const q = $("#seriesSearch").value.toLowerCase();
  const list = seriesList.filter(s => s.name.toLowerCase().includes(q));
  $("#seriesList").innerHTML = list.map(s => {
    const ticks = Array.from({ length: Math.min(s.total, 14) }, (_, i) => {
      const scale = s.total / Math.min(s.total, 14), idx = i * scale;
      return `<i class="${idx < s.done ? "done" : idx < s.done + s.failed ? "failed" : ""}"></i>`;
    }).join("");
    return `<button class="s-item ${current && current.id === s.id ? "active" : ""}" data-id="${s.id}">
      <div class="s-name">${esc(s.name)}</div>
      <div class="s-meta"><span>${s.done}/${s.total} ready</span>${s.failed ? `<span class="bad">${s.failed} failed</span>` : ""}<span>${s.engine === "api" ? "API" : false ? "" : "ChatGPT"}</span></div>
      ${s.total ? `<div class="s-ticks">${ticks}</div>` : ""}</button>`;
  }).join("") || `<div class="side-empty">${q ? "Koi match nahi." : "Abhi koi series nahi."}</div>`;
  $$(".s-item").forEach(el => el.onclick = () => openSeries(+el.dataset.id));
}

// ---------- series ----------
async function openSeries(id) {
  current = await api("GET", `/api/series/${id}`);
  if (ws && current.workspace_id && current.workspace_id !== ws.id) { setWorkspace(current.workspace_id, true); loadSeriesList(); }
  try { localStorage.setItem("kfm_lastSeries", id); } catch (e) {}
  showView("series");
  renderProjMeta(); renderRefs();
  $("#seriesName").value = current.name;
  varSel = current.active_variant || 0;
  renderVariants(true); renderChars();
  renderEngine();
  renderItems(true); renderSeriesList();
}
async function refreshCurrent() {
  if (!current) return;
  const f = await api("GET", `/api/series/${current.id}`);
  Object.assign(current, { items: f.items, chat_url: f.chat_url, folder: f.folder });
  if (JSON.stringify((f.variants || []).map(v => v.has_chat)) !== JSON.stringify((current.variants || []).map(v => v.has_chat))) {
    current.variants = current.variants.map((v, i) => Object.assign(v, { has_chat: !!(f.variants[i] || {}).has_chat })); renderVariants(false);
  }
  renderItems(false);
}
const saveSeries = debounce(async fields => {
  if (!current) return;
  await api("PUT", `/api/series/${current.id}`, fields);
  Object.assign(current, fields);
  if ("master_prompt" in fields) current.chat_url = "";
  renderChatLine(); loadSeriesList();
}, 700);

// ---------- v3.5: master variants + character sheet ----------
let varSel = 0;
const LETTERS = "ABCDEF";
function applySeriesResp(r) {
  if (!r || !r.id || !current || r.id !== current.id) return;
  Object.assign(current, { variants: r.variants, active_variant: r.active_variant, master_prompt: r.master_prompt,
    chat_url: r.chat_url, characters: r.characters });
  if (varSel >= current.variants.length) varSel = current.active_variant;
  renderVariants(document.activeElement !== $("#masterPrompt")); renderChatLine(); renderItems(false);
}
const putSeries = async fields => { const r = await api("PUT", `/api/series/${current.id}`, fields); applySeriesResp(r); return r; };
const saveVariants = debounce(() => putSeries({ variants: current.variants.map(v => ({ name: v.name, angle: v.angle, prompt: v.prompt })) }), 700);
const saveChars = debounce(() => putSeries({ characters: current.characters }), 1200);
function nextVariantOf(it) {
  const n = (current.variants || []).length; if (n <= 1) return 0;
  const base = it.variant != null && it.variant >= 0 ? it.variant : current.active_variant || 0;
  return (base + 1) % n;
}
function renderVariants(fillText) {
  const vs = current.variants || [], act = current.active_variant || 0;
  $("#variantCount").textContent = vs.length > 1 ? vs.length : "";
  $("#variantTabs").innerHTML = vs.map((v, i) => `<button class="var-tab${i === varSel ? " sel" : ""}" role="tab" aria-selected="${i === varSel}" data-i="${i}" title="${esc(v.angle || v.name)}">
      <b>${LETTERS[i] || i + 1}</b><span>${esc((v.name || "").replace(/^[A-F]\s*[—-]\s*/, "") || "Variant")}</span>
      ${i === act ? `<em class="var-act">Active</em>` : ""}${v.has_chat ? `<i class="dot on" title="Iski ChatGPT chat bani hui hai"></i>` : ""}</button>`).join("")
    + `<button class="var-tab var-add" id="varAdd" title="Selected variant ki copy se naya variant">+ Variant</button>`;
  const v = vs[varSel] || {};
  $("#variantMeta").innerHTML = vs.length ? `<span class="hint">${v.angle ? esc(v.angle) : (vs.length > 1 ? "" : "Ek hi master hai. \"+ Variant\" se B/C banao (light/angle badal ke) — Regenerate unhi se alag image banayega.")}</span>
    <span class="var-btns">${varSel !== act ? `<button class="btn btn-ghost btn-sm" id="varActivate">Isko active banao</button>` : ""}
    ${vs.length > 1 ? `<button class="btn btn-ghost btn-sm" id="varDel">Hatao</button>` : ""}</span>` : "";
  if (fillText) $("#masterPrompt").value = v.prompt || "";
  $$("#variantTabs .var-tab[data-i]").forEach(b => b.onclick = () => { varSel = +b.dataset.i; renderVariants(true); });
  $("#varAdd").onclick = () => {
    if (vs.length >= 6) return toast("Max 6 variants");
    const src = vs[varSel] || { prompt: $("#masterPrompt").value };
    vs.push({ name: `${LETTERS[vs.length]} — Copy of ${LETTERS[varSel]}`, angle: "Copy — light/angle badal ke likho", prompt: src.prompt, has_chat: false });
    varSel = vs.length - 1; renderVariants(true); saveVariants(); $("#masterPrompt").focus();
  };
  const a = $("#varActivate"); if (a) a.onclick = () => putSeries({ active_variant: varSel }).then(() => toast(`${LETTERS[varSel]} ab active — Generate isi se`));
  const d = $("#varDel"); if (d) d.onclick = async () => {
    if (!await confirmBox(`Variant ${LETTERS[varSel]} hata dein?`, { title: "Variant hatao", ok: "Hatao", danger: true })) return;
    vs.splice(varSel, 1);
    let na = current.active_variant; if (varSel < na) na--; if (na >= vs.length) na = 0;
    varSel = na; current.active_variant = na;
    await putSeries({ variants: vs.map(v => ({ name: v.name, angle: v.angle, prompt: v.prompt })), active_variant: na });
  };
}
function renderChars() {
  const cs = current.characters || [];
  $("#charCount").textContent = cs.length || "";
  $("#charList").innerHTML = cs.map((c, i) => `<div class="char" data-i="${i}">
      <div class="char-top"><input class="char-name" value="${esc(c.name || "")}" placeholder="NAAM" aria-label="Naam">
      <input class="char-role" value="${esc(c.role || "")}" placeholder="role (jaise: main lead, maa)" aria-label="Role">
      <button class="btn btn-icon btn-danger-ghost" data-del aria-label="Hatao">${icon("trash")}</button></div>
      <textarea class="char-look" rows="2" placeholder="Fixed look: umar, chehra, skin, aankhen, baal, nishaan, kapde ke rang…" aria-label="Look">${esc(c.look || "")}</textarea></div>`).join("")
    || `<p class="empty-note">Recurring characters ka fixed look yahan likho — har variant ke master mein khud jud jaata hai, chehra har poster mein same.</p>`;
  $$("#charList .char").forEach(el => {
    const i = +el.dataset.i, c = cs[i];
    el.querySelector(".char-name").oninput = e => { c.name = e.target.value; saveChars(); };
    el.querySelector(".char-role").oninput = e => { c.role = e.target.value; saveChars(); };
    el.querySelector(".char-look").oninput = e => { c.look = e.target.value; saveChars(); };
    el.querySelector("[data-del]").onclick = () => { cs.splice(i, 1); renderChars(); saveChars(); };
  });
}

function renderEngine() {
  $$(".seg-btn[data-engine]").forEach(b => { const on = b.dataset.engine === current.engine; b.classList.toggle("on", on); b.setAttribute("aria-checked", on); });
  $("#runOnWrap").classList.toggle("hidden", current.engine !== "browser");
  renderRunOn();
  renderChatLine();
}

// ---------- team / run on ----------
let me = null, team = [], agentsState = [];
function renderRunOn() {
  if (!current) return;
  const sel = $("#runOnSel"), val = current.run_on || "hub";
  const online = id => (agentsState.find(a => a.id === id) || {}).online;
  const opts = [`<option value="hub">Hub PC ka ChatGPT</option>`]
    .concat(team.map(u => `<option value="user:${u.id}">${online(u.id) ? "● " : "○ "}${esc(u.name)} ka ChatGPT${online(u.id) ? "" : " (offline)"}</option>`));
  const html = opts.join("");
  if (sel.dataset.html !== html) { sel.innerHTML = html; sel.dataset.html = html; }
  sel.value = val;
  if (sel.value !== val) sel.value = "hub";
}
// ---------- aaj ka team link + one-line command ----------
let linkInfo = null;
async function loadLink() {
  try { linkInfo = await api("GET", "/api/link"); } catch (e) { return; }
  const t = linkInfo.tunnel || {};
  const dot = $("#linkDot");
  dot.className = "dot " + (t.status === "on" ? "on" : t.status === "error" ? "err" : t.status === "starting" ? "wait" : "on");
  $("#linkUrl").textContent = t.status === "starting" ? "ban raha hai…" : (t.status === "error" ? "link nahi bana — log dekho" : linkInfo.url.replace(/^https?:\/\//, ""));
  $("#psCmd").textContent = linkInfo.ps;
  $("#macCmd").textContent = linkInfo.mac;
  if (t.status === "starting") setTimeout(loadLink, 3000);
}
async function copyText(txt, msg) {
  try { await navigator.clipboard.writeText(txt); }
  catch (e) { const ta = document.createElement("textarea"); ta.value = txt; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); }
  toast(msg);
}

async function loadTeam() {
  try { const r = await api("GET", "/api/team"); team = r.users; me = r.me; } catch (e) { return; }
  document.body.classList.toggle("is-admin", me && me.role === "admin");
  $("#meName").textContent = me ? me.name : "";
  $("#meRole").textContent = me ? (me.role === "admin" ? "Admin · hub" : "Teammate") : "";
  $("#meAvatar").textContent = me ? me.name.charAt(0).toUpperCase() : "?";
  renderRunOn(); renderTeamList();
  if (ws) setWorkspace(ws.id, true);
}
function renderAgents(agents) {
  agentsState = agents || [];
  const mine = agentsState.find(a => me && a.id === me.id);
  $("#myAgentDot").classList.toggle("on", !!(mine && mine.online));
  $("#myAgentState").innerHTML = mine && mine.online ? `<span class="dot on"></span>Aapka agent online hai`
    : (me && me.role === "admin" ? `<span class="dot"></span>Aap hub PC pe ho — "Hub PC ka ChatGPT" seedha chalta hai, agent ki zaroorat nahi` : `<span class="dot"></span>Aapka agent abhi offline hai`);
  $("#agentsLine").innerHTML = agentsState.filter(a => a.online || a.job).map(a =>
    `<span class="agent-chip ${a.online ? "on" : ""} ${a.job ? "busy" : ""}" title="${a.job ? esc(a.job.series) : ""}"><span class="dot ${a.online ? "on" : ""}"></span>${esc(a.name)}${a.job ? ` · ${a.job.status === "queued" ? "waiting" : esc(a.job.label || "start")}` : ""}</span>`).join("");
  renderRunOn();
}
function renderTeamList() {
  const box = $("#teamList"); if (!box) return;
  const online = id => (agentsState.find(a => a.id === id) || {}).online;
  const admin = me && me.role === "admin";
  box.innerHTML = team.map(u => `<div class="tm"><span class="dot ${online(u.id) ? "on" : ""}"></span>
    <span class="tm-name">${esc(u.name)}<small>${u.role === "admin" ? "admin" : "teammate"}${online(u.id) ? " · agent online" : ""}</small></span>
    ${admin && u.id !== me.id ? `<button class="btn btn-ghost" data-pw="${u.id}">Reset password</button><button class="btn btn-ghost" data-key="${u.id}" title="Purana agent.json band ho jaayega">New agent key</button><button class="btn btn-icon btn-danger-ghost" data-del="${u.id}" aria-label="Remove">${icon("trash")}</button>` : ""}</div>`).join("");
  $$("[data-pw]", box).forEach(b => b.onclick = async () => {
    const pw = prompt("Naya password (6+ characters):"); if (!pw) return;
    const r = await api("POST", `/api/team/${b.dataset.pw}/reset`, { password: pw }); toast(r.ok ? "Password badal gaya" : r.msg);
  });
  $$("[data-key]", box).forEach(b => b.onclick = async () => {
    if (!await confirmBox("Is teammate ka purana agent.json kaam karna band kar dega. Unhe naya agent.json download karna padega.", { title: "New agent key", ok: "Make new key" })) return;
    await api("POST", `/api/team/${b.dataset.key}/reset`, { new_key: true }); toast("Naya key ban gaya");
  });
  $$("[data-del]", box).forEach(b => b.onclick = async () => {
    const u = team.find(x => x.id === +b.dataset.del);
    if (!await confirmBox(`${u.name} ko team se hata dein? Unka login aur agent band ho jaayega.`, { title: "Remove teammate", ok: "Remove", danger: true })) return;
    const r = await api("DELETE", `/api/team/${u.id}`); if (!r.ok) return toast(r.msg);
    await loadTeam();
  });
}
async function downloadZip(what) {
  if (what === "excel") { window.location = `/api/series/${current.id}/export`; return; }
  const r = await fetch(`/api/series/${current.id}/download/${what}`);
  if (!r.ok) { let m = "Download nahi hua"; try { m = (await r.json()).msg || m; } catch (e) {} return toast(m); }
  const blob = await r.blob();
  const cd = r.headers.get("content-disposition") || "";
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = m ? decodeURIComponent(m[1]) : `${what}.zip`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
function renderChatLine() {
  const el = $("#chatLine");
  if (current.engine === "api") { el.textContent = "OpenAI API engine — har image = master prompt + brief. Settings mein API key chahiye."; return; }
  el.innerHTML = current.chat_url
    ? `ChatGPT chat (${LETTERS[current.active_variant || 0]}): <a href="${esc(current.chat_url)}" target="_blank">${esc(current.chat_url)}</a> · <button class="link" id="resetChat">Agli baar nayi chat</button>`
    : "Agli baar Generate par nayi ChatGPT chat banegi, pehle master prompt jaayega.";
  const r = $("#resetChat");
  if (r) r.onclick = async () => { await putSeries({ reset_chat: true }); toast("Agli baar har variant ki nayi chat banegi"); };
}

// ---------- reel + stats ----------
function renderReel() {
  const strip = $("#reelStrip");
  strip.innerHTML = current.items.map(it => `
    <div class="frame ${it.kind} ${it.status}" data-id="${it.id}" title="${esc(it.label)} — ${it.status}">
      ${it.image_path ? `<img src="${thumbUrl(it, 160)}" alt="" loading="lazy" decoding="async"><span class="tag">${shortTag(it)}</span>` : shortTag(it)}
    </div>`).join("") || `<div class="reel-empty">Briefs add karo — har thumbnail yahan ek frame banega.</div>`;
  $$(".frame", strip).forEach(f => f.onclick = () => {
    const card = $(`.card[data-id="${f.dataset.id}"]`);
    card && card.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  const c = { done: 0, pending: 0, queued: 0, running: 0, failed: 0 };
  current.items.forEach(i => c[i.status] = (c[i.status] || 0) + 1);
  const label = { done: "ready", pending: "pending", queued: "queued", running: "running", failed: "failed" };
  $("#stats").innerHTML = Object.keys(c).filter(k => c[k] || k === "done" || k === "pending")
    .map(k => `<span class="st ${k}"><b>${c[k]}</b>${label[k]}</span>`).join("");
  $("#itemCount").textContent = current.items.length ? current.items.length : "";
}

// ---------- item cards ----------
function cardHTML(it) {
  const thumb = it.image_path
    ? `<img src="${thumbUrl(it, 256)}" alt="" loading="lazy" decoding="async">`
    : (it.status === "running" ? "Ban raha hai…" : "Image drop karo<br>ya generate");
  return `<article class="card ${it.kind} ${it.status}" data-id="${it.id}">
    <div class="handle" title="Drag karke order badlo">${icon("grip")}</div>
    <div class="thumb ${it.image_path ? "has" : ""} ${it.status}" title="Click = preview · image drop = manual upload">${thumb}</div>
    <div class="card-body">
      <div class="card-top">
        <span class="kind ${it.kind}">${it.kind === "series" ? "Series" : "Episode"}</span>
        <input class="label-input" value="${esc(it.label)}" aria-label="Label">
        ${it.poster_path ? `<a class="poster-chip" href="${posterUrl(it)}" target="_blank" title="App poster (2:3)"><img src="${thumbUrl(it, 64, "poster")}" alt="" loading="lazy">Poster</a>` : ""}
        ${(current.variants || []).length > 1 && it.variant != null && it.variant >= 0 ? `<span class="vbadge" title="Master variant ${LETTERS[it.variant]} se bani${it.regen_count ? ` · ${it.regen_count}x regenerate` : ""}">${LETTERS[it.variant] || "?"}</span>` : ""}
        <span class="status ${it.status}">${it.status === "done" ? "ready" : it.status}</span>
      </div>
      <label class="final-row" title="App pe upload hone wali final WebP file ka naam">
        <span class="final-lbl">Final name</span>
        <input class="final-input" value="${esc(it.final_name || "")}" placeholder="${esc(defaultFinal(it))}" aria-label="Final file name">
        <span class="final-files">${finalFiles(it).map(f => `<code>${esc(f)}</code>`).join(" ")}</span>
      </label>
      <textarea class="prompt" rows="3" placeholder="Is thumbnail ka brief…">${esc(it.prompt)}</textarea>
      ${it.error ? `<div class="err">${esc(it.error)}</div>` : ""}
      <div class="card-actions">
        <button class="btn btn-accent" data-act="gen">${icon("play")}${it.image_path ? (rotateOn() && (current.variants || []).length > 1 ? `Regenerate → ${LETTERS[nextVariantOf(it)]}` : "Regenerate") : "Generate"}</button>
        <button class="btn btn-ghost" data-act="copy">${icon("copy")}Copy prompt</button>
        <button class="btn btn-ghost" data-act="upload">${icon("upload")}Upload image</button>
        <button class="btn btn-ghost" data-act="kind">${icon("swap")}${it.kind === "series" ? "Make episode" : "Make series"}</button>
        ${it.status !== "pending" ? `<button class="btn btn-ghost" data-act="reset">${icon("redo")}Mark pending</button>` : ""}
        <button class="btn btn-icon btn-danger-ghost push" data-act="del" title="Delete" aria-label="Delete">${icon("trash")}</button>
      </div>
    </div></article>`;
}
const sig = it => [it.status, it.image_path, it.error, it.updated_at, it.kind, it.poster_path, it.variant, rotateOn(), (current.variants || []).length].join("|");
const rotateOn = () => { const el = $("#rotateChk"); return !el || el.checked; };

function renderItems(full) {
  renderReel(); renderChatLine(); renderGallery();
  const box = $("#items");
  const ids = current.items.map(i => String(i.id));
  const domIds = $$(".card", box).map(c => c.dataset.id);
  if (!full && ids.join() === domIds.join()) {
    current.items.forEach(it => {
      const card = box.querySelector(`.card[data-id="${it.id}"]`);
      if (card.dataset.sig === sig(it)) return;
      if (card.contains(document.activeElement)) { // typing chal rahi hai — sirf status
        const p = card.querySelector(".status"); p.className = `status ${it.status}`; p.textContent = it.status === "done" ? "ready" : it.status;
        return;
      }
      card.outerHTML = cardHTML(it);
      bindCard(box.querySelector(`.card[data-id="${it.id}"]`), it);
    });
    return;
  }
  box.innerHTML = current.items.map(cardHTML).join("") ||
    `<div class="items-empty">Abhi koi brief nahi. <b>Bulk paste</b> karo ya .txt files upar drop karo.</div>`;
  current.items.forEach(it => bindCard(box.querySelector(`.card[data-id="${it.id}"]`), it));
  if (sortable) sortable.destroy();
  sortable = Sortable.create(box, {
    handle: ".handle", animation: 160, ghostClass: "sortable-ghost", chosenClass: "sortable-chosen",
    onEnd: async () => {
      const newIds = $$(".card", box).map(c => +c.dataset.id);
      current.items.sort((a, b) => newIds.indexOf(a.id) - newIds.indexOf(b.id));
      await api("POST", `/api/series/${current.id}/reorder`, { ids: newIds });
      renderReel(); toast("Order save ho gaya");
    },
  });
}

function bindCard(card, it) {
  if (!card) return;
  card.dataset.sig = sig(it);
  const label = card.querySelector(".label-input"), ta = card.querySelector(".prompt"), fin = card.querySelector(".final-input");
  const showFinal = () => {
    Object.assign(it, { label: label.value, final_name: fin.value });
    fin.placeholder = defaultFinal(it);
    card.querySelector(".final-files").innerHTML = finalFiles(it).map(f => `<code>${esc(f)}</code>`).join(" ");
  };
  const save = debounce(async () => {
    await api("PUT", `/api/items/${it.id}`, { label: label.value, prompt: ta.value, final_name: fin.value });
    Object.assign(it, { label: label.value, prompt: ta.value, final_name: fin.value });
  }, 600);
  label.oninput = () => { showFinal(); save(); }; ta.oninput = save; fin.oninput = () => { showFinal(); save(); };
  ta.onfocus = () => ta.rows = 10; ta.onblur = () => ta.rows = 3;

  const thumb = card.querySelector(".thumb");
  thumb.onclick = () => it.image_path ? preview(it) : null;
  thumb.ondragover = e => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); e.stopPropagation(); thumb.classList.add("drop-on"); } };
  thumb.ondragleave = () => thumb.classList.remove("drop-on");
  thumb.ondrop = e => { e.preventDefault(); e.stopPropagation(); thumb.classList.remove("drop-on"); const f = e.dataTransfer.files[0]; if (f && f.type.startsWith("image/")) uploadImage(it, f); };

  card.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
    const act = b.dataset.act;
    if (act === "gen") return generate({ item_ids: [it.id] });
    if (act === "copy") { await navigator.clipboard.writeText(ta.value); return toast("Prompt copy ho gaya"); }
    if (act === "upload") { const inp = document.createElement("input"); inp.type = "file"; inp.accept = "image/*"; inp.onchange = () => inp.files[0] && uploadImage(it, inp.files[0]); return inp.click(); }
    if (act === "kind") { await api("PUT", `/api/items/${it.id}`, { kind: it.kind === "series" ? "episode" : "series" }); return refreshCurrent(); }
    if (act === "reset") { await api("PUT", `/api/items/${it.id}`, { status: "pending", error: "" }); return refreshCurrent(); }
    if (act === "del") {
      if (!await confirmBox(`"${it.label}" ka brief hata dein? Bani hui image folder mein rahegi.`, { title: "Delete thumbnail", ok: "Delete", danger: true })) return;
      await api("DELETE", `/api/items/${it.id}`); await refreshCurrent(); renderItems(true); loadSeriesList();
    }
  });
}

async function uploadImage(it, file) {
  const fd = new FormData(); fd.append("file", file);
  await api("POST", `/api/items/${it.id}/upload`, fd);
  toast(`${it.label}: image save ho gayi`);
  await refreshCurrent(); loadSeriesList();
}
function preview(it) {
  const big = $("#imgBig"); big.src = thumbUrl(it, 1024); $("#imgOpen").href = imgUrl(it); $("#imgCap").textContent = it.label;
  openModal("#imgModal");
}
function renderGallery() {
  const done = current.items.filter(i => i.image_path);
  $("#gallery").innerHTML = done.map(i => `<figure><img data-id="${i.id}" src="${thumbUrl(i, 256)}" loading="lazy" decoding="async" alt="${esc(i.label)}"><figcaption>${esc(i.label)}</figcaption></figure>`).join("")
    || `<div class="gallery-empty">Bani hui images yahan dikhengi.</div>`;
  $$("#gallery img").forEach(img => img.onclick = () => preview(current.items.find(i => i.id === +img.dataset.id)));
}

async function addItem(kind) {
  await api("POST", `/api/series/${current.id}/items`, { kind, prompt: "" });
  await refreshCurrent(); renderItems(true); loadSeriesList();
  const cards = $$(".card"); cards[cards.length - 1]?.querySelector(".prompt").focus();
}
async function addBulk(text, firstIsSeries) {
  const r = await api("POST", `/api/series/${current.id}/items`, { bulk_text: text, first_is_series: firstIsSeries });
  toast(`${r.created.length} brief add hue`);
  current.items = r.series.items; renderItems(true); loadSeriesList();
}

// ---------- generate / status ----------
async function generate(body) {
  if (!current) return;
  body.new_chat = $("#newChatChk").checked;
  body.rotate = rotateOn();
  const r = await api("POST", `/api/series/${current.id}/generate`, body);
  if (!r.ok) return toast(r.msg);
  $("#newChatChk").checked = false;
  if (r.agent) toast(r.online ? `${r.queued} thumbnail ${r.agent} ke ChatGPT pe ja rahe hain` : `${r.agent} ka agent offline hai — chalu hote hi shuru hoga`);
  else toast(`${r.queued} thumbnail queue mein`);
  if (r.variants && Object.keys(r.variants).length > 1) setTimeout(() => toast("Variants: " + Object.entries(r.variants).map(([k, n]) => `${k.split(" ")[0]} ×${n}`).join(", ")), 1600);
  refreshCurrent();
}
async function poll() {
  try {
    const st = await api("GET", `/api/status?since=${logSince}${current ? `&sid=${current.id}` : ""}`);
    const log = $("#log");
    if (st.logs.length) {
      if (logSince === 0) log.textContent = "";
      const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
      st.logs.forEach(l => { log.textContent += l.t + "\n"; logSince = l.n; });
      if (atBottom) log.scrollTop = log.scrollHeight;
    }
    const pill = $("#statePill"); pill.textContent = st.state; pill.className = `state ${st.state}`;
    $("#currentLine").textContent = st.current ? `Abhi: ${st.current.label}` : (st.queued_jobs ? `${st.queued_jobs} job queue mein` : "");
    renderAgents(st.agents);
    const agentBusy = current && (st.agents || []).some(a => a.job && a.job.series_id === current.id);
    const busy = st.state !== "idle" || agentBusy;
    $("#genPendingBtn").disabled = false;
    const stKey = st.state + "|" + (agentBusy ? "a" : "");
    // series sirf tab dobara mangao jab sach mein kuch badla ho
    if (current && st.sig && st.sig !== lastSig) { lastSig = st.sig; await refreshCurrent(); }
    if (lastState !== stKey && !busy) loadSeriesList();
    lastState = stKey;
  } catch (e) { /* server restart */ }
  setTimeout(poll, document.hidden ? 6000 : 2000);
}

// ---------- .txt drop ----------
function setupDrop() {
  const dz = $("#dropZone");
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", async e => {
    if (!current) return;
    const files = [...e.dataTransfer.files].filter(f => /\.(txt|md)$/i.test(f.name))
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    if (!files.length) return toast("Sirf .txt ya .md files chalengi");
    let added = 0;
    for (const f of files) {
      const text = await f.text();
      if (/^\s*===\s*$/m.test(text)) { await addBulk(text, !current.items.some(i => i.kind === "series")); continue; }
      const label = f.name.replace(/\.(txt|md)$/i, "").replace(/[_-]+/g, " ");
      const kind = /series|master/i.test(f.name) && !current.items.some(i => i.kind === "series") ? "series" : "episode";
      await api("POST", `/api/series/${current.id}/items`, { kind, label, prompt: text.trim() }); added++;
    }
    await refreshCurrent(); renderItems(true); loadSeriesList();
    if (added) toast(`${added} file import hui`);
  });
}

// ---------- posters ----------
function updatePickCount() {
  const all = $$("#posterPicks input"), on = all.filter(c => c.checked).length;
  $("#pickCount").textContent = `${on} of ${all.length} selected`;
  $("#pickToggle").textContent = on === all.length ? "Select none" : "Select all";
}
async function openPosters() {
  const done = current.items.filter(i => i.image_path);
  if (!done.length) return toast("Pehle thumbnails generate karo");
  const st = await api("GET", "/api/settings");
  $("#posterSize").value = st.poster_size || "1000x1500";
  $("#posterPicks").innerHTML = done.map(i => `<label class="pick on"><input type="checkbox" checked value="${i.id}"><img src="${thumbUrl(i, 256)}" loading="lazy" alt=""><div class="cap">${esc(i.label)}</div></label>`).join("");
  $$("#posterPicks input").forEach(cb => cb.onchange = () => { cb.parentElement.classList.toggle("on", cb.checked); updatePickCount(); });
  updatePickCount();
  openModal("#postersModal");
}
async function openPostersFolder() {
  const r = await api("POST", `/api/series/${current.id}/open-posters`);
  toast(r.ok ? "Posters folder khul gaya" : `Folder: ${r.folder}`);
}

// ---------- settings ----------
const SETTING_KEYS = ["cdp_url", "image_prefix", "master_wait", "master_suffix", "image_timeout", "gap_seconds", "retries", "openai_api_key", "api_model", "api_size", "api_quality", "series_format", "episode_format", "webp_quality", "poster_site_url", "poster_headless", "public_url"];
async function openSettings() {
  const s = await api("GET", "/api/settings");
  SETTING_KEYS.forEach(k => { const el = $(`#s_${k}`); if (el) el.value = s[k] ?? ""; });
  openModal("#settingsModal");
}
// ---------- Gambit: workspaces ----------
let workspaces = [], ws = null, wsMeta = {};
async function loadWorkspaces() {
  const r = await api("GET", "/api/workspaces");
  workspaces = r.workspaces; wsMeta = { ratios: r.ratios, layouts: r.layouts, layout_cols: r.layout_cols };
  let want = ws ? ws.id : null;
  if (!want) { try { want = +localStorage.getItem("gambit_ws"); } catch (e) {} }
  setWorkspace((workspaces.find(w => w.id === want) || workspaces[0] || {}).id, true);
}
function setWorkspace(id, quiet) {
  ws = workspaces.find(w => w.id === id) || workspaces[0] || null;
  if (!ws) return;
  try { localStorage.setItem("gambit_ws", ws.id); } catch (e) {}
  $("#wsName").textContent = ws.name;
  $("#wsDot").style.background = ws.color || "var(--marigold)";
  $("#projLabel").textContent = ws.project_label || "Projects";
  $("#newSeriesBtn").title = `Naya ${ws.project_label || "project"}`;
  $("#wsMenu").innerHTML = workspaces.map(w => `<button class="ws-opt ${w.id === ws.id ? "on" : ""}" data-ws="${w.id}" role="option"><span class="ws-dot" style="background:${esc(w.color || "#F7A928")}"></span>${esc(w.name)}<small>${w.series_count}</small></button>`).join("")
    + (me && me.role === "admin" ? `<button class="ws-opt ws-new" data-wsnew="1">+ Naya workspace</button>` : "");
  $$("#wsMenu [data-ws]").forEach(b => b.onclick = async () => { toggleWsMenu(false); if (+b.dataset.ws === ws.id) return; setWorkspace(+b.dataset.ws); await loadSeriesList(); goDashboard(); });
  const nb = $("#wsMenu [data-wsnew]"); if (nb) nb.onclick = () => { toggleWsMenu(false); newWorkspace(); };
  document.documentElement.style.setProperty("--ws", ws.color || "#F7A928");
}
function toggleWsMenu(on) { const m = $("#wsMenu"); on = on ?? m.classList.contains("hidden"); m.classList.toggle("hidden", !on); $("#wsBtn").setAttribute("aria-expanded", on); }
async function newWorkspace() {
  const name = prompt("Naye workspace ka naam (jaise: Postly Instagram):"); if (!name) return;
  const w = await api("POST", "/api/workspaces", { name });
  await loadWorkspaces(); setWorkspace(w.id); await loadSeriesList(); goDashboard(); openWsSettings();
}
const ratioCss = r => (r || "1:1").replace(":", " / ");
function renderProjMeta() {
  if (!current) return;
  const t = current.template, isK = ws && ws.kind === "kahanifm";
  $("#projMeta").innerHTML = `<span class="chip"><span class="ws-dot" style="background:${esc(ws ? ws.color : "")}"></span>${esc(ws ? ws.name : "")}</span>`
    + (t ? `<span class="chip">${esc(t.name)}</span>` : "")
    + `<label class="chip chip-sel" title="Image ka size">Size <select id="projRatio">${(wsMeta.ratios || []).map(x => `<option ${x === (current.ratio || "1:1") ? "selected" : ""}>${x}</option>`).join("")}</select></label>`;
  $("#projRatio").onchange = async e => { await api("PUT", `/api/series/${current.id}`, { ratio: e.target.value }); current.ratio = e.target.value; renderProjMeta(); toast("Size badla — nayi images isi size mein (master mein CANVAS line bhi badal lo)"); };
  $("#builderBtn").classList.toggle("hidden", !(t && t.layout && t.layout !== "free"));
  $("#posterPanel").classList.toggle("hidden", !isK);
  $("#addSeriesItemBtn").classList.toggle("hidden", !isK);
  $("#itemsTitle").textContent = isK ? "Thumbnails" : "Posts";
  $("#items").style.setProperty("--ar", ratioCss(current.ratio));
}
function renderRefs() {
  if (!current) return;
  const refs = current.refs || [];
  $("#refCount").textContent = refs.length || "";
  $("#refList").innerHTML = refs.map(r => `<figure class="ref"><img src="${r.url}?w=160" alt="" loading="lazy"><figcaption>${r.from === "project" ? `<button class="link" data-rdel="${esc(r.name)}">hatao</button>` : "template"}</figcaption></figure>`).join("")
    || `<p class="empty-note">Koi reference nahi. Approved posts ki 2–4 images daalo — ChatGPT unke style ko follow karega.</p>`;
  $$("#refList [data-rdel]").forEach(b => b.onclick = async () => { const s = await api("DELETE", `/api/series/${current.id}/refs/${encodeURIComponent(b.dataset.rdel)}`); current.refs = s.refs; renderRefs(); toast("Reference hata di — agli baar nayi chat"); });
}
$("#refFiles").onchange = async e => {
  if (!e.target.files.length || !current) return;
  const fd = new FormData(); [...e.target.files].forEach(f => fd.append("files", f, f.name));
  const s = await api("POST", `/api/series/${current.id}/refs`, fd); current.refs = s.refs; renderRefs(); e.target.value = "";
  toast("Reference jud gayi — agli Generate nayi chat mein inke saath");
};

// ---------- post builder ----------
const COL_HELP = { word: "word", hindi: "hindi", sentence: "sentence", visual: "visual (optional)", english: "english" };
function openBuilder() {
  const t = current && current.template; if (!t) return;
  const cols = wsMeta.layout_cols[t.layout] || [];
  $("#bTitle").textContent = `Post builder · ${t.name}`;
  $("#bHint").innerHTML = `Columns: <code>${cols.map(c => COL_HELP[c] || c).join("  |  ")}</code> — har row ek ${t.layout === "grid4" || t.layout === "phrase4" ? "card (4 rows = 1 post)" : t.layout === "compare2" ? "object (2 rows = 1 post)" : "post"}. Zyada rows → posts khud ban jaayenge.`;
  $("#bTitleRow").classList.toggle("hidden", t.layout !== "grid4");
  if (!$("#bTable").value.trim()) $("#bTable").placeholder = cols.join("\t") + "\n" + ({ grid4: "Kind\tदयालु\tShe is a *kind* person.\tgirl gently pets a puppy", phrase4: "मुझे यह पसंद आया।\tI liked it.\tANAYA eating pizza, thumbs up", word: "Accomplish\tपूरा करना\tHe *accomplished* his goal.\tboy crossing a finish ribbon", compare2: "थाली\tPlatter\t" }[t.layout] || "");
  openModal("#builderModal"); builderPreview();
}
const builderPreview = debounce(async () => {
  if (!current || !$("#bTable").value.trim()) { $("#bPreview").textContent = "Table daalo — yahan brief dikhega."; $("#bCount").textContent = "Preview"; return; }
  const r = await api("POST", `/api/series/${current.id}/build`, { table: $("#bTable").value, title: $("#bHeading").value, subtitle: $("#bSub").value, preview: true });
  if (!r.ok) { $("#bPreview").textContent = r.msg; $("#bCount").textContent = "Preview"; return; }
  $("#bCount").textContent = `${r.rows} rows → ${r.posts.length} post${r.posts.length > 1 ? "s" : ""}`;
  $("#bPreview").textContent = r.posts.map(p => `■ ${p.label}\n${p.brief}`).join("\n\n");
}, 450);
["#bTable", "#bHeading", "#bSub"].forEach(id => $(id).addEventListener("input", builderPreview));
$("#builderBtn").onclick = openBuilder;
$("#bCreate").onclick = async () => {
  const r = await api("POST", `/api/series/${current.id}/build`, { table: $("#bTable").value, title: $("#bHeading").value, subtitle: $("#bSub").value, replace: $("#bReplace").checked });
  if (!r.ok) return toast(r.msg);
  closeModals(); current.items = r.series.items; renderItems(true); loadSeriesList();
  toast(`${r.created} post${r.created > 1 ? "s" : ""} ban gaye — ab Generate`);
};

// ---------- workspace settings ----------
const WS_FIELDS = ["name", "project_label", "default_ratio", "color", "fit_mode", "safe_bottom_pct", "logo_width_pct", "base_prompt"];
let wsEdit = null, tplSel = null;
function openWsSettings(tab) {
  wsEdit = JSON.parse(JSON.stringify(ws));
  $("#wsTitle").textContent = `Workspace · ${ws.name}`;
  $("#wsF_default_ratio").innerHTML = (wsMeta.ratios || []).map(x => `<option>${x}</option>`).join("");
  WS_FIELDS.forEach(k => { const el = $(`#wsF_${k}`); if (el) el.value = wsEdit[k] ?? ""; });
  $("#wsF_logo_on").checked = !!wsEdit.logo_on;
  renderWsLogo(); renderWsChars(); tplSel = (wsEdit.templates[0] || {}).id; renderTpls();
  wsTab(tab || "general"); $("#wsSaved").textContent = "";
  openModal("#wsModal");
}
function wsTab(name) {
  $$("[data-wstab]").forEach(b => b.classList.toggle("on", b.dataset.wstab === name));
  $$(".ws-pane").forEach(p => p.classList.toggle("hidden", p.dataset.pane !== name));
}
$$("[data-wstab]").forEach(b => b.onclick = () => wsTab(b.dataset.wstab));
function renderWsLogo() {
  $("#wsLogoPrev").innerHTML = wsEdit.logo_url ? `<img src="${wsEdit.logo_url}" alt="logo">` : "Logo nahi";
}
function renderWsChars() {
  const cs = wsEdit.characters || [];
  $("#wsChars").innerHTML = cs.map((c, i) => `<div class="char" data-i="${i}"><div class="char-top"><input class="char-name" value="${esc(c.name || "")}" placeholder="NAAM"><input class="char-role" value="${esc(c.role || "")}" placeholder="role"><button class="btn btn-icon btn-danger-ghost" data-del aria-label="Hatao">${icon("trash")}</button></div><textarea class="char-look" rows="2" placeholder="Fixed look">${esc(c.look || "")}</textarea></div>`).join("") || `<p class="empty-note">Koi character nahi.</p>`;
  $$("#wsChars .char").forEach(el => { const c = cs[+el.dataset.i];
    el.querySelector(".char-name").oninput = e => c.name = e.target.value; el.querySelector(".char-role").oninput = e => c.role = e.target.value;
    el.querySelector(".char-look").oninput = e => c.look = e.target.value; el.querySelector("[data-del]").onclick = () => { cs.splice(+el.dataset.i, 1); renderWsChars(); }; });
}
$("#wsCharAdd").onclick = () => { (wsEdit.characters = wsEdit.characters || []).push({ name: "", role: "", look: "" }); renderWsChars(); };
function renderTpls() {
  const ts = wsEdit.templates;
  $("#tplList").innerHTML = ts.map(t => `<button class="tpl-item ${t.id === tplSel ? "on" : ""}" data-t="${t.id}"><b>${esc(t.name)}</b><small>${esc((wsMeta.layouts || {})[t.layout] || t.layout)} · ${esc(t.ratio || "")}${t.refs.length ? ` · ${t.refs.length} ref` : ""}</small></button>`).join("")
    + `<button class="tpl-item tpl-add" id="tplAdd">+ Naya template</button>`;
  $$("#tplList [data-t]").forEach(b => b.onclick = () => { tplSel = +b.dataset.t; renderTpls(); });
  $("#tplAdd").onclick = async () => { const name = prompt("Template ka naam:"); if (!name) return; const w = await api("POST", `/api/workspaces/${ws.id}/templates`, { name }); wsEdit.templates = w.templates; tplSel = w.templates[w.templates.length - 1].id; renderTpls(); syncWs(w); };
  const t = ts.find(x => x.id === tplSel);
  $("#tplEdit").innerHTML = t ? `
    <div class="ws-cols">
      <label class="field">Naam<input id="tF_name" value="${esc(t.name)}"></label>
      <label class="field">Size<select id="tF_ratio">${(wsMeta.ratios || []).map(x => `<option ${x === t.ratio ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label class="field">Builder layout<select id="tF_layout">${Object.entries(wsMeta.layouts || {}).map(([k, v]) => `<option value="${k}" ${k === t.layout ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
    </div>
    <label class="field">Format prompt (brand rules ke baad master mein judta hai)<textarea id="tF_prompt" class="master" rows="11" spellcheck="false">${esc(t.prompt || "")}</textarea></label>
    <div class="panel-head" style="margin-top:6px"><h2 style="font-size:15px">Reference images <span class="count">${t.refs.length}</span></h2>
      <label class="btn btn-ghost btn-sm"><svg class="ic"><use href="#i-upload"/></svg>Add<input type="file" id="tF_refs" accept="image/*" multiple hidden></label></div>
    <div class="ref-list">${t.refs.map(r => `<figure class="ref"><img src="${r.url}?w=160" alt=""><figcaption><button class="link" data-trdel="${esc(r.name)}">hatao</button></figcaption></figure>`).join("") || `<p class="empty-note">Approved posts ki 2–4 images — har naye project ki chat mein jaayengi.</p>`}</div>
    <div class="tpl-actions"><button class="btn btn-quiet btn-sm" id="tplDel">Template delete</button><button class="btn btn-accent btn-sm" id="tplSave">Template save</button></div>` : "";
  if (!t) return;
  $("#tplSave").onclick = async () => { const w = await api("PUT", `/api/templates/${t.id}`, { name: $("#tF_name").value, ratio: $("#tF_ratio").value, layout: $("#tF_layout").value, prompt: $("#tF_prompt").value }); wsEdit.templates = w.templates; renderTpls(); syncWs(w); toast("Template save — naye projects mein lagega"); };
  $("#tplDel").onclick = async () => { if (!await confirmBox(`"${t.name}" template hata dein? Purane projects pe asar nahi.`, { title: "Template delete", ok: "Delete", danger: true })) return; const w = await api("DELETE", `/api/templates/${t.id}`); wsEdit.templates = w.templates; tplSel = (w.templates[0] || {}).id; renderTpls(); syncWs(w); };
  $("#tF_refs").onchange = async e => { const fd = new FormData(); [...e.target.files].forEach(f => fd.append("files", f, f.name)); const w = await api("POST", `/api/templates/${t.id}/refs`, fd); wsEdit.templates = w.templates; renderTpls(); syncWs(w); };
  $$("#tplEdit [data-trdel]").forEach(b => b.onclick = async () => { const w = await api("DELETE", `/api/templates/${t.id}/refs/${encodeURIComponent(b.dataset.trdel)}`); wsEdit.templates = w.templates; renderTpls(); syncWs(w); });
}
function syncWs(w) { const i = workspaces.findIndex(x => x.id === w.id); if (i >= 0) workspaces[i] = w; if (ws && ws.id === w.id) { setWorkspace(w.id, true); } }
$("#wsLogoFile").onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  const fd = new FormData(); fd.append("file", f, f.name);
  const r = await api("POST", `/api/workspaces/${ws.id}/logo`, fd); if (!r.ok) return toast(r.msg);
  wsEdit.logo_url = r.logo_url; wsEdit.logo_on = 1; $("#wsF_logo_on").checked = true; renderWsLogo(); syncWs(r); toast("Logo lag gaya");
};
$("#wsSave").onclick = async () => {
  const body = {}; WS_FIELDS.forEach(k => body[k] = $(`#wsF_${k}`).value);
  body.logo_on = $("#wsF_logo_on").checked ? 1 : 0; body.characters = (wsEdit.characters || []).filter(c => c.name || c.look);
  const w = await api("PUT", `/api/workspaces/${ws.id}`, body); syncWs(w); wsEdit = Object.assign(JSON.parse(JSON.stringify(w)), { templates: wsEdit.templates });
  $("#wsTitle").textContent = `Workspace · ${w.name}`; $("#wsSaved").textContent = "Saved ✓ (naye projects pe lagega)"; loadSeriesList();
};
$("#wsNewBtn").onclick = () => { closeModals(); newWorkspace(); };
$("#wsDelBtn").onclick = async () => {
  if (!await confirmBox(`"${ws.name}" workspace delete karein?`, { title: "Workspace delete", ok: "Delete", danger: true })) return;
  const r = await api("DELETE", `/api/workspaces/${ws.id}`); if (!r.ok) return toast(r.msg);
  closeModals(); ws = null; await loadWorkspaces(); await loadSeriesList(); goDashboard();
};
$("#wsSettingsBtn").onclick = () => openWsSettings();
$("#wsBtn").onclick = e => { e.stopPropagation(); toggleWsMenu(); };
document.addEventListener("click", e => { if (!e.target.closest("#wsSwitch")) toggleWsMenu(false); });

// ---------- v3: views + dashboard ----------
let dashDays = 7, dashTimer = null, dashData = null;
function setNav(which) {
  $$(".nav-item").forEach(b => b.classList.remove("active"));
  if (which === "dash") $("#dashBtn").classList.add("active");
}
function showView(which) {
  $("#empty").classList.toggle("hidden", which !== "dash");
  $("#seriesView").classList.toggle("hidden", which !== "series");
  setNav(which);
  clearInterval(dashTimer);
  if (which === "dash") dashTimer = setInterval(() => { if (!document.hidden) loadDashboard(true); }, 20000);
}
async function goDashboard() {
  current = null; renderSeriesList(); showView("dash");
  try { localStorage.removeItem("kfm_lastSeries"); } catch (e) {}
  await loadDashboard();
}
const fmtSec = s => s == null ? "—" : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
const fmtAgo = ts => { if (!ts) return "—"; const d = (Date.now() / 1000 - ts); if (d < 60) return "abhi"; if (d < 3600) return `${Math.round(d / 60)} min pehle`; if (d < 86400) return `${Math.round(d / 3600)} ghante pehle`; return `${Math.round(d / 86400)} din pehle`; };
const nf = n => n == null ? "—" : Number(n).toLocaleString("en-IN");
function kpiTile(label, icon, val, sub, unit = "") {
  return `<div class="kpi"><div class="kpi-top"><span>${label}</span><svg class="ic"><use href="#${icon}"/></svg></div>
    <div class="kpi-val">${val}${unit ? `<small>${unit}</small>` : ""}</div><div class="kpi-sub">${sub}</div></div>`;
}
function tipShow(e, html) { const t = $("#dashTip"); t.innerHTML = html; t.classList.add("on"); const x = Math.min(e.clientX + 14, innerWidth - t.offsetWidth - 10); t.style.left = x + "px"; t.style.top = (e.clientY - t.offsetHeight - 12) + "px"; }
function tipHide() { $("#dashTip").classList.remove("on"); }
function barChart(el, rows, { series, labelOf, tipOf, compact = false }) {
  const W = el.clientWidth || 600, H = el.clientHeight || 200, padL = 30, padB = 22, padT = 8;
  const max = Math.max(1, ...rows.map(r => series.reduce((a, s) => a + (r[s.key] || 0), 0)));
  const nice = max <= 5 ? 5 : Math.ceil(max / 5) * 5, iw = W - padL - 4, ih = H - padB - padT;
  const band = iw / rows.length, bw = Math.min(24, Math.max(4, band * .62));
  const y = v => padT + ih - (v / nice) * ih;
  let g = `<g class="grid">`; for (let k = 0; k <= 4; k++) { const v = nice * k / 4; g += `<line x1="${padL}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/>`; } g += `</g>`;
  let ax = `<g class="axis">`; for (let k = 0; k <= 4; k += 2) { const v = nice * k / 4; ax += `<text x="${padL - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`; }
  const every = Math.ceil(rows.length / (compact ? 8 : 10));
  rows.forEach((r, i) => { if (i % every === 0 || i === rows.length - 1) ax += `<text x="${padL + band * i + band / 2}" y="${H - 5}" text-anchor="middle">${labelOf(r)}</text>`; });
  ax += `</g>`;
  let bars = "";
  rows.forEach((r, i) => {
    let base = 0; const x = padL + band * i + (band - bw) / 2;
    const segs = series.filter(s => r[s.key] > 0);
    segs.forEach((s, k) => {
      const v = r[s.key], y1 = y(base + v), y0 = y(base), top = k === segs.length - 1;
      const h = Math.max(0, y0 - y1 - (k > 0 ? 2 : 0));
      bars += top ? `<path d="M${x},${y0 - (k > 0 ? 2 : 0)} V${y1 + 4} Q${x},${y1} ${x + 4},${y1} H${x + bw - 4} Q${x + bw},${y1} ${x + bw},${y1 + 4} V${y0 - (k > 0 ? 2 : 0)} Z" fill="${s.color}"/>`
                  : `<rect x="${x}" y="${y1}" width="${bw}" height="${h}" fill="${s.color}"/>`;
      base += v;
    });
    bars += `<rect class="hit" data-i="${i}" x="${padL + band * i}" y="${padT}" width="${band}" height="${ih}"/>`;
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="bar chart">${g}${ax}<line x1="${padL}" x2="${W}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>${bars}</svg>`;
  el.querySelectorAll(".hit").forEach(h => { h.onmousemove = e => tipShow(e, tipOf(rows[+h.dataset.i])); h.onmouseleave = tipHide; });
}
function buildInsights(d) {
  const k = d.kpi, out = [];
  if (!k.timed_thumbs && k.thumbs_done) out.push(["", "Time ka data v3 se record hona shuru hua hai — agle kuch thumbnails ke baad average time dikhega."]);
  const vv = d.variants || {};
  if (vv.regen_rate != null && k.thumbs_done >= 10 && vv.regen_rate >= 30) out.push(["", `${vv.regen_rate}% thumbnails dobara banane pade — master prompt / briefs pe kaam karo.`]);
  if (k.success_rate != null && k.success_rate < 85) out.push(["", `Success rate ${k.success_rate}% hai. Sabse bada reason: <b>${esc((d.failures[0] || {}).reason || "—")}</b> — briefs ke refusal fixes dekho.`]);
  if (k.avg_sec_week && k.avg_sec && k.avg_sec_week > k.avg_sec * 1.25) out.push(["", `Is hafte ek thumbnail ${fmtSec(k.avg_sec_week)} le raha hai (normal ${fmtSec(k.avg_sec)}) — ChatGPT slow hai ya retries zyada.`]);
  if (k.thumbs_pending) out.push(["", `${k.thumbs_pending} thumbnails abhi pending hain.`]);
  return out.slice(0, 3).map(([c, t]) => `<div class="insight ${c}"><svg class="ic"><use href="#i-spark"/></svg><span>${t}</span></div>`).join("");
}
async function loadDashboard(quiet) {
  let d; try { d = await api("GET", `/api/dashboard?days=${dashDays}${ws ? "&workspace=" + ws.id : ""}`); } catch (e) { return; }
  dashData = d; const k = d.kpi;
  $("#dashHello").textContent = `Namaste${me ? ", " + me.name : ""} · ${new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" })}`;
  const pct = k.thumbs_done + k.thumbs_failed + k.thumbs_pending ? Math.round(100 * k.thumbs_done / (k.thumbs_done + k.thumbs_failed + k.thumbs_pending)) : 0;
  $("#kpis").innerHTML = [
    kpiTile("Series", "i-disc", nf(k.series), `<b>${k.series_complete}</b> poori ho gayi`),
    kpiTile("Episodes", "i-paste", nf(k.episodes), `${k.series ? (k.episodes / k.series).toFixed(1) : 0} per series`),
    kpiTile("Thumbnails bane", "i-image", nf(k.thumbs_done), `aaj <b>${k.today}</b> · 7 din <b>${k.week}</b>`),
    kpiTile("Avg time", "i-clock", fmtSec(k.avg_sec), k.median_sec ? `per thumbnail · median <b>${fmtSec(k.median_sec)}</b>` : "per thumbnail (v3 se record)"),
    kpiTile("Success rate", "i-play", k.success_rate == null ? "—" : k.success_rate, k.first_try_rate == null ? `${pct}% items done` : `pehli try mein <b>${k.first_try_rate}%</b>`, k.success_rate == null ? "" : "%"),
    kpiTile("App posters", "i-download", nf(k.posters), d.poster_avg_sec ? `~${fmtSec(d.poster_avg_sec)} per poster` : `${k.thumbs_done ? Math.round(100 * k.posters / k.thumbs_done) : 0}% thumbnails ke`),
  ].join("");
  $("#insights").innerHTML = buildInsights(d);
  const days = d.daily.slice(-dashDays);
  barChart($("#dailyChart"), days, {
    series: [{ key: "ok", color: "var(--good)" }, { key: "failed", color: "var(--bad)" }],
    labelOf: r => r.date.slice(8) + "/" + r.date.slice(5, 7),
    tipOf: r => `<div class="t-h">${new Date(r.date).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })}</div>
      <div class="t-r"><span><i style="background:var(--good)"></i>Bane</span><b>${r.ok}</b></div>
      <div class="t-r"><span><i style="background:var(--bad)"></i>Fail</span><b>${r.failed}</b></div>
      <div class="t-r"><span>Avg time</span><b>${fmtSec(r.avg_sec)}</b></div>`,
  });
  $("#dailyTable").innerHTML = `<table class="dtable"><thead><tr><th>Din</th><th class="num">Bane</th><th class="num">Fail</th><th class="num">Avg time</th></tr></thead><tbody>${days.map(r => `<tr><td>${r.date}</td><td class="num">${r.ok}</td><td class="num">${r.failed}</td><td class="num">${fmtSec(r.avg_sec)}</td></tr>`).join("")}</tbody></table>`;
  const q = d.queue || {}, running = q.state && !["idle", "stopped"].includes(q.state);
  $("#liveBox").innerHTML = `
    <div class="live-row"><span>Hub</span><b class="pill ${running ? "run" : "idle"}">${running ? "● " + esc(q.state) : "idle"}</b></div>
    ${running && q.current ? `<div class="live-row"><span>Abhi</span><b>${esc(q.current.label || "")}</b></div>` : ""}
    <div class="live-row"><span>Agents online</span><b>${d.agents_online.length ? d.agents_online.map(esc).join(", ") : "koi nahi"}</b></div>
    <div class="live-row"><span>Pending thumbnails</span><b>${k.thumbs_pending}</b></div>
    <div class="live-row"><span>Generate mein laga time</span><b>${k.hours_generating} ghante</b></div>
`;
  $("#seriesTable").innerHTML = d.series.length ? `<thead><tr><th>Series</th><th class="num">Episodes</th><th>Progress</th><th class="num">Fail</th><th class="num">Posters</th><th class="num">Avg time</th><th>Last activity</th></tr></thead><tbody>${d.series.map(r => {
      const t = r.total || 1, dn = Math.round(100 * r.done / t), fl = Math.round(100 * r.failed / t);
      return `<tr data-id="${r.id}"><td class="nm" title="${esc(r.name)}">${esc(r.name)}</td><td class="num">${r.episodes}</td>
        <td><div class="prog"><div class="prog-bar"><i style="width:${dn}%;background:var(--good)"></i><i style="width:${fl}%;background:var(--bad)"></i></div><small>${r.done}/${r.total}</small></div></td>
        <td class="num">${r.failed || "—"}</td><td class="num">${r.posters || "—"}</td><td class="num">${fmtSec(r.avg_sec)}</td><td>${fmtAgo(r.last_activity)}</td></tr>`; }).join("")}</tbody>`
    : `<tbody><tr><td class="empty-note">Abhi koi series nahi — upar <b>New series</b> dabao.</td></tr></tbody>`;
  $$("#seriesTable tbody tr[data-id]").forEach(tr => tr.onclick = () => openSeries(+tr.dataset.id));
  const maxP = Math.max(1, ...d.people.map(p => p.ok));
  $("#peopleBox").innerHTML = d.people.length ? `<div class="rank">${d.people.map(p => `<div class="rank-row"><span><b>${esc(p.who)}</b>${p.online ? ' <small style="color:var(--jade)">● online</small>' : ""}</span><span>${p.ok} <small>· ${fmtSec(p.avg_sec)}${p.failed ? ` · ${p.failed} fail` : ""}</small></span><div class="bar"><i style="width:${100 * p.ok / maxP}%"></i></div></div>`).join("")}</div>`
    : `<p class="empty-note">Thumbnails bante hi yahan dikhega kisne kitne banaye.</p>`;
  const vv = d.variants || {};
  $("#geminiBox").innerHTML = `<div class="mini-kpis">
      <div class="mini"><b>${nf(vv.regens || 0)}</b><span>regenerate hue</span></div>
      <div class="mini"><b>${vv.regen_rate == null ? "—" : vv.regen_rate + "%"}</b><span>thumbnails dobara bane</span></div>
      <div class="mini"><b>${nf(vv.series_with_variants || 0)}</b><span>series mein A/B/C variants</span></div>
      <div class="mini"><b>${nf(vv.series_with_characters || 0)}</b><span>series mein character sheet</span></div></div>
    ${vv.use && vv.use.length ? `<p class="hint">Variant use: ${vv.use.map(v => `${esc(v.variant)} ×${v.count}`).join(", ")}</p>` : `<p class="empty-note">Regenerate karoge to yahan dikhega kaun sa variant kitna chala.</p>`}`;
  const maxF = Math.max(1, ...d.failures.map(f => f.count));
  $("#failBox").innerHTML = d.failures.length ? `<div class="rank">${d.failures.map(f => `<div class="rank-row"><span>${esc(f.reason)}</span><span>${f.count}</span><div class="bar bad"><i style="width:${100 * f.count / maxF}%"></i></div></div>`).join("")}</div>`
    : `<p class="empty-note">Koi fail nahi 🎉</p>`;
  barChart($("#hoursChart"), d.hours, {
    series: [{ key: "count", color: "var(--marigold)" }], compact: true,
    labelOf: r => r.hour % 6 === 0 ? `${r.hour}:00` : "",
    tipOf: r => `<div class="t-h">${r.hour}:00 – ${r.hour + 1}:00</div><div class="t-r"><span>Thumbnails</span><b>${r.count}</b></div>`,
  });
  const kindTxt = { thumb: "Thumbnail", poster: "App posters" };
  $("#feedBox").innerHTML = d.feed.length ? d.feed.map(f => `<div class="feed-row"><svg class="ic ${f.ok ? "ok" : "no"}"><use href="#${f.ok ? "i-play" : "i-x"}"/></svg>
      <span><b>${kindTxt[f.kind] || f.kind}</b> · ${esc(f.series)}${f.label ? " · " + esc(f.label) : ""}${f.who ? ` <small>· ${esc(f.who)}</small>` : ""}${!f.ok && f.error ? ` <small style="color:var(--ember)">· ${esc(f.error)}</small>` : ""}</span>
      <small>${fmtSec(f.seconds)} · ${fmtAgo(f.at)}</small></div>`).join("") : `<p class="empty-note">Abhi koi activity nahi.</p>`;
  $("#onboard").classList.toggle("hidden", k.series > 0);
}

// ---------- wiring ----------
$$("[data-close]").forEach(b => b.onclick = closeModals);
$$(".modal").forEach(m => m.addEventListener("mousedown", e => { if (e.target === m) closeModals(); }));
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModals(); });

const startNew = () => {
  $("#newSeriesName").value = "";
  const tpls = (ws && ws.templates) || [];
  $("#newTemplate").innerHTML = tpls.map(t => `<option value="${t.id}">${esc(t.name)}${t.ratio ? " · " + t.ratio : ""}</option>`).join("") || `<option value="">— koi template nahi —</option>`;
  const fillRatio = () => {
    const t = tpls.find(x => String(x.id) === $("#newTemplate").value);
    const r = (t && t.ratio) || (ws && ws.default_ratio) || "1:1";
    $("#newRatio").innerHTML = (wsMeta.ratios || []).map(x => `<option ${x === r ? "selected" : ""}>${x}</option>`).join("");
    $("#newHint").innerHTML = t ? `Master prompt = <b>${esc(ws.name)}</b> ke brand rules + <b>${esc(t.name)}</b> format + size${(ws.characters || []).length ? " + characters" : ""}${(t.refs || []).length ? ` · ${t.refs.length} reference image(s) bhi jaayengi` : ""}.` : "";
  };
  $("#newTemplate").onchange = fillRatio; fillRatio();
  $("#nsTitle").textContent = `Naya ${(ws && ws.project_label) || "project"} · ${ws ? ws.name : ""}`;
  openModal("#newSeriesModal"); setTimeout(() => $("#newSeriesName").focus(), 50);
};
$("#newSeriesBtn").onclick = startNew;
$("#emptyNewBtn").onclick = startNew;
const createSeries = async () => {
  const name = $("#newSeriesName").value.trim();
  if (!name) return $("#newSeriesName").focus();
  closeModals();
  const s = await api("POST", "/api/series", { name, workspace_id: ws && ws.id, template_id: +$("#newTemplate").value || 0, ratio: $("#newRatio").value });
  await loadSeriesList(); openSeries(s.id);
  toast(s.template && s.template.layout !== "free" ? "Ban gaya — ab Post builder se posts banao" : "Ban gaya — master prompt check karo, phir briefs daalo");
};
$("#newSeriesCreate").onclick = createSeries;
$("#newSeriesName").addEventListener("keydown", e => { if (e.key === "Enter") createSeries(); });

$("#seriesSearch").oninput = renderSeriesList;
$("#seriesName").oninput = e => saveSeries({ name: e.target.value });
$("#masterPrompt").oninput = e => { const v = (current.variants || [])[varSel]; if (!v) return saveSeries({ master_prompt: e.target.value }); v.prompt = e.target.value; saveVariants(); };
$("#rotateChk").onchange = () => { try { localStorage.setItem("kfm_rotate", $("#rotateChk").checked ? "1" : "0"); } catch (e) {} if (current) renderItems(true); };
try { if (localStorage.getItem("kfm_rotate") === "0") $("#rotateChk").checked = false; } catch (e) {}
$("#charAddBtn").onclick = () => { current.characters = current.characters || []; current.characters.push({ name: "", role: "", look: "" }); renderChars(); $$("#charList .char-name").pop().focus(); };
$$(".seg-btn[data-engine]").forEach(b => b.onclick = () => { current.engine = b.dataset.engine; renderEngine(); saveSeries({ engine: b.dataset.engine }); });

$("#deleteSeriesBtn").onclick = async () => {
  if (!await confirmBox(`"${current.name}" aur uske saare briefs hata dein? Images outputs folder mein rahengi.`, { title: "Delete series", ok: "Delete series", danger: true })) return;
  await api("DELETE", `/api/series/${current.id}`);
  await loadSeriesList(); goDashboard();
};
$("#folderBtn").onclick = async () => { const r = await api("POST", `/api/series/${current.id}/open-folder`); toast(r.ok ? "Folder khul gaya" : `Folder: ${r.folder}`); };
$("#downloadBtn").onclick = () => openModal("#downloadModal");
$$("#downloadModal [data-dl]").forEach(a => a.onclick = () => { closeModals(); downloadZip(a.dataset.dl); });
$("#finalZipBtn").onclick = () => downloadZip("final");
$("#runOnSel").onchange = e => { current.run_on = e.target.value; saveSeries({ run_on: e.target.value }); };
$("#teamBtn").onclick = async () => { await Promise.all([loadTeam(), loadLink()]); openModal("#teamModal"); };
$("#copyLinkBtn").onclick = () => linkInfo && copyText(linkInfo.url, "Team link copy ho gaya — teammates ko bhej do");
$("#copyPsBtn").onclick = () => linkInfo && copyText(linkInfo.ps, "Command copy — PowerShell mein paste karke Enter");
$("#copyMacBtn").onclick = () => linkInfo && copyText(linkInfo.mac, "Command copy — Terminal mein paste karke Enter");
$("#addUserBtn").onclick = async () => {
  const r = await api("POST", "/api/team", { name: $("#newUserName").value.trim(), password: $("#newUserPass").value });
  if (!r.ok) return toast(r.msg);
  toast("Teammate add ho gaya — unhe naam, password aur hub link bhej do");
  $("#newUserName").value = ""; $("#newUserPass").value = ""; loadTeam();
};
$("#pwSave").onclick = async () => {
  const r = await api("POST", "/api/me/password", { old: $("#pwOld").value, new: $("#pwNew").value });
  toast(r.ok ? "Password badal gaya" : r.msg); if (r.ok) { $("#pwOld").value = ""; $("#pwNew").value = ""; }
};
$("#convertBtn").onclick = async () => {
  const r = await api("POST", `/api/series/${current.id}/convert-formats`);
  toast(r.changed ? `${r.changed} image ka format badla` : "Sab images pehle se sahi format mein hain");
  refreshCurrent();
};

$("#addSeriesItemBtn").onclick = () => addItem("series");
$("#addEpisodeBtn").onclick = () => addItem("episode");
$("#bulkBtn").onclick = () => { $("#bulkText").value = ""; $("#bulkFirstSeries").checked = !current.items.some(i => i.kind === "series"); openModal("#bulkModal"); };
$("#bulkSave").onclick = async () => { const t = $("#bulkText").value; if (!t.trim()) return; closeModals(); await addBulk(t, $("#bulkFirstSeries").checked); };

$("#genPendingBtn").onclick = () => generate({ mode: "pending" });
$("#genAllBtn").onclick = async () => {
  if (await confirmBox("Saare thumbnails dobara banenge aur purani files overwrite hongi.", { title: "Regenerate all", ok: "Regenerate all" })) generate({ mode: "all" });
};
$("#stopBtn").onclick = async () => { await api("POST", "/api/stop", { series_id: current && current.id }); toast("Stop — current image ke baad rukega"); };

$("#postersBtn").onclick = openPosters;
$("#openPostersBtn").onclick = openPostersFolder;
$("#openPostersBtn2").onclick = openPostersFolder;
$("#finalBtn").onclick = async () => {
  const r = await api("POST", `/api/series/${current.id}/final`, { open: true });
  toast(r.count ? `Final folder: ${r.count} WebP file ready` : "Pehle app posters banao — final folder abhi khaali hai");
};
$("#pickToggle").onclick = () => {
  const all = $$("#posterPicks input"), target = !all.every(c => c.checked);
  all.forEach(c => { c.checked = target; c.parentElement.classList.toggle("on", target); });
  updatePickCount();
};
$("#postersGo").onclick = async () => {
  const ids = $$("#posterPicks input:checked").map(c => +c.value);
  if (!ids.length) return toast("Kam se kam ek image chuno");
  closeModals();
  const r = await api("POST", `/api/series/${current.id}/posters`, { item_ids: ids, poster_size: $("#posterSize").value });
  toast(r.ok ? `${r.queued} image poster site pe ja rahi hain` : r.msg);
};

$("#settingsBtn").onclick = openSettings;
$("#settingsSave").onclick = async () => {
  const body = {}; SETTING_KEYS.forEach(k => { const el = $(`#s_${k}`); if (el) body[k] = el.value; });
  await api("PUT", "/api/settings", body); closeModals(); toast("Settings save ho gayi");
};

setupDrop();
loadTeam();
loadLink();
$("#dashBtn").onclick = goDashboard;
$$(".range-btn").forEach(b => b.onclick = () => { dashDays = +b.dataset.days; $$(".range-btn").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); }); loadDashboard(); });
addEventListener("resize", debounce(() => { if (dashData && !$("#empty").classList.contains("hidden")) loadDashboard(true); }, 250));
loadWorkspaces().then(loadSeriesList).then(() => { showView("dash"); loadDashboard(); });
poll();
