/* SlopStudy SPA — no build step, hash routing. */
"use strict";

const state = {
  user: null,
  topics: [],
  topic: null,
  stats: null,
  leaderboard: [],
  study: null, // {sessionId, topicTitle, cards, idx, feedback, summary, results}
  newFiles: [],
  authMode: "login",
  pollTimer: null,
};

/* ---------------- utils ---------------- */

const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function lang() {
  return state.user?.language || localStorage.getItem("fd_lang") ||
    (navigator.language || "en").slice(0, 2);
}

function t(key, a, b) {
  const dict = I18N[lang()] || I18N.en;
  let s = dict[key] ?? I18N.en[key] ?? key;
  if (a !== undefined) s = s.replace("{a}", a);
  if (b !== undefined) s = s.replace("{b}", b);
  return s;
}

function applyTheme() {
  const theme = state.user?.theme || localStorage.getItem("fd_theme") || "dark";
  document.documentElement.dataset.theme = theme;
}

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function apiError(e) {
  const code = e?.detail || e?.message || String(e);
  const known = { invalid_credentials: 1, email_taken: 1, wrong_password: 1,
    not_enough_points: 1, topic_not_ready: 1, joker_used: 1,
    invite_required: 1, invite_invalid: 1, rate_limited: 1, reset_invalid: 1,
    account_disabled: 1, cannot_disable_self: 1, reeval_pending: 1 };
  if (code === 429) { toast(t("err_rate_limited"), "error"); return; }
  toast(known[code] ? t("err_" + code) : t("err_generic", code), "error");
}

async function api(path, opts = {}) {
  if (opts.json !== undefined) {
    opts.body = JSON.stringify(opts.json);
    opts.headers = { "Content-Type": "application/json" };
    opts.method = opts.method || "POST";
  }
  const resp = await fetch("/api" + path, { credentials: "same-origin", ...opts });
  if (resp.status === 401) {
    state.user = null;
    go("auth");
    throw { detail: "not_authenticated" };
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw typeof data.detail === "string" ? data : { detail: resp.status };
  return data;
}

function go(route) { location.hash = "#/" + route; }

function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleDateString(lang() === "de" ? "de-DE" : "en-US",
    { day: "numeric", month: "short" });
}

/* ---------------- shell ---------------- */

function navLink(route, key, ico) {
  const current = (location.hash.slice(2) || "dashboard").split("/")[0];
  const active = current === route ? "active" : "";
  return `<a class="${active}" href="#/${route}"><span class="ico">${ico}</span> ${t(key)}</a>`;
}

function shell(content) {
  const u = state.user;
  return `
  <div class="shell">
    <header class="topbar">
      <div class="logo" onclick="location.hash='#/dashboard'">🎴 SlopStudy</div>
      <nav>
        ${navLink("dashboard", "nav_dashboard", "🏠")}
        ${navLink("new", "nav_new", "✨")}
        ${navLink("catalogue", "nav_catalogue", "📚")}
        ${navLink("leaderboard", "nav_leaderboard", "🏆")}
        ${u.is_admin ? navLink("admin", "nav_admin", "🛡️") : ""}
        ${navLink("settings", "nav_settings", "⚙️")}
      </nav>
      <div class="statpills">
        <span class="pill" title="${t("points")}"><span class="ico">💎</span> <span id="points-pill">${u.points}</span></span>
        <span class="pill" title="${t("level")}"><span class="ico">⭐</span> ${t("level")} ${u.level.level}</span>
        ${u.streak ? `<span class="pill" title="${t("streak_days")}"><span class="ico">🔥</span> ${u.streak}</span>` : ""}
      </div>
    </header>
    <main>${content}</main>
    <nav class="bottomnav">
      ${navLink("dashboard", "nav_dashboard", "🏠")}
      ${navLink("catalogue", "nav_catalogue_short", "📚")}
      ${navLink("new", "nav_new_short", "✨")}
      ${u.is_admin ? navLink("admin", "nav_admin", "🛡️") : navLink("leaderboard", "nav_leaderboard_short", "🏆")}
      ${navLink("settings", "nav_settings_short", "⚙️")}
    </nav>
  </div>`;
}

function setPointsPill(points) {
  state.user.points = points;
  const el = $("#points-pill");
  if (el) el.textContent = points;
}

/* ---------------- auth view ---------------- */

async function renderAuth() {
  const isLogin = state.authMode === "login";
  if (state.authConfig === undefined) {
    state.authConfig = await api("/auth-config").catch(() => ({ require_invite: false }));
  }
  const needInvite = !isLogin && state.authConfig.require_invite;
  $("#app").innerHTML = `
  <div class="auth-wrap">
    <div class="auth-hero">
      <div class="logo">🎴 SlopStudy</div>
      <p class="dim">${t("tagline")}</p>
    </div>
    <div class="card">
      <h2>${isLogin ? t("login") : t("register")}</h2>
      <form id="auth-form">
        ${isLogin ? "" : `
        <label class="field"><span>${t("name")}</span>
          <input type="text" name="name" required maxlength="80"></label>
        <label class="field"><span>${t("language")}</span>
          <select name="language">
            <option value="en" ${lang() === "en" ? "selected" : ""}>English</option>
            <option value="de" ${lang() === "de" ? "selected" : ""}>Deutsch</option>
          </select></label>`}
        <label class="field"><span>${t("email")}</span>
          <input type="email" name="email" required autocomplete="email"></label>
        <label class="field"><span>${t("password")}</span>
          <input type="password" name="password" required minlength="8"
            autocomplete="${isLogin ? "current-password" : "new-password"}">
          ${isLogin ? "" : `<small class="dim">${t("password_hint")}</small>`}</label>
        ${needInvite ? `<label class="field"><span>${t("invite_code")}</span>
          <input type="text" name="invite" required maxlength="64" autocomplete="off">
          <small class="dim">${t("invite_hint")}</small></label>` : ""}
        <button class="btn primary block" type="submit">${isLogin ? t("login") : t("register")}</button>
      </form>
      <p style="text-align:center;margin-bottom:0">
        <a href="#" id="auth-toggle">${isLogin ? t("no_account") : t("have_account")}</a>
        ${isLogin ? `<br><a href="#/forgot" class="small dim">${t("forgot_link")}</a>` : ""}
      </p>
    </div>
  </div>`;

  $("#auth-toggle").onclick = (e) => {
    e.preventDefault();
    state.authMode = isLogin ? "register" : "login";
    renderAuth();
  };
  $("#auth-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    try {
      await api(isLogin ? "/login" : "/register", { json: body });
      if (body.language) localStorage.setItem("fd_lang", body.language);
      await loadUser();
      go("dashboard");
    } catch (err) { apiError(err); }
  };
}

/* ---------------- invite landing ---------------- */

async function renderInvite(code) {
  let info;
  try {
    info = await api("/invite/" + encodeURIComponent(code || ""));
  } catch {
    // Invalid / used / revoked invite — fall back to the normal login screen.
    state.authMode = "login";
    go("auth");
    renderAuth();
    toast(t("err_invite_invalid"), "error");
    return;
  }
  $("#app").innerHTML = `
  <div class="auth-wrap">
    <div class="auth-hero">
      <div class="logo">🎴 SlopStudy</div>
      <p class="dim">${t("invite_welcome")}</p>
    </div>
    <div class="card">
      <h2>${t("invite_create_account")}</h2>
      <form id="invite-reg">
        <label class="field"><span>${t("email")}</span>
          <input type="email" value="${esc(info.email)}" readonly
            style="opacity:.7;cursor:not-allowed"></label>
        <label class="field"><span>${t("name")}</span>
          <input type="text" name="name" required maxlength="80" autofocus></label>
        <label class="field"><span>${t("language")}</span>
          <select name="language">
            <option value="en" ${lang() === "en" ? "selected" : ""}>English</option>
            <option value="de" ${lang() === "de" ? "selected" : ""}>Deutsch</option>
          </select></label>
        <label class="field"><span>${t("password")}</span>
          <input type="password" name="password" required minlength="8" autocomplete="new-password">
          <small class="dim">${t("password_hint")}</small></label>
        <button class="btn primary block" type="submit">${t("invite_create_account")}</button>
      </form>
    </div>
  </div>`;
  $("#invite-reg").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("/register", { json: {
        email: info.email, name: fd.get("name"), password: fd.get("password"),
        language: fd.get("language"), invite: code,
      }});
      localStorage.setItem("fd_lang", fd.get("language"));
      await loadUser();
      go("dashboard");
    } catch (err) { apiError(err); }
  };
}

/* ---------------- password reset ---------------- */

async function renderForgot() {
  if (state.authConfig === undefined) {
    state.authConfig = await api("/auth-config").catch(() => ({ smtp_enabled: false }));
  }
  const smtpOn = state.authConfig.smtp_enabled;
  $("#app").innerHTML = `
  <div class="auth-wrap">
    <div class="auth-hero"><div class="logo">🎴 SlopStudy</div></div>
    <div class="card">
      <h2>${t("forgot_title")}</h2>
      ${smtpOn ? `
      <p class="small dim">${t("forgot_hint")}</p>
      <form id="forgot-form">
        <label class="field"><span>${t("email")}</span>
          <input type="email" name="email" required autocomplete="email"></label>
        <button class="btn primary block" type="submit">${t("forgot_send")}</button>
      </form>` : `<p class="small dim">${t("forgot_smtp_off")}</p>`}
      <p style="text-align:center;margin-bottom:0"><a href="#/auth">${t("back_to_login")}</a></p>
    </div>
  </div>`;
  const form = $("#forgot-form");
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/forgot", { json: { email: e.target.email.value.trim() } });
      toast(t("forgot_sent"), "success");
      go("auth");
    } catch (err) { apiError(err); }
  };
}

async function renderReset(token) {
  try {
    await api("/reset/" + encodeURIComponent(token || ""));
  } catch {
    toast(t("err_reset_invalid"), "error");
    go("auth");
    renderAuth();
    return;
  }
  $("#app").innerHTML = `
  <div class="auth-wrap">
    <div class="auth-hero"><div class="logo">🎴 SlopStudy</div></div>
    <div class="card">
      <h2>${t("reset_title")}</h2>
      <form id="reset-form">
        <label class="field"><span>${t("password_new")}</span>
          <input type="password" name="password" required minlength="8" autocomplete="new-password" autofocus>
          <small class="dim">${t("password_hint")}</small></label>
        <button class="btn primary block" type="submit">${t("reset_submit")}</button>
      </form>
    </div>
  </div>`;
  $("#reset-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/reset", { json: { token, password: e.target.password.value } });
      toast(t("reset_done"), "success");
      state.authMode = "login";
      go("auth");
      renderAuth();
    } catch (err) { apiError(err); }
  };
}

/* ---------------- dashboard ---------------- */

function progressLabel(topic) {
  const msg = topic.progress_msg || "";
  if (msg.startsWith("generating_unit:")) {
    const [a, b] = msg.split(":")[1].split("/");
    return t("prog_generating_unit", a, b);
  }
  if (msg === "planning") return t("prog_planning");
  if (msg === "extracting_sources") return t("prog_extracting_sources");
  return t("status_processing");
}

function topicCardHtml(topic) {
  const badge = `<span class="badge ${topic.status}">${t("status_" + topic.status)}</span>`;
  const mode = `<span class="badge mode">${t("mode_" + topic.mode)}</span>`
    + (topic.shared ? ` <span class="badge queued">👥${topic.owner_name ? " " + esc(topic.owner_name) : ""}</span>` : "")
    + (topic.visibility === "private" && !topic.shared ? ` <span class="badge queued">🔒</span>` : "");
  let body = "";
  if (topic.status === "processing" || topic.status === "queued") {
    body = `
      <div class="progressbar"><div style="width:${topic.progress_pct}%"></div></div>
      <div class="small dim">${topic.status === "queued" ? t("status_queued") : progressLabel(topic)}
        · ${state.user.smtp_enabled && state.user.email_notifications ? t("email_notice") : t("email_notice_off")}</div>`;
  } else if (topic.status === "failed") {
    body = `<div class="small" style="color:var(--bad)">${esc(topic.error)}</div>
      <div class="row">
        <button class="btn sm" onclick="FD.retryTopic(${topic.id})">${t("retry")}</button>
        <button class="btn sm danger" onclick="FD.deleteTopic(${topic.id})">${t("delete")}</button>
      </div>`;
  } else {
    body = `
      <div class="small dim">${topic.card_count} ${t("cards")} · ${topic.units} ${t("units")}
        ${topic.due_cards ? ` · <b style="color:var(--accent)">${topic.due_cards} ${t("due_now")}</b>` : ""}</div>
      <div class="row">
        <button class="btn sm primary" onclick="FD.quickStart(${topic.id})">▶ ${t("study_now")}</button>
        <a class="btn sm ghost" href="#/topic/${topic.id}">${t("view_topic")}</a>
      </div>`;
  }
  return `
  <div class="card topic-card">
    <div class="row spread">${mode}${badge}</div>
    <h3><a href="#/topic/${topic.id}" style="color:inherit">${esc(topic.title)}</a></h3>
    ${body}
  </div>`;
}

function statsCardHtml() {
  const s = state.stats;
  if (!s || !s.totals.sessions) return "";
  const accuracy = s.answers.seen ? Math.round(100 * s.answers.correct / s.answers.seen) : 0;
  const max = Math.max(1, ...s.week.map((d) => d.points));
  const days = s.week.map((d) =>
    `<div class="bar" style="height:${Math.max(4, Math.round(86 * d.points / max))}px" title="${d.points} ${t("points")}">
       <span>${esc(d.day.slice(5))}</span></div>`).join("");
  return `
  <div class="card">
    <div class="row spread">
      <h2 style="margin:0">${t("week_activity")}</h2>
      <div class="row">
        <span class="pill">📚 ${s.totals.sessions} ${t("total_sessions")}</span>
        <span class="pill">🎯 ${accuracy}% ${t("accuracy")}</span>
        ${s.streak ? `<span class="pill">🔥 ${s.streak} ${t("streak_days")}</span>` : ""}
      </div>
    </div>
    <div class="bars" style="margin-bottom:22px">${days || ""}</div>
  </div>`;
}

async function renderDashboard() {
  [state.topics, state.stats] = await Promise.all([api("/topics"), api("/stats")]);
  const topics = state.topics;
  let content;
  if (!topics.length) {
    content = `<div class="card empty">
      <div class="big">🎴</div>
      <p>${t("no_topics")}</p>
      <a class="btn primary" href="#/new">✨ ${t("create_first")}</a>
    </div>`;
  } else {
    content = statsCardHtml() +
      `<h1>${t("your_topics")}</h1><div class="grid">${topics.map(topicCardHtml).join("")}</div>`;
  }
  $("#app").innerHTML = shell(content);
  schedulePoll();
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  const busy = state.topics.some((t2) => t2.status === "queued" || t2.status === "processing");
  const route = location.hash.slice(2).split("/")[0] || "dashboard";
  if (busy && route === "dashboard") {
    state.pollTimer = setTimeout(() => renderDashboard().catch(() => {}), 4000);
  }
}

/* ---------------- new topic ---------------- */

const MODES = ["multiple_choice", "exact", "yes_no", "exam"];

function renderNew() {
  state.newFiles = [];
  const modeOpts = MODES.map((m, i) => `
    <div class="opt ${i === 0 ? "active" : ""}" data-mode="${m}" onclick="FD.pickMode(this)">
      <b>${t("mode_" + m)}</b><small>${t("mode_" + m + "_desc")}</small>
    </div>`).join("");
  $("#app").innerHTML = shell(`
  <h1>✨ ${t("new_topic")}</h1>
  <form id="new-form" class="card">
    <label class="field"><span>${t("topic_prompt_label")}</span>
      <textarea name="prompt" required minlength="3" maxlength="4000"
        placeholder="${esc(t("topic_prompt_ph"))}"></textarea></label>

    <label class="field"><span>${t("mode_label")}</span></label>
    <div class="seg" id="mode-seg">${modeOpts}</div>

    <div class="row" style="margin-top:14px">
      <label class="field" style="flex:1;min-width:140px"><span>${t("card_count_label")}</span>
        <select name="card_count">
          <option>20</option><option selected>40</option><option>60</option><option>80</option><option>100</option>
        </select></label>
      <label class="field" style="flex:1;min-width:140px"><span>${t("card_lang_label")}</span>
        <select name="language">
          <option value="en" ${lang() === "en" ? "selected" : ""}>English</option>
          <option value="de" ${lang() === "de" ? "selected" : ""}>Deutsch</option>
        </select></label>
    </div>

    <label class="field"><span>${t("visibility_label")}</span>
      <select name="visibility" onchange="document.getElementById('vis-hint').textContent = this.value === 'private' ? FD._t('visibility_private_hint') : FD._t('visibility_public_hint')">
        <option value="public">${t("visibility_public")}</option>
        <option value="private">${t("visibility_private")}</option>
      </select>
      <small class="dim" id="vis-hint">${t("visibility_public_hint")}</small></label>

    <label class="field"><span>${t("sources_label")}</span></label>
    <div class="dropzone" id="dropzone">📄 ${t("upload_hint")}</div>
    <input type="file" id="file-input" multiple hidden accept=".pdf,.docx,.txt,.md,.csv">
    <div id="file-chips"></div>
    <label class="field" style="margin-top:14px"><span>${t("urls_label")}</span>
      <textarea name="urls" rows="2" placeholder="https://…"></textarea></label>

    <button class="btn primary block" type="submit" id="create-btn">🚀 ${t("create_topic")}</button>
    <p class="small dim" style="text-align:center;margin-bottom:0">
      ${state.user.smtp_enabled && state.user.email_notifications ? t("email_notice") : t("email_notice_off")}</p>
  </form>`);

  const dz = $("#dropzone"), fi = $("#file-input");
  dz.onclick = () => fi.click();
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("drag"); };
  dz.ondragleave = () => dz.classList.remove("drag");
  dz.ondrop = (e) => {
    e.preventDefault(); dz.classList.remove("drag");
    addFiles(e.dataTransfer.files);
  };
  fi.onchange = () => { addFiles(fi.files); fi.value = ""; };

  $("#new-form").onsubmit = async (e) => {
    e.preventDefault();
    const btn = $("#create-btn");
    btn.disabled = true;
    btn.textContent = t("creating");
    const fd = new FormData(e.target);
    fd.set("mode", $("#mode-seg .opt.active").dataset.mode);
    for (const f of state.newFiles) fd.append("files", f);
    try {
      const res = await api("/topics", { method: "POST", body: fd });
      toast("✨ " + t("status_queued"), "success");
      go("topic/" + res.topic_id);
    } catch (err) {
      apiError(err);
      btn.disabled = false;
      btn.textContent = "🚀 " + t("create_topic");
    }
  };
}

function addFiles(list) {
  for (const f of list) {
    if (state.newFiles.length >= 10) break;
    state.newFiles.push(f);
  }
  renderFileChips();
}

function renderFileChips() {
  $("#file-chips").innerHTML = state.newFiles.map((f, i) =>
    `<span class="filechip">📄 ${esc(f.name)}
       <button type="button" onclick="FD.removeFile(${i})">✕</button></span>`).join("");
}

/* ---------------- topic detail ---------------- */

async function renderTopic(id) {
  const topic = await api("/topics/" + id);
  if (topic.status === "ready" || topic.status === "stopped") {
    [topic.revisions, topic.cards, topic.members] = await Promise.all([
      topic.is_owner ? api(`/topics/${id}/revisions`).catch(() => []) : Promise.resolve([]),
      api(`/topics/${id}/cards`).catch(() => []),
      topic.is_owner ? api(`/topics/${id}/members`).catch(() => []) : Promise.resolve(null),
    ]);
  }
  state.topic = topic;
  let planHtml = "";
  if (topic.plan) {
    const units = topic.plan.units.map((u, i) => `
      <div class="unit">
        <button type="button" onclick="this.parentNode.querySelector('.unit-body').hidden ^= 1">
          <span>${i + 1}. ${esc(u.title)}</span><span>▾</span></button>
        <div class="unit-body" hidden>
          ${u.objectives?.length ? `<h3>${t("objectives")}</h3><ul>${u.objectives.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
          ${u.key_concepts?.length ? `<h3>${t("key_concepts")}</h3><ul>${u.key_concepts.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
          ${u.pitfalls?.length ? `<h3>${t("pitfalls")}</h3><ul>${u.pitfalls.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
        </div>
      </div>`).join("");
    planHtml = `<div class="card">
      <h2>📋 ${t("plan")}</h2>
      <p class="dim">${esc(topic.plan.overview || "")}</p>${units}</div>`;
  }

  let actionHtml = "";
  if (topic.status === "ready") {
    actionHtml = `<div class="card">
      <div class="row spread">
        <div>
          <div class="small dim">${topic.card_count} ${t("cards")} · ${topic.units} ${t("units")}
            ${topic.due_cards ? ` · <b style="color:var(--accent)">${topic.due_cards} ${t("due_now")}</b>` : ""}</div>
          <div class="small dim">${t("topic_stats", topic.stats.sessions, topic.stats.points)}</div>
        </div>
        <div class="row" style="align-items:flex-end">
          <label class="field" style="margin:0"><span class="small">${t("session_size")}</span>
            <select id="sess-size" style="width:auto;min-width:84px"><option>5</option><option selected>10</option><option>15</option><option>20</option></select>
          </label>
          <button class="btn primary" onclick="FD.startSession(${topic.id})">▶ ${t("start_session")}</button>
        </div>
      </div>
      ${topic.is_owner ? `
      <label class="switch" style="margin-top:14px" title="${esc(t("nightly_refresh_hint"))}">
        <input type="checkbox" ${topic.nightly_refresh ? "checked" : ""}
          onchange="FD.toggleRefresh(${topic.id}, this.checked)">
        <span class="track"></span> 🌙 ${t("nightly_refresh")}
      </label>
      <p class="small dim" style="margin:6px 0 0">${t("nightly_refresh_hint")}</p>
      <label class="switch" style="margin-top:12px">
        <input type="checkbox" ${topic.visibility === "public" ? "checked" : ""}
          onchange="FD.toggleVisibility(${topic.id}, this.checked)">
        <span class="track"></span> 🌍 ${t("visibility_public")}
      </label>
      <p class="small dim" style="margin:6px 0 0">${topic.visibility === "public" ? t("visibility_public_hint") : t("visibility_private_hint")}</p>` : ""}
    </div>`;
  } else if (topic.status === "failed") {
    actionHtml = `<div class="card">
      <h2 style="color:var(--bad)">${t("generation_failed")}</h2>
      <p class="small">${esc(topic.error)}</p>
      <div class="row">
        <button class="btn" onclick="FD.retryTopic(${topic.id})">${t("retry")}</button>
        <button class="btn danger" onclick="FD.deleteTopic(${topic.id})">${t("delete")}</button>
      </div></div>`;
  } else {
    actionHtml = `<div class="card">
      <div class="progressbar"><div style="width:${topic.progress_pct}%"></div></div>
      <p class="small dim" style="margin-bottom:0">${topic.status === "queued" ? t("status_queued") : progressLabel(topic)}</p>
    </div>`;
    setTimeout(() => {
      if (location.hash === "#/topic/" + id) renderTopic(id).catch(() => {});
    }, 4000);
  }

  let materialHtml = "";
  if (topic.status === "ready") {
    const mat = (topic.material || []).filter((m) => m.text);
    const expected = topic.plan ? topic.plan.units.length : 0;
    const items = mat.map((m) => `
      <div class="unit">
        <button type="button" onclick="this.parentNode.querySelector('.unit-body').hidden ^= 1">
          <span>📖 ${esc(m.title)}</span><span>▾</span></button>
        <div class="unit-body" hidden>
          ${m.text.split(/\n\n+/).map((p) => `<p>${esc(p)}</p>`).join("")}
          ${(m.sources || []).length ? `<p class="small srcs"><b>🔗 ${t("web_sources")}:</b> ${
            m.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(" · ")
          }</p>` : ""}
        </div>
      </div>`).join("");
    materialHtml = `<div class="card">
      <h2>📖 ${t("learning_material")}</h2>
      <div class="hintbox">🧠 ${t("pretest_hint")}</div>
      ${items}
      ${mat.length < expected ? `<p class="small dim" style="margin-bottom:0">⏳ ${t("material_pending")}</p>` : ""}
    </div>`;
    // Refresh quietly while background enrichment is still producing material,
    // but never once notes exist (a re-render would collapse what you're reading).
    if (!mat.length && expected) {
      setTimeout(() => {
        if (location.hash === "#/topic/" + topic.id) renderTopic(topic.id).catch(() => {});
      }, 8000);
    }
  }

  const pm = topic.progress_msg || "";
  const enriching = topic.status === "ready" && pm.startsWith("enriching")
    ? `<p class="small dim">🔎 ${t("enriching_note")}</p>`
    : topic.status === "ready" && pm.startsWith("translating")
    ? `<p class="small dim">🌐 ${t("translating_note")}</p>` : "";

  // Live AI progress for this deck (deep explanations + translations).
  let aiHtml = "";
  if (topic.status === "ready" && topic.ai && topic.ai.total > 0) {
    const ai = topic.ai;
    const allDone = ai.enriched >= ai.total && ai.translated >= ai.total && ai.content_translated;
    const bar = (label, done, total) => `
      <div class="row spread" style="margin-top:8px">
        <span class="small">${label}</span><span class="small dim">${done}/${total}</span>
      </div>
      <div class="progressbar"><div style="width:${Math.round(100 * done / total)}%"></div></div>`;
    aiHtml = `<div class="card">
      <h2>🤖 ${t("ai_status")}</h2>
      ${allDone ? `<p class="small dim" style="margin-bottom:0">✅ ${t("ai_complete")}</p>` : `
        ${bar("📚 " + t("ai_explanations"), ai.enriched, ai.total)}
        ${bar("🌐 " + t("ai_translations"), ai.translated, ai.total)}
        ${bar("📋 " + t("ai_content"), ai.content_done, ai.content_total)}
        ${pm.startsWith("enriching") || pm.startsWith("translating")
          ? `<p class="small dim" style="margin:10px 0 0">⚙️ ${pm.startsWith("translating") ? t("translating_note") : t("enriching_note")}</p>` : ""}`}
    </div>`;
  }

  // Sharing (owner/admin only): invite existing users to study this deck.
  let membersHtml = "";
  if (topic.is_owner && topic.members !== null && topic.members !== undefined) {
    const rows = topic.members.map((m) => `
      <div class="row spread" style="border-top:1px solid var(--border);padding:8px 0">
        <span class="small"><b>${esc(m.name)}</b> <span class="dim">${esc(m.email)}</span></span>
        <button class="btn sm ghost" onclick="FD.removeMember(${topic.id}, ${m.id})">${t("remove")}</button>
      </div>`).join("");
    membersHtml = `<div class="card">
      <h2>👥 ${t("shared_with")}</h2>
      <p class="small dim">${t("shared_hint")}</p>
      <input type="text" id="member-search" placeholder="${esc(t("share_search_ph"))}"
        autocomplete="off" oninput="FD.searchUsers(${topic.id}, this.value)">
      <div id="member-results"></div>
      ${rows || `<p class="small dim" style="margin:10px 0 0">${t("no_members")}</p>`}
    </div>`;
  }

  let reviseHtml = "";
  if ((topic.status === "ready" || topic.status === "stopped") && topic.is_owner) {
    const revs = topic.revisions || [];
    const modeOptions = MODES.map((m) =>
      `<option value="${m}" ${topic.mode === m ? "selected" : ""}>${t("mode_" + m)}</option>`).join("");
    reviseHtml = `<div class="card">
      <h2>✏️ ${t("revise_title")}</h2>
      <label class="field" style="max-width:340px"><span>${t("mode_change_label")}</span>
        <select onchange="FD.changeMode(${topic.id}, this.value)">${modeOptions}</select></label>
      <p class="small dim" style="margin-top:-6px">${t("mode_change_hint")}</p>
      <p class="small dim">${t("revise_hint")}</p>
      <form id="revise-form" data-topic="${topic.id}">
        <textarea name="instruction" rows="2" required minlength="3" maxlength="1000"
          placeholder="${esc(t("revise_ph"))}"></textarea>
        <button class="btn primary" type="submit" style="margin-top:10px">✨ ${t("revise_submit")}</button>
      </form>
      ${revs.length ? `<h3 style="margin-top:16px">${t("revise_history")}</h3>
        ${revs.map((r) => `<div class="row spread" style="border-top:1px solid var(--border);padding:8px 0">
          <span class="small">${esc(r.instruction)}</span>
          <span class="badge ${r.status === "done" ? "ready" : r.status === "failed" ? "failed" : "processing"}"
            title="${esc(r.result_msg || "")}">${t("rev_status_" + r.status)}</span>
        </div>`).join("")}` : ""}
    </div>`;
  }

  let cardsHtml = "";
  if ((topic.cards || []).length) {
    const rows = topic.cards.map((c) => `
      <div class="row spread cardrow" data-q="${esc(c.question.toLowerCase())}"
           style="border-top:1px solid var(--border);padding:8px 0;gap:8px">
        <span class="small" style="flex:1">
          <span class="badge diff">U${c.unit_index + 1} · ${"●".repeat(c.difficulty)}</span>
          ${esc(c.question)}
        </span>
        ${topic.is_owner ? `<button class="btn sm danger" onclick="FD.deleteCard(${c.id}, ${topic.id})">✕</button>` : ""}
      </div>`).join("");
    cardsHtml = `<div class="card">
      <div class="unit" style="margin-bottom:0">
        <button type="button" onclick="this.parentNode.querySelector('.unit-body').hidden ^= 1">
          <span>🗂️ ${t("all_cards")} (${topic.cards.length})</span><span>▾</span></button>
        <div class="unit-body" hidden>
          <input type="text" placeholder="${esc(t("filter_cards"))}" style="margin-bottom:6px"
            oninput="FD.filterCards(this.value)">
          <div id="card-list">${rows}</div>
        </div>
      </div>
    </div>`;
  }

  const sources = topic.sources.length
    ? `<div class="card"><h2>🔗 ${t("sources")}</h2>
        ${topic.sources.map((s) => `<span class="filechip">${s.kind === "url" ? "🌐" : "📄"} ${esc(s.name)}</span>`).join("")}</div>`
    : "";

  // The page re-renders while background work is running — remember which
  // accordions the user opened so a refresh doesn't collapse what they're reading.
  const openStates = [...document.querySelectorAll("main .unit-body")].map((b) => !b.hidden);

  const dangerHtml = topic.status === "ready" && topic.is_owner
    ? `<div class="card row spread">
        <span class="dim small">${esc(topic.title)}</span>
        <button class="btn sm danger" onclick="FD.deleteTopic(${topic.id})">🗑 ${t("delete")}</button>
      </div>` : "";

  // Creator identity is admin-only: owner_name is only present for admins.
  const sharedBadge = !topic.is_owner
    ? (topic.owner_name
        ? ` <span class="badge queued">👥 ${t("shared_by", esc(topic.owner_name))}</span>`
        : ` <span class="badge queued">👥</span>`)
    : "";
  const privBadge = topic.is_owner && topic.visibility === "private"
    ? ` <span class="badge queued">🔒 ${t("private_badge")}</span>` : "";

  $("#app").innerHTML = shell(`
    <h1>${esc(topic.title)} <span class="badge mode">${t("mode_" + topic.mode)}</span>${privBadge}${sharedBadge}</h1>
    ${enriching}${actionHtml}${aiHtml}${materialHtml}${planHtml}${cardsHtml}${reviseHtml}${membersHtml}${sources}${dangerHtml}`);

  const bodies = document.querySelectorAll("main .unit-body");
  if (bodies.length === openStates.length) {
    openStates.forEach((open, i) => { if (open) bodies[i].hidden = false; });
  }

  const revForm = $("#revise-form");
  if (revForm) {
    revForm.onsubmit = async (e) => {
      e.preventDefault();
      const instruction = e.target.instruction.value.trim();
      try {
        await api(`/topics/${id}/revise`, { json: { instruction } });
        toast(t("revise_queued"), "success");
        renderTopic(id).catch(() => {});
      } catch (err) { apiError(err); }
    };
  }
  // Refresh while a revision is being applied or background enrichment/translation runs.
  const revBusy = (topic.revisions || []).some((r) => r.status === "queued" || r.status === "processing");
  if (revBusy || pm.startsWith("enriching") || pm.startsWith("translating")) {
    setTimeout(() => {
      if (location.hash === "#/topic/" + id) renderTopic(id).catch(() => {});
    }, 6000);
  }
}

/* ---------------- study session ---------------- */

async function startSessionFor(topicId, size) {
  try {
    const data = await api("/sessions/start", { json: { topic_id: topicId, size } });
    state.study = {
      sessionId: data.session_id, topicTitle: data.topic_title,
      topicId, size,
      cards: data.cards, idx: 0, feedback: null, summary: null,
      fifty: {}, optionsShown: false,
    };
    setPointsPill(data.points);
    // Render directly: "Study again" restarts from the summary, which is already
    // at #/study, so setting the same hash would fire no hashchange.
    if (location.hash !== "#/study") location.hash = "#/study";
    renderStudy();
  } catch (err) { apiError(err); }
}

function diffDots(d) {
  return `<span class="diffdots" title="${t("difficulty")} ${d}/5">` +
    [1, 2, 3, 4, 5].map((i) => `<i class="${i <= d ? "on" : ""}"></i>`).join("") + "</span>";
}

function renderStudy() {
  const st = state.study;
  if (!st) { go("dashboard"); return; }
  if (st.summary) { renderSummary(); return; }
  const card = st.cards[st.idx];
  const fb = st.feedback;
  const canSkip = state.user.points >= card.skip_cost;

  let answerArea = "";
  if (!fb) {
    if (card.type === "multiple_choice") {
      if (!st.optionsShown) {
        // Active recall: force a retrieval attempt before recognition kicks in.
        answerArea = `
          <p class="dim small" style="margin:14px 0 10px">🧠 ${t("recall_first")}</p>
          <button class="btn primary" onclick="FD.showOptions()">${t("show_options")}</button>`;
      } else {
        const removed = (st.fifty && st.fifty[card.id]) || [];
        answerArea = `<div class="choice-grid">` + card.choices.map((c) => {
          if (removed.includes(c)) {
            return `<button class="choice removed" disabled>${esc(c)}</button>`;
          }
          return `<button class="choice" onclick="FD.answer(this.dataset.v)" data-v="${esc(c)}">${esc(c)}</button>`;
        }).join("") + `</div>`;
      }
    } else if (card.type === "yes_no") {
      answerArea = `<div class="choice-grid" style="grid-template-columns:1fr 1fr">
        <button class="choice" style="text-align:center" onclick="FD.answer('yes')">👍 ${t("yes")}</button>
        <button class="choice" style="text-align:center" onclick="FD.answer('no')">👎 ${t("no")}</button>
      </div>`;
    } else if (card.type === "exact") {
      answerArea = `<form onsubmit="event.preventDefault();FD.answer(this.a.value)">
        <div class="row" style="margin:14px 0">
          <input type="text" name="a" autofocus autocomplete="off" placeholder="${esc(t("your_answer_ph"))}" style="flex:1">
          <button class="btn primary" type="submit">${t("check")}</button>
        </div></form>`;
    } else { // open / self-graded
      answerArea = st.revealed
        ? `<div class="feedback" style="border:1.5px solid var(--border)">
             <b>${t("correct_answer")}:</b> ${esc(card.answer || "")}
             ${card.explanation ? `<div class="small dim" style="margin-top:4px">${esc(card.explanation)}</div>` : ""}
           </div>
           <p style="font-weight:700;margin-bottom:8px">${t("self_grade_q")}</p>
           <div class="row">
             <button class="btn ok" onclick="FD.selfGrade(true)">✓ ${t("i_was_right")}</button>
             <button class="btn danger" onclick="FD.selfGrade(false)">✗ ${t("i_was_wrong")}</button>
           </div>`
        : `<button class="btn primary" style="margin-top:12px" onclick="FD.reveal()">${t("show_answer")}</button>`;
    }
  }

  let feedbackArea = "";
  if (fb) {
    const last = st.idx === st.cards.length - 1;
    feedbackArea = `
      <div class="feedback ${fb.correct ? "ok" : "bad"}">
        <div class="head">${fb.skipped ? "⏭ " + t("skipped") : fb.correct ? "🎉 " + t("correct") : "❌ " + t("wrong")}
          <span class="pts-float ${fb.points_delta >= 0 ? "plus" : "minus"}">
            ${fb.points_delta >= 0 ? "+" : ""}${fb.points_delta} ${t("points")}</span></div>
        ${fb.skipped ? "" : `
          <div style="margin-top:6px"><b>${t("correct_answer")}:</b> ${esc(fb.answer)}</div>
          ${fb.explanation ? `<div class="small dim" style="margin-top:4px"><b>${t("explanation")}:</b> ${esc(fb.explanation)}</div>` : ""}`}
      </div>
      ${fb.long_explanation ? `
        <div class="deepdive">
          <b>📚 ${t("deep_dive")}</b>
          <p>${esc(fb.long_explanation)}</p>
          ${(fb.web_sources || []).length ? `<div class="small srcs"><b>🔗 ${t("web_sources")}:</b> ${
            fb.web_sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(" · ")
          }</div>` : ""}
        </div>` : ""}
      ${fb.skipped ? "" : `
      <div id="dispute-box" style="margin-top:12px">
        <a href="#" class="small dim" onclick="event.preventDefault();FD.openDispute()">${t("dispute_link")}</a>
      </div>`}
      <button class="btn primary block" style="margin-top:14px" onclick="FD.next()">
        ${last ? "🏁 " + t("finish_session") : t("next_card") + " →"}</button>`;
  }

  $("#app").innerHTML = shell(`
  <div class="study-wrap">
    <div class="row spread" style="flex-wrap:nowrap">
      <span class="dim small truncate">${esc(st.topicTitle)} — ${t("card_x_of_y", st.idx + 1, st.cards.length)}</span>
      <a href="#" class="small" style="white-space:nowrap" onclick="event.preventDefault();FD.quit()">${t("quit_session")}</a>
    </div>
    <div class="progressbar" style="margin-top:8px"><div style="width:${Math.round(100 * st.idx / st.cards.length)}%"></div></div>
    <div class="qcard">
      <div class="row spread">
        ${diffDots(card.difficulty)}
        <span class="badge diff">+${card.points_correct} / ${card.points_wrong}</span>
      </div>
      <div class="question">${esc(card.question)}</div>
      ${answerArea}${feedbackArea}
      ${fb ? "" : (() => {
        const fiftyUsed = !!(st.fifty && st.fifty[card.id]);
        const fiftyAvailable = card.type === "multiple_choice" && card.choices.length >= 4 &&
          st.optionsShown && !fiftyUsed;
        const canFifty = state.user.points >= card.fifty_cost;
        return `<div class="row" style="margin-top:18px">
          ${fiftyUsed ? `<span class="small dim">✂️ ${t("fifty_done")}</span>` : ""}
          ${fiftyAvailable ? `<button class="btn ghost sm" ${canFifty ? "" : "disabled"} onclick="FD.fifty()">
            ✂️ ${canFifty ? t("fifty_for", card.fifty_cost) : t("fifty_locked", card.fifty_cost)}</button>` : ""}
          <button class="btn ghost sm right" ${canSkip ? "" : "disabled"} onclick="FD.skip()">
            🃏 ${canSkip ? t("skip_for", card.skip_cost) : t("skip_locked", card.skip_cost)}</button>
        </div>
        ${card.type === "multiple_choice" && st.optionsShown
          ? `<p class="small dim" style="margin:10px 0 0;text-align:center">${t("kbd_hint")}</p>` : ""}`;
      })()}
    </div>
  </div>`);
  const input = $(".qcard input[type=text]");
  if (input) input.focus();
}

function renderSummary() {
  const s = state.study.summary;
  $("#app").innerHTML = shell(`
  <div class="study-wrap">
    <div class="qcard" style="text-align:center">
      <div style="font-size:46px">🏆</div>
      <h1 style="margin:8px 0">${t("summary")}</h1>
      <div class="summary-stats">
        <div class="stat"><b style="color:var(--ok)">${s.counts.correct || 0}</b>${t("sum_correct")}</div>
        <div class="stat"><b style="color:var(--bad)">${s.counts.wrong || 0}</b>${t("sum_wrong")}</div>
        <div class="stat"><b>${s.counts.skipped || 0}</b>${t("sum_skipped")}</div>
      </div>
      ${s.bonus ? `<p>🎁 ${t("session_bonus")}: <b class="pts-float plus">+${s.bonus}</b></p>` : ""}
      <p style="font-size:18px">${t("points_earned")}:
        <b class="pts-float ${s.points_earned >= 0 ? "plus" : "minus"}">${s.points_earned >= 0 ? "+" : ""}${s.points_earned}</b></p>
      <div class="levelbar" style="margin:14px 0">
        <span class="pill">⭐ ${t("level")} ${s.level.level}</span>
        <div class="progressbar"><div style="width:${Math.round(100 * s.level.progress)}%"></div></div>
      </div>
      ${s.streak ? `<p>🔥 ${s.streak} ${t("streak_days")}</p>` : ""}
      <button class="btn primary block" onclick="FD.studyAgain()">🔁 ${t("study_again")}</button>
      <button class="btn ghost block" style="margin-top:8px" onclick="FD.backToDash()">${t("back_dashboard")}</button>
    </div>
  </div>`);
}

async function submitAnswer(payload) {
  const st = state.study;
  const card = st.cards[st.idx];
  try {
    const res = await api(`/sessions/${st.sessionId}/answer`, {
      json: { card_id: card.id, ...payload },
    });
    st.feedback = res;
    st.revealed = false;
    setPointsPill(res.points);
    renderStudy();
  } catch (err) { apiError(err); }
}

async function finishStudy() {
  const st = state.study;
  try {
    const res = await api(`/sessions/${st.sessionId}/finish`, { method: "POST" });
    st.summary = res;
    setPointsPill(res.points);
    state.user.streak = res.streak;
    state.user.level = res.level;
    renderStudy();
  } catch (err) { apiError(err); }
}

/* ---------------- settings ---------------- */

function renderSettings() {
  const u = state.user;
  $("#app").innerHTML = shell(`
  <h1>⚙️ ${t("settings")}</h1>

  <form class="card" id="profile-form">
    <h2>👤 ${t("profile")}</h2>
    <div class="row">
      <label class="field" style="flex:1;min-width:200px"><span>${t("name")}</span>
        <input type="text" name="name" value="${esc(u.name)}" required maxlength="80"></label>
      <label class="field" style="flex:1;min-width:200px"><span>${t("email")}</span>
        <input type="email" name="email" value="${esc(u.email)}" required></label>
    </div>
    <label class="field" style="max-width:340px"><span>${t("language")}</span>
      <select name="language">
        <option value="en" ${u.language === "en" ? "selected" : ""}>English</option>
        <option value="de" ${u.language === "de" ? "selected" : ""}>Deutsch</option>
      </select></label>
    <label class="switch" style="margin-bottom:12px">
      <input type="checkbox" name="theme_dark" ${u.theme === "dark" ? "checked" : ""}>
      <span class="track"></span> 🌙 ${t("appearance_dark")}</label>
    <label class="switch" style="margin-bottom:16px">
      <input type="checkbox" name="email_notifications" ${u.email_notifications ? "checked" : ""} ${u.smtp_enabled ? "" : "disabled"}>
      <span class="track"></span> 📧 ${t("notifications")} ${u.smtp_enabled ? "" : `<span class="dim small">${t("smtp_disabled_hint")}</span>`}</label>
    <button class="btn primary" type="submit">${t("save")}</button>
  </form>

  <form class="card" id="pw-form">
    <h2>🔒 ${t("change_password")}</h2>
    <div class="row">
      <label class="field" style="flex:1;min-width:200px"><span>${t("password_current")}</span>
        <input type="password" name="current_password" required autocomplete="current-password"></label>
      <label class="field" style="flex:1;min-width:200px"><span>${t("password_new")}</span>
        <input type="password" name="new_password" required minlength="8" autocomplete="new-password"></label>
    </div>
    <button class="btn primary" type="submit">${t("save")}</button>
  </form>

  <div class="card">
    <h2>💎 ${t("how_points_title")}</h2>
    <p class="small dim" style="margin-bottom:0">${t("how_points")}</p>
  </div>

  <div class="card row spread">
    <span class="dim small">${esc(u.email)}</span>
    <button class="btn danger" onclick="FD.logout()">${t("nav_logout")}</button>
  </div>`);

  $("#profile-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    // Disabled checkboxes are excluded from FormData — don't interpret a
    // disabled notifications toggle (SMTP off) as "user unchecked it".
    const notifEl = e.target.querySelector("[name=email_notifications]");
    try {
      await api("/me", { method: "PUT", json: {
        name: fd.get("name"), email: fd.get("email"), language: fd.get("language"),
        theme: fd.get("theme_dark") ? "dark" : "light",
        email_notifications: notifEl.disabled ? undefined : !!fd.get("email_notifications"),
      }});
      localStorage.setItem("fd_lang", fd.get("language"));
      localStorage.setItem("fd_theme", fd.get("theme_dark") ? "dark" : "light");
      await loadUser();
      toast(t("saved"), "success");
      renderSettings();
    } catch (err) { apiError(err); }
  };

  $("#pw-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("/me/password", { method: "PUT", json: {
        current_password: fd.get("current_password"), new_password: fd.get("new_password"),
      }});
      e.target.reset();
      toast(t("saved"), "success");
    } catch (err) { apiError(err); }
  };
}

/* ---------------- leaderboard ---------------- */

async function renderLeaderboard() {
  const rows = await api("/leaderboard");
  const medals = ["🥇", "🥈", "🥉"];
  $("#app").innerHTML = shell(`
  <h1>🏆 ${t("leaderboard")}</h1>
  <div class="card">
    <div class="scroll-x"><table class="lb">
      <tr><th>${t("lb_rank")}</th><th>${t("lb_user")}</th><th>${t("level")}</th><th>${t("lb_points")}</th></tr>
      ${rows.map((r) => `<tr>
        <td class="medal">${medals[r.rank - 1] || "#" + r.rank}</td>
        <td>${esc(r.name)}${r.name === state.user.name ? " ✦" : ""}</td>
        <td>⭐ ${r.level}</td><td><b>${r.lifetime_points}</b></td></tr>`).join("")}
    </table></div>
  </div>`);
}

/* ---------------- admin ---------------- */

async function renderAdmin() {
  const [topics, users, bg, ollama, invites] = await Promise.all([
    api("/admin/topics"), api("/admin/users"), api("/admin/background"),
    api("/admin/ollama"), api("/admin/invites"),
  ]);
  state.adminTopics = topics;

  // Generation queue: anything still queued or processing, in processing order.
  const queue = topics.filter((tp) => tp.status === "queued" || tp.status === "processing");
  const queueHtml = queue.length ? queue.map((tp, i) => `
    <div class="row spread" style="border-top:1px solid var(--border);padding:10px 0">
      <div>
        <b><a href="#/topic/${tp.id}" style="color:inherit">${esc(tp.title)}</a></b>
        <span class="badge ${tp.status}">${t("status_" + tp.status)}</span>
        ${tp.paused ? `<span class="badge queued">${t("admin_paused")}</span>` : ""}
        <div class="small dim">${t("admin_owner")}: ${esc(tp.owner)}</div>
      </div>
      <div class="row">
        ${tp.status === "queued" ? `
          <button class="btn sm ghost" ${i === 0 ? "disabled" : ""} title="${t("admin_move_up")}"
            onclick="FD.queueMove(${tp.id}, -1)">▲</button>
          <button class="btn sm ghost" ${i === queue.length - 1 ? "disabled" : ""} title="${t("admin_move_down")}"
            onclick="FD.queueMove(${tp.id}, 1)">▼</button>
          ${tp.paused
            ? `<button class="btn sm" onclick="FD.adminTopic(${tp.id},'resume')">▶ ${t("admin_resume")}</button>`
            : `<button class="btn sm" onclick="FD.adminTopic(${tp.id},'pause')">⏸ ${t("admin_pause")}</button>`}` : ""}
        <button class="btn sm danger" onclick="FD.adminStop(${tp.id})">⏹ ${t("admin_stop")}</button>
      </div>
    </div>`).join("") : `<p class="dim small">${t("admin_queue_empty")}</p>`;

  const topicsHtml = topics.map((tp) => `
    <tr>
      <td><a href="#/topic/${tp.id}">${esc(tp.title)}</a></td>
      <td class="small">${esc(tp.owner)}</td>
      <td><span class="badge ${tp.status}">${t("status_" + tp.status)}</span></td>
      <td class="small">${tp.card_count} ${t("cards")}</td>
      <td><button class="btn sm danger" onclick="FD.adminDelete(${tp.id})">${t("delete")}</button></td>
    </tr>`).join("");

  const usersHtml = users.map((us) => `
    <tr>
      <td><a href="#/admin/user/${us.id}"><b>${esc(us.name)}</b></a>${us.id === state.user.id ? ` <span class="dim">(${t("admin_you")})</span>` : ""}
        ${us.is_admin ? "🛡️" : ""}${us.disabled ? ` <span class="badge failed">🚫</span>` : ""}</td>
      <td class="small">${esc(us.email)}</td>
      <td class="small">${us.topics} ${t("admin_topics_count")}</td>
      <td>${us.id === state.user.id ? "" : (us.is_admin
        ? `<button class="btn sm ghost" onclick="FD.setAdmin(${us.id},false)">${t("admin_revoke_admin")}</button>`
        : `<button class="btn sm" onclick="FD.setAdmin(${us.id},true)">${t("admin_make_admin")}</button>`)}</td>
    </tr>`).join("");

  const bgItems = bg.items.map((it) => {
    const parts = [];
    if (it.pending_enrich) parts.push(`📚 ${t("bg_explanations")} ${it.enrich_done}/${it.total}`);
    if (it.pending_translate) parts.push(`🌐 ${t("bg_translations")} ${it.translate_done}/${it.total}`);
    // The global pause overrides every item; only show "working" when nothing is paused.
    const paused = bg.paused || it.enrich_paused;
    const working = !paused && it.activity &&
      (it.activity.startsWith("enriching") || it.activity.startsWith("translating"));
    return `<div class="row spread" style="border-top:1px solid var(--border);padding:10px 0">
      <div>
        <b><a href="#/topic/${it.id}" style="color:inherit">${esc(it.title)}</a></b>
        ${working ? `<span class="badge processing">${t("bg_working")}</span>` : ""}
        ${paused ? `<span class="badge queued">${t("admin_paused")}</span>` : ""}
        <div class="small dim">${esc(it.owner)} · ${parts.join(" · ") || "—"}</div>
      </div>
      <div class="row">
        ${bg.paused ? ""  /* per-item controls are moot while everything is paused */
          : it.enrich_paused
          ? `<button class="btn sm" onclick="FD.enrichToggle(${it.id},'resume')">▶ ${t("admin_resume")}</button>`
          : `<button class="btn sm ghost" onclick="FD.enrichToggle(${it.id},'pause')">⏸ ${t("admin_pause")}</button>`}
      </div>
    </div>`;
  }).join("");

  const inviteRows = invites.items.map((iv) => {
    const used = !!iv.used_at;
    return `<div class="row spread" style="border-top:1px solid var(--border);padding:9px 0">
      <div>
        <b>${esc(iv.email || iv.code)}</b>
        ${used ? `<span class="badge ready">${t("inv_used_by", iv.used_by_name || "?")}</span>`
               : `<span class="badge queued">${t("inv_unused")}</span>`}
      </div>
      <div class="row">
        ${used ? "" : `<button class="btn sm ghost" onclick="FD.copyInvite('${esc(iv.link)}')">${t("inv_copy_link")}</button>
          <button class="btn sm danger" onclick="FD.revokeInvite('${esc(iv.code)}')">${t("inv_revoke")}</button>`}
      </div>
    </div>`;
  }).join("");
  const invitesHtml = `<div class="card">
    <div class="row spread">
      <h2 style="margin:0">🎟️ ${t("admin_invites")}</h2>
      <label class="switch"><input type="checkbox" ${invites.require_invite ? "checked" : ""}
        onchange="FD.toggleRequireInvite(this.checked)"><span class="track"></span> ${t("inv_require")}</label>
    </div>
    <p class="small dim">${t("admin_invites_desc")}${invites.smtp_enabled ? "" : " " + t("inv_no_smtp")}</p>
    <form id="invite-form" class="row" style="gap:8px">
      <input type="email" name="email" required placeholder="${t("inv_email_ph")}" style="flex:1;min-width:200px">
      <button class="btn primary" type="submit">✉️ ${t("inv_send")}</button>
    </form>
    ${inviteRows || `<p class="small dim" style="margin-bottom:0">${t("inv_none")}</p>`}
  </div>`;

  $("#app").innerHTML = shell(`
  <h1>🛡️ ${t("admin_title")}</h1>
  <form class="card" id="ollama-form">
    <h2>🤖 ${t("ai_models")}</h2>
    <label class="field" style="max-width:280px"><span>${t("default_provider")}</span>
      <select name="default_provider">
        <option value="ollama" ${ollama.default_provider === "ollama" ? "selected" : ""}>Ollama (local)</option>
        <option value="deepseek" ${ollama.default_provider === "deepseek" ? "selected" : ""}>DeepSeek (cloud)</option>
      </select></label>

    <h3 style="margin-top:14px">🦙 ${t("ollama")}</h3>
    <label class="field"><span>${t("ollama_url")}</span>
      <input type="text" name="ollama_url" value="${esc(ollama.ollama_url)}" required>
      <small class="dim">${t("ollama_url_hint")}</small></label>
    <div class="row">
      <label class="field" style="flex:1;min-width:180px"><span>${t("ollama_model")}</span>
        <input type="text" name="ollama_model" value="${esc(ollama.ollama_model)}" required></label>
      <label class="field" style="flex:2;min-width:220px"><span>${t("ollama_key")}</span>
        <input type="password" name="ollama_api_key" placeholder="${ollama.ollama_api_key_set ? t("ollama_key_keep") : ""}"></label>
    </div>
    <button class="btn ghost sm" type="button" onclick="FD.testProvider('ollama')">🔌 ${t("test_ollama")}</button>
    <span class="small" id="test-ollama" style="margin-left:8px"></span>

    <h3 style="margin-top:18px">🌊 DeepSeek</h3>
    <p class="small dim">${t("deepseek_hint")}</p>
    <div class="row">
      <label class="field" style="flex:1;min-width:180px"><span>${t("deepseek_model")}</span>
        <input type="text" name="deepseek_model" value="${esc(ollama.deepseek_model || "")}" placeholder="deepseek-v4-flash"></label>
      <label class="field" style="flex:2;min-width:220px"><span>${t("deepseek_key")}</span>
        <input type="password" name="deepseek_api_key" placeholder="${ollama.deepseek_api_key_set ? t("ollama_key_keep") : "sk-…"}"></label>
    </div>
    <button class="btn ghost sm" type="button" onclick="FD.testProvider('deepseek')">🔌 ${t("test_deepseek")}</button>
    <span class="small" id="test-deepseek" style="margin-left:8px"></span>

    <h3 style="margin-top:18px">${t("model_per_task")}</h3>
    <p class="small dim">${t("model_per_task_hint")}</p>
    ${["generate", "enrich", "translate", "report", "judge"].map((task) => {
      const spec = (ollama.tasks && ollama.tasks[task]) || { provider: "", model: "" };
      return `<div class="row" style="align-items:flex-end">
        <label class="field" style="flex:2;min-width:180px;margin-bottom:8px"><span>${t("model_task_" + task)}</span>
          <select name="provider_${task}">
            <option value="" ${!spec.provider ? "selected" : ""}>${t("provider_default")}</option>
            <option value="ollama" ${spec.provider === "ollama" ? "selected" : ""}>Ollama</option>
            <option value="deepseek" ${spec.provider === "deepseek" ? "selected" : ""}>DeepSeek</option>
          </select></label>
        <label class="field" style="flex:3;min-width:180px;margin-bottom:8px"><span>&nbsp;</span>
          <input type="text" name="model_${task}" value="${esc(spec.model || "")}"
            placeholder="${task === "judge" ? esc(t("model_judge_ph")) : esc(t("model_default_ph"))}"></label>
      </div>`;
    }).join("")}
    <div class="row">
      <button class="btn primary" type="submit">${t("save")}</button>
    </div>
  </form>
  <div class="card">
    <div class="row spread">
      <h2 style="margin:0">🧠 ${t("admin_background")}</h2>
      <button class="btn sm ${bg.paused ? "ok" : "ghost"}" onclick="FD.bgPauseAll(${!bg.paused})">
        ${bg.paused ? "▶ " + t("admin_bg_resume_all") : "⏸ " + t("admin_bg_pause_all")}</button>
    </div>
    <p class="small dim">${t("admin_bg_desc")}</p>
    ${bg.paused ? `<div class="hintbox">⏸ ${t("admin_bg_all_paused")}</div>` : ""}
    ${bgItems || `<p class="dim small">${t("admin_bg_idle")}</p>`}
  </div>
  <div class="card">
    <h2>⏱️ ${t("admin_queue")}</h2>
    ${queueHtml}
  </div>
  <div class="card">
    <h2>👥 ${t("admin_users")}</h2>
    <div class="scroll-x"><table class="lb">
      <tr><th>${t("lb_user")}</th><th>${t("email")}</th><th></th><th></th></tr>
      ${usersHtml}
    </table></div>
  </div>
  ${invitesHtml}
  <div class="card">
    <h2>📚 ${t("admin_all_topics")}</h2>
    <div class="scroll-x"><table class="lb">
      <tr><th>${t("your_topics")}</th><th>${t("admin_owner")}</th><th></th><th></th><th></th></tr>
      ${topicsHtml}
    </table></div>
  </div>`);

  const invForm = $("#invite-form");
  if (invForm) invForm.onsubmit = async (e) => {
    e.preventDefault();
    const email = e.target.email.value.trim();
    try {
      const res = await api("/admin/invites", { json: { email } });
      await navigator.clipboard?.writeText(res.link).catch(() => {});
      toast(res.emailed ? t("inv_sent", email) : t("inv_link_copied"), "success");
      renderAdmin();
    } catch (err) { apiError(err); }
  };

  $("#ollama-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const tasks = {};
    for (const task of ["generate", "enrich", "translate", "report", "judge"]) {
      tasks[task] = { provider: fd.get("provider_" + task) || "", model: fd.get("model_" + task) || "" };
    }
    try {
      await api("/admin/ollama", { method: "PUT", json: {
        default_provider: fd.get("default_provider"),
        ollama_url: fd.get("ollama_url"), ollama_model: fd.get("ollama_model"),
        ollama_api_key: fd.get("ollama_api_key") || null,
        deepseek_model: fd.get("deepseek_model") || "",
        deepseek_api_key: fd.get("deepseek_api_key") || null,
        tasks,
      }});
      toast(t("saved"), "success");
    } catch (err) { apiError(err); }
  };

  // Live-refresh while the queue OR background AI work is active.
  const bgActive = !bg.paused && bg.items.some(
    (it) => it.pending_enrich || it.pending_translate);
  if (queue.some((tp) => tp.status === "processing") || bgActive) {
    clearTimeout(state.pollTimer);
    const tick = () => {
      if (!(location.hash.slice(2) || "").startsWith("admin")) return;
      // Don't clobber a field the admin is typing in (e.g. the Ollama form) — retry later.
      const el = document.activeElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) {
        state.pollTimer = setTimeout(tick, 4000);
        return;
      }
      renderAdmin().catch(() => {});
    };
    state.pollTimer = setTimeout(tick, 4000);
  }
}

/* ---------------- catalogue ---------------- */

async function renderCatalogue() {
  const data = await api("/catalogue");
  const byCat = {};
  for (const tp of data.topics) (byCat[tp.category] ||= []).push(tp);
  const order = data.categories.filter((c) => byCat[c]);

  const sections = order.map((cat) => `
    <h2 style="margin:22px 0 10px">${esc(cat)}</h2>
    <div class="grid">
      ${byCat[cat].map((tp) => `
        <div class="card topic-card">
          <div class="row spread">
            <span class="badge mode">${t("mode_" + tp.mode)}</span>
            ${tp.is_owner ? `<span class="badge ready">${t("cat_owner")}</span>`
              : tp.joined ? `<span class="badge ready">${t("cat_joined")}</span>` : ""}
          </div>
          <h3><a href="#/topic/${tp.id}" style="color:inherit">${esc(tp.title)}</a></h3>
          <div class="small dim">${tp.card_count} ${t("cards")}</div>
          <div class="row">
            ${tp.is_owner || tp.joined
              ? `<a class="btn sm primary" href="#/topic/${tp.id}">▶ ${t("cat_study")}</a>` : ""}
            ${tp.is_owner ? ""
              : tp.joined
              ? `<button class="btn sm ghost" onclick="FD.leaveTopic(${tp.id})">${t("cat_leave")}</button>`
              : `<button class="btn sm primary" onclick="FD.joinTopic(${tp.id})">➕ ${t("cat_join")}</button>`}
          </div>
        </div>`).join("")}
    </div>`).join("");

  $("#app").innerHTML = shell(`
    <h1>📚 ${t("catalogue_title")}</h1>
    ${data.topics.length
      ? `<p class="dim small">${t("catalogue_intro")}</p>${sections}`
      : `<div class="card empty"><div class="big">📚</div><p>${t("catalogue_empty")}</p></div>`}`);
}

/* ---------------- admin: user profile ---------------- */

async function renderAdminUser(id) {
  const profile = await api(`/admin/users/${id}`);
  const u = profile.user;

  const topicRows = profile.topics.map((tp) => {
    const pct = tp.total ? Math.round(100 * tp.seen / tp.total) : 0;
    return `
    <div style="border-top:1px solid var(--border);padding:12px 0">
      <div class="row spread">
        <span>
          <a href="#/topic/${tp.id}" style="color:inherit"><b>${esc(tp.title)}</b></a>
          <span class="badge ${tp.role === "owner" ? "mode" : "queued"}">
            ${tp.role === "owner" ? "✍️ " + t("role_owner") : "👥 " + t("role_member")}</span>
          <span class="badge ${tp.status}">${t("status_" + tp.status)}</span>
        </span>
        ${tp.role === "member"
          ? `<button class="btn sm ghost" onclick="FD.adminRemoveTopic(${tp.id}, ${id})">${t("remove")}</button>` : ""}
      </div>
      <div class="row spread" style="margin-top:6px">
        <span class="small dim">${t("prof_progress", tp.seen, tp.total)} ·
          ${tp.mastered} ${t("prof_mastered")} · ${tp.sessions} ${t("total_sessions")} ·
          ${tp.points} ${t("points")}</span>
        <span class="small dim">${pct}%</span>
      </div>
      <div class="progressbar"><div style="width:${pct}%"></div></div>
    </div>`;
  }).join("");

  $("#app").innerHTML = shell(`
  <h1>👤 ${esc(u.name)} ${u.is_admin ? "🛡️" : ""}
    ${u.disabled ? `<span class="badge failed">🚫 ${t("disabled_badge")}</span>` : ""}</h1>
  <div class="card">
    <div class="row spread">
      <div class="row">
        <span class="pill">📧 ${esc(u.email)}</span>
        <span class="pill">💎 ${u.points}</span>
        <span class="pill">⭐ ${t("level")} ${u.level.level}</span>
        ${u.streak ? `<span class="pill">🔥 ${u.streak}</span>` : ""}
        <span class="pill">📅 ${t("member_since", fmtDate(u.created_at))}</span>
      </div>
      ${u.id === state.user.id ? "" : (u.disabled
        ? `<button class="btn sm ok" onclick="FD.setDisabled(${u.id}, false)">✅ ${t("activate")}</button>`
        : `<button class="btn sm danger" onclick="FD.setDisabled(${u.id}, true)">🚫 ${t("deactivate")}</button>`)}
    </div>
  </div>

  <div class="card">
    <h2>📚 ${t("prof_topics")}</h2>
    ${topicRows || `<p class="small dim">${t("prof_no_topics")}</p>`}
    <h3 style="margin-top:16px">➕ ${t("prof_assign")}</h3>
    <p class="small dim">${t("prof_assign_hint")}</p>
    <input type="text" id="assign-search" autocomplete="off"
      placeholder="${esc(t("prof_assign_search_ph"))}"
      oninput="FD.adminTopicSearch(${id}, this.value)">
    <div id="assign-results"></div>
  </div>

  <form class="card" id="admin-pw-form">
    <h2>🔒 ${t("prof_set_pw")}</h2>
    <p class="small dim">${t("prof_pw_hint")}</p>
    <div class="row">
      <input type="password" name="password" required minlength="8" autocomplete="new-password"
        placeholder="${esc(t("password_new"))}" style="flex:1;min-width:200px">
      <button class="btn primary" type="submit">${t("save")}</button>
    </div>
  </form>`);

  $("#admin-pw-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api(`/admin/users/${id}/password`, { method: "PUT",
        json: { password: e.target.password.value } });
      e.target.reset();
      toast(t("pw_set_ok"), "success");
    } catch (err) { apiError(err); }
  };
}

/* ---------------- handlers (global) ---------------- */

window.FD = {
  _t: t,
  pickMode(el) {
    document.querySelectorAll("#mode-seg .opt").forEach((o) => o.classList.remove("active"));
    el.classList.add("active");
  },
  removeFile(i) { state.newFiles.splice(i, 1); renderFileChips(); },
  async quickStart(topicId) { await startSessionFor(topicId, 10); },
  async startSession(topicId) {
    const size = parseInt($("#sess-size")?.value || "10", 10);
    await startSessionFor(topicId, size);
  },
  async deleteCard(cardId, topicId) {
    if (!confirm(t("confirm_delete_card"))) return;
    try {
      await api(`/cards/${cardId}`, { method: "DELETE" });
      toast(t("card_deleted"), "success");
      renderTopic(topicId).catch(() => {});
    } catch (err) { apiError(err); }
  },
  filterCards(value) {
    const needle = value.trim().toLowerCase();
    document.querySelectorAll("#card-list .cardrow").forEach((row) => {
      row.style.display = !needle || row.dataset.q.includes(needle) ? "" : "none";
    });
  },
  async changeMode(id, mode) {
    try {
      await api(`/topics/${id}`, { method: "PUT", json: { mode } });
      toast(t("mode_changed"), "success");
    } catch (err) { apiError(err); }
  },
  searchUsers(topicId, value) {
    clearTimeout(state.searchTimer);
    const box = $("#member-results");
    if (!value || value.trim().length < 2) { if (box) box.innerHTML = ""; return; }
    state.searchTimer = setTimeout(async () => {
      try {
        const users = await api("/users/search?q=" + encodeURIComponent(value.trim()));
        if (!box) return;
        box.innerHTML = users.length
          ? users.map((us) => `<button class="btn sm ghost" style="margin:6px 6px 0 0"
              onclick="FD.addMember(${topicId}, ${us.id})">➕ ${esc(us.name)} <span class="dim">(${esc(us.email)})</span></button>`).join("")
          : `<p class="small dim" style="margin:8px 0 0">${t("no_user_found")}</p>`;
      } catch (err) { apiError(err); }
    }, 250);
  },
  async addMember(topicId, userId) {
    try {
      await api(`/topics/${topicId}/members`, { json: { user_id: userId } });
      toast(t("share_added"), "success");
      renderTopic(topicId).catch(() => {});
    } catch (err) { apiError(err); }
  },
  async removeMember(topicId, userId) {
    try {
      await api(`/topics/${topicId}/members/${userId}`, { method: "DELETE" });
      toast(t("share_removed"), "success");
      renderTopic(topicId).catch(() => {});
    } catch (err) { apiError(err); }
  },
  async toggleRefresh(id, on) {
    try {
      await api(`/topics/${id}`, { method: "PUT", json: { nightly_refresh: on } });
      toast(t("saved"), "success");
    } catch (err) { apiError(err); }
  },
  async toggleVisibility(id, isPublic) {
    try {
      await api(`/topics/${id}`, { method: "PUT", json: { visibility: isPublic ? "public" : "private" } });
      toast(t("saved"), "success");
      renderTopic(id).catch(() => {});
    } catch (err) { apiError(err); }
  },
  async retryTopic(id) {
    try { await api(`/topics/${id}/retry`, { method: "POST" }); route(); }
    catch (err) { apiError(err); }
  },
  async adminTopic(id, action) {
    try { await api(`/admin/topics/${id}/${action}`, { method: "POST" }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async adminStop(id) {
    if (!confirm(t("confirm_stop"))) return;
    try { await api(`/admin/topics/${id}/stop`, { method: "POST" }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async adminDelete(id) {
    if (!confirm(t("confirm_delete_topic"))) return;
    try { await api(`/topics/${id}`, { method: "DELETE" }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  adminTopicSearch(userId, value) {
    clearTimeout(state.searchTimer);
    const box = $("#assign-results");
    if (!value || value.trim().length < 2) { if (box) box.innerHTML = ""; return; }
    state.searchTimer = setTimeout(async () => {
      try {
        const topics = await api(
          `/admin/topics/search?q=${encodeURIComponent(value.trim())}&user_id=${userId}`);
        if (!box) return;
        box.innerHTML = topics.length
          ? topics.map((tp) => `<button class="btn sm ghost" style="margin:6px 6px 0 0"
              onclick="FD.adminAssignTopic(${tp.id}, ${userId})">➕ ${esc(tp.title)}
              <span class="dim">(${esc(tp.owner)})</span></button>`).join("")
          : `<p class="small dim" style="margin:8px 0 0">${t("no_topic_found")}</p>`;
      } catch (err) { apiError(err); }
    }, 250);
  },
  async adminAssignTopic(topicId, userId) {
    try {
      await api(`/topics/${topicId}/members`, { json: { user_id: userId } });
      toast(t("share_added"), "success");
      renderAdminUser(userId).catch(() => {});
    } catch (err) { apiError(err); }
  },
  async setDisabled(userId, disabled) {
    if (disabled && !confirm(t("confirm_deactivate"))) return;
    try {
      await api(`/admin/users/${userId}/disabled`, { method: "PUT", json: { disabled } });
      toast(t("saved"), "success");
      renderAdminUser(userId).catch(() => {});
    } catch (err) { apiError(err); }
  },
  async adminRemoveTopic(topicId, userId) {
    try {
      await api(`/topics/${topicId}/members/${userId}`, { method: "DELETE" });
      toast(t("share_removed"), "success");
      renderAdminUser(userId).catch(() => {});
    } catch (err) { apiError(err); }
  },
  async setAdmin(id, on) {
    try { await api(`/admin/users/${id}`, { method: "PUT", json: { is_admin: on } }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async testProvider(provider) {
    const out = $("#test-" + provider);
    if (!out) return;
    out.textContent = t("testing"); out.style.color = "";
    const modelField = provider === "deepseek" ? "deepseek_model" : "ollama_model";
    const model = $(`#ollama-form [name=${modelField}]`)?.value || "";
    try {
      const res = await api("/admin/ollama/test?provider=" + provider, { method: "POST" });
      if (res.ok) {
        out.style.color = res.model_available ? "var(--ok)" : "var(--warn)";
        out.textContent = res.model_available
          ? t("conn_ok", model)
          : t("conn_ok_no_model", model, (res.models || []).slice(0, 6).join(", ") || "—");
      } else { out.style.color = "var(--bad)"; out.textContent = res.error; }
    } catch (err) {
      out.style.color = "var(--bad)";
      out.textContent = err.error || t("err_generic", err.detail || "");
    }
  },
  async bgPauseAll(on) {
    try { await api("/admin/background", { json: { paused: on } }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async toggleRequireInvite(on) {
    try { await api("/admin/invites/require", { method: "PUT", json: { require_invite: on } });
      state.authConfig = undefined; renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async copyInvite(link) {
    try { await navigator.clipboard.writeText(link); toast(t("inv_link_copied"), "success"); }
    catch { toast(link); }
  },
  async revokeInvite(code) {
    try { await api(`/admin/invites/${encodeURIComponent(code)}`, { method: "DELETE" }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async enrichToggle(id, action) {
    try { await api(`/admin/topics/${id}/enrich/${action}`, { method: "POST" }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async queueMove(id, dir) {
    // Reorder among currently-queued topics, then persist the new priority order.
    const queued = (state.adminTopics || []).filter((tp) => tp.status === "queued");
    const ids = queued.map((tp) => tp.id);
    const i = ids.indexOf(id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    try { await api("/admin/queue/reorder", { json: { order: ids } }); renderAdmin(); }
    catch (err) { apiError(err); }
  },
  async deleteTopic(id) {
    if (!confirm(t("confirm_delete_topic"))) return;
    try { await api(`/topics/${id}`, { method: "DELETE" }); go("dashboard"); route(); }
    catch (err) { apiError(err); }
  },
  answer(value) { submitAnswer({ answer: value }); },
  selfGrade(ok) { submitAnswer({ self_grade: ok }); },
  reveal() {
    state.study.revealed = true;
    renderStudy();
  },
  openDispute() {
    const box = $("#dispute-box");
    if (!box) return;
    box.innerHTML = `
      <textarea id="dispute-text" rows="2" placeholder="${esc(t("dispute_ph"))}"></textarea>
      <button class="btn ghost sm" style="margin-top:8px" onclick="FD.submitDispute()">
        🚩 ${t("dispute_submit")}</button>`;
    $("#dispute-text").focus();
  },
  async submitDispute() {
    const st = state.study;
    const card = st.cards[st.idx];
    const ctx = ($("#dispute-text")?.value || "").trim();
    try {
      await api(`/cards/${card.id}/reevaluate`, { json: { context: ctx } });
      const box = $("#dispute-box");
      if (box) box.innerHTML = `<p class="small dim">✅ ${t("dispute_queued")}</p>`;
    } catch (err) { apiError(err); }
  },
  showOptions() {
    state.study.optionsShown = true;
    renderStudy();
  },
  async fifty() {
    const st = state.study;
    const card = st.cards[st.idx];
    try {
      const res = await api(`/sessions/${st.sessionId}/fifty`, { json: { card_id: card.id } });
      setPointsPill(res.points);
      st.fifty[card.id] = res.remove;
      renderStudy();
    } catch (err) { apiError(err); }
  },
  async skip() {
    const st = state.study;
    const card = st.cards[st.idx];
    try {
      const res = await api(`/sessions/${st.sessionId}/skip`, { json: { card_id: card.id } });
      setPointsPill(res.points);
      st.feedback = { skipped: true, correct: false, points_delta: res.points_delta };
      renderStudy();
    } catch (err) { apiError(err); }
  },
  next() {
    const st = state.study;
    st.feedback = null;
    st.revealed = false;
    st.optionsShown = false;
    if (st.idx === st.cards.length - 1) { finishStudy(); return; }
    st.idx += 1;
    renderStudy();
  },
  quit() {
    if (!confirm(t("confirm_quit"))) return;
    finishStudy();
  },
  backToDash() { state.study = null; go("dashboard"); },
  async joinTopic(id) {
    try { await api(`/topics/${id}/join`, { method: "POST" }); toast(t("joined_topic"), "success"); renderCatalogue(); }
    catch (err) { apiError(err); }
  },
  async leaveTopic(id) {
    try { await api(`/topics/${id}/leave`, { method: "POST" }); toast(t("left_topic"), "success"); renderCatalogue(); }
    catch (err) { apiError(err); }
  },
  async studyAgain() {
    const st = state.study;
    state.study = null;
    await startSessionFor(st.topicId, st.size);
  },
  async logout() {
    try { await api("/logout", { method: "POST" }); } catch {}
    state.user = null;
    go("auth");
    route();
  },
};

/* ---------------- router & boot ---------------- */

async function loadUser() {
  state.user = await api("/me");
  applyTheme();
  localStorage.setItem("fd_lang", state.user.language);
  localStorage.setItem("fd_theme", state.user.theme);
}

async function route() {
  clearTimeout(state.pollTimer);
  applyTheme();
  const parts = (location.hash.slice(2) || "dashboard").split("/");
  // Public pages (the visitor may have no account / be logged out).
  if (parts[0] === "invite") { await renderInvite(parts[1]); return; }
  if (parts[0] === "forgot") { await renderForgot(); return; }
  if (parts[0] === "reset") { await renderReset(parts[1]); return; }
  if (!state.user) {
    try { await loadUser(); } catch { renderAuth(); return; }
  }
  try {
    switch (parts[0]) {
      case "invite": await renderInvite(parts[1]); break;
      case "auth": state.user ? go("dashboard") : renderAuth(); break;
      case "new": renderNew(); break;
      case "topic": await renderTopic(parseInt(parts[1], 10)); break;
      case "study": renderStudy(); break;
      case "settings": renderSettings(); break;
      case "leaderboard": await renderLeaderboard(); break;
      case "catalogue": await renderCatalogue(); break;
      case "admin":
        if (parts[1] === "user" && parts[2]) await renderAdminUser(parseInt(parts[2], 10));
        else await renderAdmin();
        break;
      default: await renderDashboard();
    }
  } catch (err) {
    if (err?.detail !== "not_authenticated") {
      apiError(err);
      // Never leave the user on a blank page (e.g. deep link to a foreign topic).
      if (parts[0] !== "dashboard") { go("dashboard"); await renderDashboard().catch(() => {}); }
    }
  }
}

// Study-session keyboard shortcuts: 1-9 picks a choice, Enter advances,
// y/j = yes, n = no. Ignored while typing in an input (e.g. exact answers).
window.addEventListener("keydown", (e) => {
  const st = state.study;
  const onStudy = (location.hash.slice(2) || "").split("/")[0] === "study";
  if (!st || st.summary || !onStudy) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const el = e.target;
  if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
  const card = st.cards[st.idx];
  if (st.feedback) {
    if (e.key === "Enter" || e.key === "ArrowRight") { e.preventDefault(); FD.next(); }
    return;
  }
  if (card.type === "multiple_choice") {
    if (!st.optionsShown) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); FD.showOptions(); }
      return;
    }
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= card.choices.length) {
      const choice = card.choices[n - 1];
      const removed = (st.fifty && st.fifty[card.id]) || [];
      if (!removed.includes(choice)) { e.preventDefault(); FD.answer(choice); }
    }
  } else if (card.type === "yes_no") {
    if (e.key === "y" || e.key === "j" || e.key === "1") { e.preventDefault(); FD.answer("yes"); }
    if (e.key === "n" || e.key === "2") { e.preventDefault(); FD.answer("no"); }
  } else if (card.type === "open" && !st.revealed) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); FD.reveal(); }
  }
});

window.addEventListener("hashchange", route);
route();
