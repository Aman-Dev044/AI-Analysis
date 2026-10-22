/* DocuMind AI — single-page frontend (vanilla JS, no build step) */
(function () {
  "use strict";

  // ------------------------------------------------------------------ icons
  var ICONS = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    files: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 13h6M9 17h4"/>',
    settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15z"/><path d="M6.5 17A2.5 2.5 0 0 0 4 19.5 2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    check: '<path d="m9 11 3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    tick: '<path d="M20 6 9 17l-5-5"/>',
    smile: '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/>',
    graduation: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
    sparkles: '<path d="m12 3 1.9 5.8L20 10l-6.1 1.2L12 17l-1.9-5.8L4 10l6.1-1.2z"/><path d="M19 17v4M17 19h4"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    printer: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
    trash: '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    text: '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    send: '<path d="m22 2-7 20-4-9-9-4 20-7z"/><path d="M22 2 11 13"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    hash: '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    highlighter: '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
    scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10"/>',
    brain: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
  };
  function icon(name, cls) {
    return '<svg class="icon ' + (cls || "") + '" viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[name] || ICONS.info) + "</svg>";
  }
  function hydrateIcons(root) {
    (root || document).querySelectorAll("svg[data-i]").forEach(function (s) {
      s.setAttribute("viewBox", "0 0 24 24");
      s.innerHTML = ICONS[s.dataset.i] || "";
      s.removeAttribute("data-i");
    });
  }

  // ------------------------------------------------------------------ utils
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmtSize(b) {
    if (!b) return "0 B";
    var u = ["B", "KB", "MB", "GB"], i = Math.min(3, Math.floor(Math.log(b) / Math.log(1024)));
    return (b / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + u[i];
  }
  function fmtDate(iso, opts) {
    if (!iso) return "";
    var d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("en-IN", opts || { day: "numeric", month: "short", year: "numeric" });
  }
  function ago(iso) {
    if (!iso) return "";
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 45) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    if (s < 86400 * 7) return Math.round(s / 86400) + " d ago";
    return fmtDate(iso);
  }
  function relDays(n) {
    if (n === 0) return "today";
    if (n === 1) return "tomorrow";
    if (n === -1) return "yesterday";
    return n > 0 ? "in " + n + " days" : Math.abs(n) + " days ago";
  }
  function fileKind(ext) {
    ext = (ext || "").replace(".", "").toLowerCase();
    if (["png", "jpg", "jpeg", "svg", "bmp", "tif", "tiff", "webp"].indexOf(ext) >= 0) return "img";
    if (ext === "doc") return "docx";
    return ext || "txt";
  }
  function fileIcon(ext) {
    var k = fileKind(ext);
    return '<div class="file-ic ' + k + '">' + esc((ext || "").replace(".", "").slice(0, 4) || "DOC") + "</div>";
  }
  function debounce(fn, ms) { var t; return function () { var a = arguments, c = this; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); }; }

  // ------------------------------------------------------------------ api
  async function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: { "X-Requested-With": "DocuMind" } };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    var r = await fetch(url, opts);
    var data = await r.json().catch(function () { return {}; });
    if (r.status === 401) { location.href = "/login"; throw new Error("Please sign in again."); }
    if (!r.ok) throw new Error(data.error || ("Request failed (" + r.status + ")"));
    return data;
  }
  var GET = function (u) { return api("GET", u); };
  var POST = function (u, b) { return api("POST", u, b || {}); };

  // ------------------------------------------------------------------ toast & modal
  function toast(msg, kind) {
    var el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.innerHTML = icon(kind === "bad" ? "alert" : kind === "ok" ? "tick" : "info") + "<span>" + esc(msg) + "</span>";
    $("#toasts").appendChild(el);
    setTimeout(function () { el.style.opacity = "0"; el.style.transition = ".3s"; }, 3200);
    setTimeout(function () { el.remove(); }, 3600);
  }
  function confirmBox(title, text, okLabel) {
    return new Promise(function (resolve) {
      var back = document.createElement("div");
      back.className = "modal-back";
      back.innerHTML = '<div class="modal" role="dialog" aria-modal="true"><h3>' + esc(title) + "</h3><p>" + esc(text) +
        '</p><div class="row"><button class="btn" data-a="no">Cancel</button><button class="btn primary" data-a="yes">' + esc(okLabel || "Confirm") + "</button></div></div>";
      document.body.appendChild(back);
      back.addEventListener("click", function (e) {
        var a = e.target.closest("[data-a]");
        if (e.target === back || a) { back.remove(); resolve(!!a && a.dataset.a === "yes"); }
      });
      $("[data-a=yes]", back).focus();
    });
  }

  // ------------------------------------------------------------------ markdown
  var DATE_RX = /\b(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?,?\s+\d{4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})\b/gi;
  var MONEY_RX = /(?:₹|Rs\.?\s?|INR\s?|USD\s?|\$|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|crores|k|million|billion))?/gi;
  var PCT_RX = /\b\d+(?:\.\d+)?\s?%/g;

  function highlight(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (n.parentElement.closest("code,pre,a,.hl-date,.hl-money,.hl-pct")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    var combined = new RegExp("(" + DATE_RX.source + ")|(" + MONEY_RX.source + ")|(" + PCT_RX.source + ")", "gi");
    nodes.forEach(function (node) {
      var text = node.nodeValue, m, last = 0, frag = null;
      combined.lastIndex = 0;
      while ((m = combined.exec(text))) {
        if (!frag) frag = document.createDocumentFragment();
        frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        var span = document.createElement("span");
        span.className = m[1] ? "hl-date" : m[2] ? "hl-money" : "hl-pct";
        span.textContent = m[0];
        frag.appendChild(span);
        last = m.index + m[0].length;
      }
      if (frag) { frag.appendChild(document.createTextNode(text.slice(last))); node.parentNode.replaceChild(frag, node); }
    });
  }
  function renderMD(md) {
    md = String(md || "");
    var html;
    if (window.marked) {
      html = window.marked.parse(md, { gfm: true, breaks: false });
    } else {
      html = "<p>" + esc(md).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br>") + "</p>";
    }
    if (window.DOMPurify) html = window.DOMPurify.sanitize(html, { ADD_ATTR: ["checked", "disabled"] });
    var box = document.createElement("div");
    box.innerHTML = html;
    $$("a", box).forEach(function (a) { a.target = "_blank"; a.rel = "noopener noreferrer"; });
    $$("table", box).forEach(function (tb) { var w = document.createElement("div"); w.className = "table-wrap"; tb.parentNode.insertBefore(w, tb); w.appendChild(tb); });
    highlight(box);
    return box.innerHTML;
  }

  // ------------------------------------------------------------------ state
  var S = {
    user: window.DM_USER,
    meta: null,
    health: null,
    uploads: [],          // upload queue items survive navigation
    timers: [],           // view-scoped intervals, cleared on route change
    docCache: {}
  };
  function every(ms, fn) { var t = setInterval(fn, ms); S.timers.push(t); return t; }
  function clearTimers() { S.timers.forEach(clearInterval); S.timers = []; }

  function setUserCard() {
    $("#userName").textContent = S.user.name;
    $("#userEmail").textContent = S.user.email;
    $("#avatar").textContent = (S.user.name || "?").trim().split(/\s+/).map(function (p) { return p[0]; }).join("").slice(0, 2).toUpperCase();
  }

  async function checkHealth() {
    var pill = $("#ollamaPill"), dot = $(".dot", pill), txt = $("#ollamaText");
    try {
      S.health = await GET("/api/ollama/health");
    } catch (e) { S.health = { ok: false, error: e.message, models: [] }; }
    dot.className = "dot " + (S.health.ok ? "ok" : "bad");
    txt.textContent = S.health.ok
      ? (S.health.default_model_installed === false ? "Model missing: " + S.health.default_model : "Connected · " + (S.health.default_model || ""))
      : "Not reachable";
    pill.title = S.health.ok ? (S.health.url + " · v" + S.health.version) : (S.health.error || "");
  }

  // ------------------------------------------------------------------ router
  var routes = {
    dashboard: viewDashboard,
    upload: viewUpload,
    documents: viewDocuments,
    doc: viewDoc,
    settings: viewSettings
  };
  function route() {
    clearTimers();
    var parts = (location.hash.replace(/^#\/?/, "") || "dashboard").split("/");
    var name = routes[parts[0]] ? parts[0] : "dashboard";
    $$("#nav a").forEach(function (a) {
      a.classList.toggle("active", a.dataset.route === name || (name === "doc" && a.dataset.route === "documents"));
    });
    $("#sidebar").classList.remove("open");
    var view = $("#view");
    view.innerHTML = '<div class="skeleton" style="height:34px;width:260px;margin-bottom:22px"></div><div class="grid g-4"><div class="skeleton" style="height:86px"></div><div class="skeleton" style="height:86px"></div><div class="skeleton" style="height:86px"></div><div class="skeleton" style="height:86px"></div></div>';
    window.scrollTo(0, 0);
    Promise.resolve(routes[name](view, parts.slice(1))).catch(function (e) {
      view.innerHTML = '<div class="card card-pad empty">' + icon("alert") + "<p>" + esc(e.message) + "</p></div>";
    });
  }

  // ------------------------------------------------------------------ shared bits
  function statusBadge(d) {
    var s = d.status;
    if (s === "ready") return d.summary_failed ? '<span class="badge warn">Ready · summary failed</span>' : '<span class="badge ok"><span class="dot"></span>Ready</span>';
    if (s === "failed") return '<span class="badge bad">Failed</span>';
    var label = { queued: "Queued", extracting: "Extracting", analyzing: "Analyzing", summarizing: "Summarizing" }[s] || s;
    return '<span class="badge primary"><span class="dot pulse"></span>' + esc(label) + " " + (d.progress || 0) + "%</span>";
  }
  function expiryBadge(exp) {
    if (!exp) return "";
    var map = { expired: ["bad", "Expired"], expiring_soon: ["warn", "Expires " + relDays(exp.days_remaining)], verify: ["warn", "Verify expiry"], valid: ["ok", "Valid till " + fmtDate(exp.date)] };
    var m = map[exp.status] || ["", exp.status];
    return '<span class="badge ' + m[0] + '">' + icon("clock", "sm") + esc(m[1]) + "</span>";
  }
  var STEPS = [["upload", "Upload"], ["scan", "Extract"], ["brain", "Analyze"], ["sparkles", "Summarize"], ["tick", "Ready"]];
  function stepIndex(stage) {
    return { uploading: 0, queued: 1, extracting: 1, analyzing: 2, summarizing: 3, ready: 5 }[stage] ?? 1;
  }
  function stepper(stage, failedAt) {
    var idx = stepIndex(stage);
    return '<div class="stepper">' + STEPS.map(function (s, i) {
      var cls = i < idx ? "done" : i === idx ? "active" : "";
      if (stage === "failed" && i === failedAt) cls = "failed";
      if (stage === "failed" && i < failedAt) cls = "done";
      var inner = cls === "done" ? icon("tick", "sm") : cls === "active" ? '<span class="loader" style="width:14px;height:14px;border-width:2px"></span>' : cls === "failed" ? icon("x", "sm") : icon(s[0], "sm");
      return '<div class="step ' + cls + '"><div class="bubble">' + inner + "</div><span>" + s[1] + "</span></div>";
    }).join("") + "</div>";
  }

  // ================================================================== DASHBOARD
  async function viewDashboard(view) {
    var d = await GET("/api/dashboard");
    $("#navDocs").textContent = d.stats.documents;
    var hour = new Date().getHours();
    var greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    view.innerHTML =
      '<section class="hero"><div style="position:relative;z-index:1"><h1>' + greet + ", " + esc(d.user.name.split(" ")[0]) + " 👋</h1>" +
      "<p>" + new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) +
      " · " + (d.stats.processing ? d.stats.processing + " document(s) processing right now." : "Drop a document and get a beautiful summary in seconds.") + "</p></div>" +
      '<a class="btn lg" href="#/upload">' + icon("upload") + "Upload document</a></section>" +

      '<div class="grid g-4" style="margin-bottom:20px">' +
      statCard("files", "c1", d.stats.documents, "Documents") +
      statCard("sparkles", "c2", d.stats.summaries, "AI summaries") +
      statCard("activity", "c3", d.stats.processing, "Processing now") +
      statCard("hash", "c4", d.stats.words.toLocaleString("en-IN"), "Words analysed") +
      "</div>" +

      '<div class="grid g-main">' +
      '<div class="grid" style="align-content:start">' +
      (d.plan ? planCard(d.plan, true) : "") +
      '<section class="card"><div class="card-head"><h3>' + icon("files") + 'Recent documents</h3><a class="btn sm ghost" href="#/documents">View all</a></div>' +
      (d.recent.length ? '<ul class="list">' + d.recent.map(docRow).join("") + "</ul>" :
        '<div class="empty">' + icon("upload") + '<p>No documents yet.</p><a class="btn primary" href="#/upload">Upload your first document</a></div>') +
      "</section></div>" +

      '<div class="grid" style="align-content:start">' +
      '<section class="card"><div class="card-head"><h3>' + icon("alert") + "Expiry alerts</h3><small>" + d.alerts.length + "</small></div>" +
      (d.alerts.length ? '<ul class="list">' + d.alerts.map(function (a) {
        return '<li><div class="grow"><a class="title" href="#/doc/' + a.document.id + '">' + esc(a.document.title) + '</a><span class="sub">' + esc(a.text) + " · " + relDays(a.days_remaining) + "</span></div>" + expiryBadge(a) + "</li>";
      }).join("") + "</ul>" : '<div class="empty" style="padding:22px">' + icon("tick") + "<p>No documents expiring soon.</p></div>") +
      "</section>" +
      '<section class="card"><div class="card-head"><h3>' + icon("calendar") + "Upcoming dates</h3></div>" +
      (d.upcoming.length ? '<div class="card-pad"><div class="timeline">' + d.upcoming.map(function (u) {
        return '<div class="tl-item ' + esc(u.label) + '"><b>' + fmtDate(u.iso, { weekday: "short", day: "numeric", month: "short", year: "numeric" }) + "</b> " +
          '<span class="badge">' + esc(u.label) + '</span><p><a href="#/doc/' + u.document_id + '">' + esc(u.document_title) + "</a> · " + relDays(u.days_from_today) + "</p></div>";
      }).join("") + "</div></div>" : '<div class="empty" style="padding:22px">' + icon("calendar") + "<p>No upcoming deadlines found.</p></div>") +
      "</section>" +
      '<section class="card"><div class="card-head"><h3>' + icon("activity") + "Recent activity</h3></div>" +
      (d.activity.length ? '<ul class="list">' + d.activity.map(function (a) {
        return '<li><div class="grow"><span class="title" style="font-weight:600;font-size:13px">' + esc(a.description) + '</span><span class="sub">' + ago(a.created_at) + "</span></div></li>";
      }).join("") + "</ul>" : '<div class="empty">No activity yet.</div>') +
      "</section></div></div>";
    if (d.stats.processing) every(4000, function () { if (location.hash.indexOf("dashboard") >= 0 || !location.hash) refreshRecent(); });
  }
  async function refreshRecent() {
    try {
      var d = await GET("/api/dashboard");
      var list = $("#view .list");
      if (list && d.recent.length) list.innerHTML = d.recent.map(docRow).join("");
      if (!d.stats.processing) clearTimers();
    } catch (e) { /* ignore transient errors */ }
  }
  function statCard(ic, c, value, label) {
    return '<div class="card stat"><div class="stat-ic ' + c + '">' + icon(ic) + "</div><div><b>" + esc(value) + "</b><span>" + esc(label) + "</span></div></div>";
  }
  function docRow(d) {
    var processing = d.status !== "ready" && d.status !== "failed";
    return '<li>' + fileIcon(d.ext) + '<div class="grow"><a class="title" href="#/doc/' + d.id + '">' + esc(d.title) + '</a><span class="sub">' +
      esc(d.doc_type || "Processing…") + " · " + fmtSize(d.size) + " · " + ago(d.uploaded_at) + "</span>" +
      (processing ? '<div class="bar thin live" style="margin-top:6px"><i style="width:' + d.progress + '%"></i></div>' : "") +
      "</div>" + statusBadge(d) + "</li>";
  }

  // ------------------------------------------------------------------ plan card
  function planCard(p, withLink) {
    var head = '<div class="card-head"><h3>' + icon("target") + esc(p.title || "Work plan") + "</h3>" +
      '<span class="badge ' + (p.active ? "ok" : "") + '">' + (p.active ? "Active today" : "Outside plan period") + "</span></div>";
    var body = '<div class="card-pad">';
    if (p.kind === "tabular") {
      body += '<div class="plan-today"><small>Today · ' + esc(p.today.weekday) + "</small><h3>" + esc(p.today.focus) + "</h3></div>";
      body += p.entries.length ? '<div class="routine">' + p.entries.map(function (e) {
        return "<div><span>" + esc(e.start || "") + (e.end ? "–" + esc(e.end) : "") + "</span>" + esc(e.activity) + (e.location ? " · " + esc(e.location) : "") + "</div>";
      }).join("") + "</div>" : "";
      return '<section class="card">' + head + body + "</div></section>";
    }
    body += '<div class="plan-today"><small>Today · ' + esc(p.today.weekday) + " · " + fmtDate(p.today.date) + "</small><h3>" + esc(p.today.focus) + "</h3>" +
      (p.today.type === "workday" ? '<p class="muted" style="margin:6px 0 0;font-size:12.5px">Weekly deliverable due <b>' + fmtDate(p.today.due_date, { weekday: "long", day: "numeric", month: "short" }) + "</b></p>" : "") + "</div>";
    var month = p.month || p.next_month, quarter = p.quarter || p.next_quarter;
    body += '<div class="grid g-2" style="gap:12px;margin-bottom:14px">' +
      (month ? '<div class="kv" style="margin:0;grid-template-columns:1fr"><div><small>' + (p.month ? "This month" : "Next month") + " · M" + month.number + "</small><p style=\"margin:4px 0;font-size:13px\">" + esc(month.focus || "") + '</p><span class="badge">' + icon("flag", "sm") + "Review " + fmtDate(month.review_date) + "</span></div></div>" : "") +
      (quarter ? '<div class="kv" style="margin:0;grid-template-columns:1fr"><div><small>' + (p.quarter ? "This quarter" : "Next quarter") + " · Q" + quarter.number + " " + esc(quarter.title || "") + "</small><p style=\"margin:4px 0;font-size:13px\">" + esc(quarter.focus || "") + '</p><span class="badge">' + icon("flag", "sm") + "Review " + fmtDate(quarter.review_date) + "</span></div></div>" : "") +
      "</div>";
    var todayIso = p.today.date;
    body += '<div class="section-title">' + icon("calendar", "sm") + 'This week</div><div class="week">' + p.week.map(function (w) {
      return '<div class="' + (w.date === todayIso ? "today" : "") + '"><b>' + w.day.slice(0, 3) + " · " + fmtDate(w.date, { day: "numeric", month: "short" }) + "</b>" + esc(w.focus) + "</div>";
    }).join("") + "</div>";
    if (p.routine && p.routine.length) {
      var nowMin = new Date().getHours() * 60 + new Date().getMinutes();
      body += '<div class="section-title">' + icon("clock", "sm") + 'Daily routine</div><div class="routine">' + p.routine.map(function (r) {
        var s = toMin(r.from), e = toMin(r.to), now = s != null && e != null && nowMin >= s && nowMin < e;
        return '<div class="' + (now ? "now" : "") + '"><span>' + esc(r.from) + "–" + esc(r.to) + "</span>" + esc(r.what) + (now ? " · now" : "") + "</div>";
      }).join("") + "</div>";
    }
    body += '<div class="section-title">Plan progress · ' + fmtDate(p.start) + " → " + fmtDate(p.end) + '</div><div class="bar"><i style="width:' + p.progress_percent + '%"></i></div><p class="muted" style="font-size:12px;margin:6px 0 0">' + p.progress_percent + "% of the plan period completed</p>";
    if (withLink) body += '<a class="btn sm" style="margin-top:14px" href="#/doc/' + p.document_id + '">Open plan document</a>';
    return '<section class="card">' + head + body + "</div></section>";
  }
  function toMin(t) {
    var m = /^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i.exec((t || "").trim());
    if (!m) return null;
    var h = +m[1], min = +m[2], ap = (m[3] || "").toUpperCase();
    if (ap === "PM" && h < 12) h += 12;
    if (ap === "AM" && h === 12) h = 0;
    if (!ap && h < 7) h += 12; // "01:00" in a 9-to-6 routine means 1 PM
    return h * 60 + min;
  }

  // ================================================================== UPLOAD
  var uploadOpts = { auto: true, mode: null, length: null, language: null };

  function viewUpload(view) {
    var m = S.meta, prefs = S.user.prefs;
    uploadOpts.mode = uploadOpts.mode || prefs.mode;
    uploadOpts.length = uploadOpts.length || prefs.length || "standard";
    uploadOpts.language = uploadOpts.language || prefs.language;
    view.innerHTML =
      '<div class="page-head"><div><h1>Upload documents</h1><p>PDF, Word (.doc/.docx), text, CSV, images (JPG, PNG, SVG…) — up to ' + m.max_upload_mb + " MB each. Multiple files supported.</p></div></div>" +
      '<div class="grid g-main">' +
      '<div class="grid" style="align-content:start">' +
      '<div class="dropzone" id="dz" tabindex="0" role="button" aria-label="Choose files to upload">' +
      '<div class="dz-ic">' + icon("upload", "lg") + "</div><h3>Drag &amp; drop files here</h3><p>or <b style=\"color:var(--primary)\">browse your computer</b></p>" +
      '<div class="formats">' + m.extensions.map(function (e) { return '<span class="badge">' + esc(e.replace(".", "").toUpperCase()) + "</span>"; }).join("") + "</div>" +
      '<input type="file" id="fileInput" multiple hidden accept="' + m.extensions.join(",") + '"></div>' +
      '<section class="card" id="queueCard"><div class="card-head"><h3>' + icon("activity") + 'Processing queue</h3><button class="btn sm ghost" id="clearDone">Clear finished</button></div><div id="queue"></div></section>' +
      "</div>" +
      '<section class="card card-pad" style="align-self:start"><h3 style="margin:0 0 4px;font-size:15px">Summary options</h3><p class="muted" style="margin:0 0 16px;font-size:13px">Applied automatically after upload. You can generate more styles later.</p>' +
      '<label class="switch" style="margin-bottom:16px"><input type="checkbox" id="optAuto"' + (uploadOpts.auto ? " checked" : "") + "> Auto-generate summary</label>" +
      '<div class="field"><label>Summary style</label><div class="modes" id="optModes" style="grid-template-columns:1fr 1fr">' +
      m.modes.filter(function (x) { return x.key !== "custom"; }).map(function (x) {
        return '<button type="button" class="mode" data-mode="' + x.key + '" aria-pressed="' + (x.key === uploadOpts.mode) + '">' + icon(x.icon) + "<b>" + esc(x.label) + "</b><span>" + esc(x.desc) + "</span></button>";
      }).join("") + "</div></div>" +
      '<div class="field"><label>Length</label><div class="seg" id="optLength">' + m.lengths.map(function (l) {
        return '<button type="button" data-v="' + l + '" aria-pressed="' + (l === uploadOpts.length) + '">' + l + "</button>";
      }).join("") + "</div></div>" +
      '<div class="field"><label for="optLang">Language</label><select class="select" id="optLang">' + m.languages.map(function (l) {
        return "<option" + (l === uploadOpts.language ? " selected" : "") + ">" + esc(l) + "</option>";
      }).join("") + "</select></div></section></div>";

    var dz = $("#dz"), input = $("#fileInput");
    dz.addEventListener("click", function () { input.click(); });
    dz.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    ["dragenter", "dragover"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("drag"); }); });
    ["dragleave", "drop"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("drag"); }); });
    dz.addEventListener("drop", function (e) { addFiles(e.dataTransfer.files); });
    input.addEventListener("change", function () { addFiles(input.files); input.value = ""; });
    $("#optAuto").addEventListener("change", function (e) { uploadOpts.auto = e.target.checked; });
    $("#optModes").addEventListener("click", function (e) {
      var b = e.target.closest(".mode"); if (!b) return;
      uploadOpts.mode = b.dataset.mode;
      $$("#optModes .mode").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
    });
    $("#optLength").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      uploadOpts.length = b.dataset.v;
      $$("#optLength button").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
    });
    $("#optLang").addEventListener("change", function (e) { uploadOpts.language = e.target.value; });
    $("#clearDone").addEventListener("click", function () {
      S.uploads = S.uploads.filter(function (u) { return u.stage !== "ready" && u.stage !== "failed"; });
      renderQueue();
    });
    renderQueue();
    every(1000, renderQueue);
  }

  function addFiles(list) {
    var m = S.meta;
    Array.prototype.forEach.call(list, function (file) {
      var ext = "." + (file.name.split(".").pop() || "").toLowerCase();
      var item = { lid: Math.random().toString(36).slice(2), name: file.name, size: file.size, ext: ext, stage: "uploading", uploadPct: 0, progress: 0, message: "Starting upload", error: null, summary: null, docId: null };
      S.uploads.unshift(item);
      if (m.extensions.indexOf(ext) < 0) { item.stage = "failed"; item.failedAt = 0; item.error = "Unsupported file type " + ext; return; }
      if (file.size > m.max_upload_mb * 1024 * 1024) { item.stage = "failed"; item.failedAt = 0; item.error = "File is larger than " + m.max_upload_mb + " MB"; return; }
      uploadFile(file, item);
    });
    renderQueue();
  }

  function uploadFile(file, item) {
    var fd = new FormData();
    fd.append("files", file);
    fd.append("auto_summary", uploadOpts.auto ? "true" : "false");
    fd.append("mode", uploadOpts.mode || "");
    fd.append("length", uploadOpts.length || "");
    fd.append("language", uploadOpts.language || "");
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents");
    xhr.setRequestHeader("X-Requested-With", "DocuMind");
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) { item.uploadPct = Math.round(e.loaded / e.total * 100); item.message = "Uploading " + fmtSize(e.loaded) + " of " + fmtSize(e.total); renderQueue(); }
    };
    xhr.onload = function () {
      var data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* non-JSON */ }
      if (xhr.status === 401) { location.href = "/login"; return; }
      if (xhr.status >= 400) { item.stage = "failed"; item.failedAt = 0; item.error = data.error || "Upload failed"; renderQueue(); return; }
      item.docId = data.documents[0].id;
      item.stage = "queued"; item.uploadPct = 100; item.message = "Uploaded — waiting for processing";
      updateNavUploads();
      pollItem(item);
    };
    xhr.onerror = function () { item.stage = "failed"; item.failedAt = 0; item.error = "Network error while uploading"; renderQueue(); };
    xhr.send(fd);
  }

  function pollItem(item) {
    var tick = async function () {
      try {
        var s = await GET("/api/documents/" + item.docId + "/status");
        item.stage = s.stage; item.progress = s.progress; item.message = s.stage_message; item.error = s.error;
        item.docType = s.doc_type; item.summary = s.summary; item.summaryFailed = s.summary_failed;
        if (s.stage === "failed") item.failedAt = stepIndex(item.prevStage || "extracting");
        item.prevStage = s.stage;
        renderQueue();
        if (s.stage === "ready" || s.stage === "failed") {
          updateNavUploads();
          toast(s.stage === "ready" ? "“" + s.title + "” is ready" : "Processing failed: " + s.title, s.stage === "ready" ? "ok" : "bad");
          return;
        }
      } catch (e) { item.message = "Reconnecting… " + e.message; }
      setTimeout(tick, 900);
    };
    tick();
  }

  function updateNavUploads() {
    var n = S.uploads.filter(function (u) { return u.stage !== "ready" && u.stage !== "failed"; }).length;
    var el = $("#navUploads");
    el.hidden = !n; el.textContent = n;
  }

  function renderQueue() {
    var box = $("#queue");
    if (!box) return;
    if (!S.uploads.length) {
      box.innerHTML = '<div class="empty">' + icon("files") + "<p>Your uploads will appear here with live progress.</p></div>";
      return;
    }
    box.innerHTML = S.uploads.map(function (u) {
      var uploading = u.stage === "uploading", done = u.stage === "ready", failed = u.stage === "failed";
      var pct = uploading ? Math.round(u.uploadPct * 0.08) : (done ? 100 : u.progress);
      var right = done ? '<a class="btn sm primary" href="#/doc/' + u.docId + '">Open ' + icon("external", "sm") + "</a>" :
        failed ? '<span class="badge bad">Failed</span>' : '<span class="badge primary"><span class="dot pulse"></span>' + (uploading ? u.uploadPct + "% uploaded" : pct + "%") + "</span>";
      var preview = "";
      if (u.summary && (u.summary.content || u.summary.status === "running")) {
        var live = u.summary.status === "running";
        preview = '<div class="preview"><div class="preview-label">' + (live ? '<span class="loader" style="width:12px;height:12px;border-width:2px"></span>Writing summary live' : icon("sparkles", "sm") + "Summary preview") +
          '</div><div class="md' + (live ? " cursor" : "") + '" style="font-size:13.5px">' + (u.summary.content ? renderMD(u.summary.content) : '<p class="muted">Waiting for the first words…</p>') + "</div></div>";
      }
      if (done && u.summaryFailed && u.summary && u.summary.error) {
        preview += '<div class="error-box">' + icon("alert", "sm") + "<span>Summary failed: " + esc(u.summary.error) + "</span></div>";
      }
      return '<div class="job"><div class="job-top">' + fileIcon(u.ext) + '<div style="flex:1;min-width:0"><b style="display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(u.name) + '</b><span class="muted" style="font-size:12px">' +
        fmtSize(u.size) + (u.docType ? " · " + esc(u.docType) : "") + "</span></div>" + right + "</div>" +
        (failed ? "" : '<div class="bar ' + (done ? "ok" : "live") + '" style="margin-top:12px"><i style="width:' + (uploading ? u.uploadPct : pct) + '%"></i></div>') +
        stepper(u.stage, u.failedAt || 0) +
        '<div class="job-msg"><span>' + (done ? "<b>Done.</b> " : "") + esc(u.message || "") + "</span><span>" + (uploading ? "" : pct + "%") + "</span></div>" +
        (failed ? '<div class="error-box">' + icon("alert", "sm") + "<span>" + esc(u.error || "Failed") + "</span></div>" : "") +
        preview + "</div>";
    }).join("");
  }

  // ================================================================== DOCUMENTS
  var docFilter = { q: "", type: "", status: "" };
  async function viewDocuments(view, args) {
    if (args && args[0] === "search") docFilter.q = decodeURIComponent(args[1] || "");
    view.innerHTML =
      '<div class="page-head"><div><h1>Documents</h1><p>All your uploads, summaries and insights.</p></div><a class="btn primary" href="#/upload">' + icon("upload", "sm") + "Upload</a></div>" +
      '<div class="filters"><div class="input-icon">' + icon("search", "sm") + '<input class="input" id="fq" placeholder="Search by title or file name" value="' + esc(docFilter.q) + '"></div>' +
      '<select class="select" id="ftype"><option value="">All types</option></select>' +
      '<select class="select" id="fstatus"><option value="">Any status</option><option value="ready">Ready</option><option value="failed">Failed</option><option value="summarizing">Summarizing</option><option value="extracting">Extracting</option></select></div>' +
      '<div id="docList" class="doc-grid"></div>';
    $("#fstatus").value = docFilter.status;
    $("#fq").addEventListener("input", debounce(function (e) { docFilter.q = e.target.value; loadDocs(); }, 250));
    $("#ftype").addEventListener("change", function (e) { docFilter.type = e.target.value; loadDocs(); });
    $("#fstatus").addEventListener("change", function (e) { docFilter.status = e.target.value; loadDocs(); });
    $("#docList").addEventListener("click", onDocCardClick);
    await loadDocs(true);
    every(3000, function () { if ($$("#docList .bar.live").length) loadDocs(); });
  }
  async function loadDocs(first) {
    var qs = new URLSearchParams(docFilter).toString();
    var docs = await GET("/api/documents?" + qs);
    if (first) {
      var all = await GET("/api/documents");
      $("#navDocs").textContent = all.length;
      var types = Array.from(new Set(all.map(function (d) { return d.doc_type; }).filter(Boolean))).sort();
      $("#ftype").innerHTML = '<option value="">All types</option>' + types.map(function (t) { return "<option>" + esc(t) + "</option>"; }).join("");
      $("#ftype").value = docFilter.type;
    }
    var box = $("#docList");
    if (!box) return;
    if (!docs.length) {
      box.innerHTML = '<div class="card empty" style="grid-column:1/-1">' + icon("files") + "<p>" + (docFilter.q || docFilter.type || docFilter.status ? "No documents match your filters." : "No documents yet.") + '</p><a class="btn primary" href="#/upload">Upload a document</a></div>';
      return;
    }
    box.innerHTML = docs.map(function (d) {
      var processing = d.status !== "ready" && d.status !== "failed";
      return '<article class="card doc-card" data-id="' + d.id + '"><div class="top">' + fileIcon(d.ext) + '<div style="min-width:0;flex:1"><h4 title="' + esc(d.title) + '">' + esc(d.title) + '</h4><div class="meta">' +
        esc(d.doc_type || "—") + " · " + fmtSize(d.size) + "</div></div></div>" +
        (processing ? '<div><div class="bar thin live"><i style="width:' + d.progress + '%"></i></div><div class="meta" style="margin-top:6px">' + esc(d.stage_message || "") + "</div></div>" :
          '<div class="meta">' + (d.pages ? d.pages + " pages · " : "") + (d.word_count ? d.word_count.toLocaleString("en-IN") + " words · " : "") + (d.reading_minutes ? d.reading_minutes + " min read" : "") + "</div>") +
        '<div class="row wrap" style="gap:6px">' + statusBadge(d) + expiryBadge(d.expiry) + (d.ocr_used ? '<span class="badge info">OCR</span>' : "") + (d.is_plan ? '<span class="badge primary">Plan</span>' : "") + "</div>" +
        '<div class="foot"><span class="meta">' + ago(d.uploaded_at) + '</span><div class="row" style="gap:4px">' +
        '<a class="btn sm ghost icon-only" title="Download original" href="/api/documents/' + d.id + '/file?download=1" data-stop>' + icon("download", "sm") + "</a>" +
        '<button class="btn sm ghost icon-only danger" title="Delete" data-del="' + d.id + '" data-title="' + esc(d.title) + '">' + icon("trash", "sm") + "</button></div></div></article>";
    }).join("");
  }
  async function onDocCardClick(e) {
    if (e.target.closest("[data-stop]")) return;
    var del = e.target.closest("[data-del]");
    if (del) {
      e.stopPropagation();
      if (await confirmBox("Delete document?", "“" + del.dataset.title + "” and all its summaries and chats will be permanently removed.", "Delete")) {
        try { await api("DELETE", "/api/documents/" + del.dataset.del); toast("Document deleted", "ok"); loadDocs(true); } catch (err) { toast(err.message, "bad"); }
      }
      return;
    }
    var card = e.target.closest(".doc-card");
    if (card) location.hash = "#/doc/" + card.dataset.id;
  }

  // ================================================================== DOCUMENT VIEW
  var D = null; // current document state

  async function viewDoc(view, args) {
    var id = args[0];
    var doc = await GET("/api/documents/" + id);
    D = { doc: doc, current: null, mode: S.user.prefs.mode || "short", length: S.user.prefs.length || "standard", language: S.user.prefs.language || "English", tab: "insights", size: "m", hl: true, chat: [] };
    if (doc.status !== "ready" && doc.status !== "failed") return renderProcessing(view, doc);
    renderDoc(view);
  }

  function renderProcessing(view, doc) {
    view.innerHTML = docHeader(doc) +
      '<section class="card card-pad" style="max-width:820px"><h3 style="margin:0 0 4px">Processing your document…</h3><p class="muted" style="margin:0">You can leave this page — processing continues in the background.</p>' +
      '<div id="procBox"></div></section>';
    bindHeader(doc);
    var paint = function (s) {
      var box = $("#procBox"); if (!box) return;
      var sum = s.summary;
      box.innerHTML = '<div class="bar live" style="margin-top:18px"><i style="width:' + s.progress + '%"></i></div>' + stepper(s.stage) +
        '<div class="job-msg"><span>' + esc(s.stage_message || "") + "</span><span>" + s.progress + "%</span></div>" +
        (sum && sum.content ? '<div class="preview" style="max-height:none"><div class="preview-label"><span class="loader" style="width:12px;height:12px;border-width:2px"></span>Writing summary live</div><div class="md cursor">' + renderMD(sum.content) + "</div></div>" : "");
    };
    paint(doc);
    every(900, async function () {
      try {
        var s = await GET("/api/documents/" + doc.id + "/status");
        if (s.status === "ready" || s.status === "failed") { clearTimers(); route(); return; }
        paint(s);
      } catch (e) { /* retry next tick */ }
    });
  }

  function docHeader(doc) {
    return '<div class="doc-head"><div style="min-width:0;flex:1"><a href="#/documents" class="muted" style="font-size:12.5px;font-weight:600">← All documents</a>' +
      '<div class="row" style="margin-top:6px">' + fileIcon(doc.ext) + '<h1 id="docTitle" contenteditable="true" spellcheck="false" title="Click to rename">' + esc(doc.title) + "</h1></div>" +
      '<div class="doc-meta">' + statusBadge(doc) + (doc.doc_type ? '<span class="badge primary">' + esc(doc.doc_type) + "</span>" : "") + expiryBadge(doc.expiry) +
      (doc.ocr_used ? '<span class="badge info">' + icon("scan", "sm") + "OCR · " + esc(doc.ocr_engine || "") + "</span>" : "") +
      "<span>" + esc(doc.filename) + " · " + fmtSize(doc.size) + "</span>" + (doc.pages ? "<span>· " + doc.pages + " pages</span>" : "") +
      (doc.word_count ? "<span>· " + doc.word_count.toLocaleString("en-IN") + " words</span>" : "") + "<span>· uploaded " + ago(doc.uploaded_at) + "</span></div></div>" +
      '<div class="row actions">' +
      '<a class="btn sm" target="_blank" rel="noopener" href="/api/documents/' + doc.id + '/file">' + icon("eye", "sm") + "View original</a>" +
      '<button class="btn sm" id="reprocessBtn">' + icon("refresh", "sm") + "Reprocess</button>" +
      '<button class="btn sm danger" id="deleteBtn">' + icon("trash", "sm") + "Delete</button></div></div>";
  }
  function bindHeader(doc) {
    var t = $("#docTitle");
    t.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); t.blur(); } });
    t.addEventListener("blur", async function () {
      var v = t.textContent.trim();
      if (!v || v === doc.title) { t.textContent = doc.title; return; }
      try { await api("PATCH", "/api/documents/" + doc.id, { title: v }); doc.title = v; toast("Renamed", "ok"); } catch (e) { toast(e.message, "bad"); t.textContent = doc.title; }
    });
    $("#reprocessBtn").addEventListener("click", async function () {
      if (!(await confirmBox("Reprocess document?", "Text will be extracted again and a fresh summary generated.", "Reprocess"))) return;
      try { await POST("/api/documents/" + doc.id + "/reprocess"); toast("Reprocessing started", "ok"); route(); } catch (e) { toast(e.message, "bad"); }
    });
    $("#deleteBtn").addEventListener("click", async function () {
      if (!(await confirmBox("Delete document?", "This permanently removes the file, summaries and chat.", "Delete"))) return;
      try { await api("DELETE", "/api/documents/" + doc.id); toast("Document deleted", "ok"); location.hash = "#/documents"; } catch (e) { toast(e.message, "bad"); }
    });
  }

  function renderDoc(view) {
    var doc = D.doc, m = S.meta;
    if (doc.status === "failed") {
      view.innerHTML = docHeader(doc) + '<section class="card card-pad" style="max-width:760px"><div class="error-box" style="margin:0">' + icon("alert") +
        "<div><b>Processing failed</b><br>" + esc(doc.error || "Unknown error") + "</div></div>" +
        '<p class="muted">Check that the file is readable and that Ollama / OCR are configured, then reprocess.</p></section>';
      bindHeader(doc);
      return;
    }
    var models = (S.health && S.health.models) || [];
    var chosenModel = S.user.prefs.model || m.default_model;
    view.innerHTML = docHeader(doc) +
      '<div class="doc-layout"><div class="grid" style="align-content:start">' +
      '<section class="card card-pad studio"><div class="row between wrap" style="margin-bottom:12px"><h3 style="margin:0;font-size:15px" class="row">' + icon("sparkles") + "Summary studio</h3>" +
      '<span class="muted" style="font-size:12.5px">Pick a style, then Generate</span></div>' +
      '<div class="modes" id="modes">' + m.modes.map(function (x) {
        return '<button type="button" class="mode" data-mode="' + x.key + '" aria-pressed="' + (x.key === D.mode) + '">' + icon(x.icon) + "<b>" + esc(x.label) + "</b><span>" + esc(x.desc) + "</span></button>";
      }).join("") + "</div>" +
      '<div class="field" id="customBox" style="margin:14px 0 0" ' + (D.mode === "custom" ? "" : "hidden") + '><label for="customText">Your instructions</label><textarea class="textarea" id="customText" placeholder="e.g. Summarise only the payment terms as a table and list penalties"></textarea></div>' +
      '<div class="opts"><div class="field"><label>Length</label><div class="seg" id="lenSeg">' + m.lengths.map(function (l) {
        return '<button type="button" data-v="' + l + '" aria-pressed="' + (l === D.length) + '">' + l + "</button>";
      }).join("") + "</div></div>" +
      '<div class="field"><label for="langSel">Language</label><select class="select" id="langSel" style="width:150px">' + m.languages.map(function (l) {
        return "<option" + (l === D.language ? " selected" : "") + ">" + esc(l) + "</option>";
      }).join("") + "</select></div>" +
      '<div class="field"><label for="modelSel">Model</label><select class="select" id="modelSel" style="width:190px">' +
      (models.length ? models : [chosenModel]).map(function (x) { return "<option" + (x === chosenModel ? " selected" : "") + ">" + esc(x) + "</option>"; }).join("") + "</select></div>" +
      '<div style="flex:1"></div><button class="btn primary lg" id="genBtn">' + icon("sparkles") + "Generate</button></div></section>" +

      '<section class="card" id="outCard"><div class="history" id="history"></div>' +
      '<div class="output-bar"><div class="grow"><b id="outTitle">Summary</b> <span class="muted" id="outMeta" style="font-size:12px"></span></div>' +
      '<div class="seg" id="sizeSeg" title="Text size"><button data-v="s" aria-pressed="false">A-</button><button data-v="m" aria-pressed="true">A</button><button data-v="l" aria-pressed="false">A+</button></div>' +
      '<button class="btn sm icon-only" id="hlBtn" title="Toggle date/amount highlights" aria-pressed="true">' + icon("highlighter", "sm") + "</button>" +
      '<button class="btn sm icon-only" id="copyBtn" title="Copy">' + icon("copy", "sm") + "</button>" +
      '<button class="btn sm icon-only" id="mdBtn" title="Download Markdown">' + icon("download", "sm") + "</button>" +
      '<button class="btn sm icon-only" id="printBtn" title="Print / Save as PDF">' + icon("printer", "sm") + "</button>" +
      '<button class="btn sm icon-only danger" id="delSumBtn" title="Delete this summary">' + icon("trash", "sm") + "</button></div>" +
      '<div class="output size-m" id="output"></div></section></div>' +

      '<aside class="side-sticky"><section class="card"><div class="tabs" role="tablist" id="tabs">' +
      tabBtn("insights", "info", "Insights") + tabBtn("chat", "chat", "Ask AI") + tabBtn("text", "text", "Text") + (doc.plan ? tabBtn("plan", "target", "Plan") : "") +
      '</div><div id="tabBody"></div></section></aside></div>';

    bindHeader(doc);
    bindStudio();
    renderHistory();
    var first = doc.summaries.find(function (s) { return s.status === "running" || s.status === "queued"; }) || doc.summaries[0];
    selectSummary(first ? first.id : null);
    switchTab(D.tab);
  }
  function tabBtn(key, ic, label) {
    return '<button role="tab" data-tab="' + key + '" aria-selected="false">' + icon(ic, "sm") + label + "</button>";
  }

  function bindStudio() {
    $("#modes").addEventListener("click", function (e) {
      var b = e.target.closest(".mode"); if (!b) return;
      D.mode = b.dataset.mode;
      $$("#modes .mode").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
      $("#customBox").hidden = D.mode !== "custom";
      if (D.mode === "custom") $("#customText").focus();
    });
    $("#lenSeg").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      D.length = b.dataset.v;
      $$("#lenSeg button").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
    });
    $("#langSel").addEventListener("change", function (e) { D.language = e.target.value; });
    $("#genBtn").addEventListener("click", generate);
    $("#sizeSeg").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      D.size = b.dataset.v;
      $$("#sizeSeg button").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
      $("#output").className = "output size-" + D.size + (D.hl ? "" : " no-hl");
    });
    $("#hlBtn").addEventListener("click", function () {
      D.hl = !D.hl;
      $("#hlBtn").setAttribute("aria-pressed", D.hl);
      $("#hlBtn").classList.toggle("ghost", !D.hl);
      $("#output").classList.toggle("no-hl", !D.hl);
    });
    $("#copyBtn").addEventListener("click", function () {
      if (!D.current || !D.current.content) return toast("Nothing to copy yet");
      navigator.clipboard.writeText(D.current.content).then(function () { toast("Summary copied", "ok"); }, function () { toast("Copy failed", "bad"); });
    });
    $("#mdBtn").addEventListener("click", function () {
      if (!D.current || !D.current.content) return toast("Nothing to download yet");
      var blob = new Blob(["# " + D.doc.title + " — " + D.current.mode_label + "\n\n" + D.current.content], { type: "text/markdown" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (D.doc.title || "summary").replace(/[^\w\- ]+/g, "") + " - " + D.current.mode_label + ".md";
      a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });
    $("#printBtn").addEventListener("click", function () { window.print(); });
    $("#delSumBtn").addEventListener("click", async function () {
      if (!D.current) return;
      if (!(await confirmBox("Delete this summary?", "Only this version is removed.", "Delete"))) return;
      await api("DELETE", "/api/summaries/" + D.current.id);
      D.doc.summaries = D.doc.summaries.filter(function (s) { return s.id !== D.current.id; });
      renderHistory();
      selectSummary(D.doc.summaries[0] ? D.doc.summaries[0].id : null);
    });
    $("#tabs").addEventListener("click", function (e) { var b = e.target.closest("[data-tab]"); if (b) switchTab(b.dataset.tab); });
  }

  async function generate() {
    var body = { mode: D.mode, length: D.length, language: D.language, model: $("#modelSel").value };
    if (D.mode === "custom") {
      body.instructions = $("#customText").value.trim();
      if (!body.instructions) { toast("Write your custom instructions first", "bad"); $("#customText").focus(); return; }
    }
    var btn = $("#genBtn");
    btn.disabled = true;
    try {
      var s = await POST("/api/documents/" + D.doc.id + "/summaries", body);
      D.doc.summaries.unshift(s);
      renderHistory();
      selectSummary(s.id);
      $("#outCard").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { toast(e.message, "bad"); }
    btn.disabled = false;
  }

  function renderHistory() {
    var h = $("#history");
    if (!h) return;
    if (!D.doc.summaries.length) { h.hidden = true; return; }
    h.hidden = false;
    h.innerHTML = D.doc.summaries.map(function (s) {
      var st = s.status === "done" ? "" : s.status === "failed" ? '<span class="dot" style="color:var(--bad)"></span>' : '<span class="dot pulse" style="color:var(--primary)"></span>';
      return '<button data-sid="' + s.id + '" aria-pressed="' + (D.current && D.current.id === s.id) + '">' + st + esc(s.mode_label) + " · " + esc(s.language) + ' <span class="muted">' + ago(s.created_at) + "</span></button>";
    }).join("");
    h.onclick = function (e) { var b = e.target.closest("[data-sid]"); if (b) selectSummary(b.dataset.sid); };
  }

  var summaryPoll = null;
  function selectSummary(id) {
    if (summaryPoll) { clearInterval(summaryPoll); summaryPoll = null; }
    var out = $("#output");
    if (!id) {
      D.current = null;
      $("#outTitle").textContent = "No summary yet";
      $("#outMeta").textContent = "";
      out.innerHTML = '<div class="empty">' + icon("sparkles") + "<p>Choose a style above and click <b>Generate</b> to create your first summary.</p></div>";
      return;
    }
    D.current = D.doc.summaries.find(function (s) { return s.id === id; });
    $$("#history button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.sid === id); });
    paintSummary();
    if (D.current.status === "queued" || D.current.status === "running") {
      summaryPoll = setInterval(async function () {
        try {
          var s = await GET("/api/summaries/" + id);
          var i = D.doc.summaries.findIndex(function (x) { return x.id === id; });
          if (i >= 0) D.doc.summaries[i] = s;
          if (!D.current || D.current.id !== id) return;
          D.current = s;
          paintSummary();
          if (s.status === "done" || s.status === "failed") {
            clearInterval(summaryPoll); summaryPoll = null;
            renderHistory();
            toast(s.status === "done" ? s.mode_label + " ready" : "Summary failed", s.status === "done" ? "ok" : "bad");
          }
        } catch (e) { /* retry */ }
      }, 700);
      S.timers.push(summaryPoll);
    }
  }

  function paintSummary() {
    var s = D.current, out = $("#output");
    if (!out || !s) return;
    $("#outTitle").textContent = s.mode_label;
    $("#outMeta").textContent = "· " + s.language + " · " + s.length + " · " + (s.model || "") +
      (s.duration_ms ? " · " + (s.duration_ms / 1000).toFixed(1) + "s" : "") + " · " + ago(s.created_at);
    var running = s.status === "queued" || s.status === "running";
    var html = "";
    if (running) {
      html += '<div class="gen-status"><span class="loader"></span><span>' + esc(s.stage_message || "Starting…") + '</span><div class="bar live"><i style="width:' + (s.progress || 2) + '%"></i></div><b>' + (s.progress || 0) + "%</b></div>";
    }
    if (s.status === "failed") {
      html += '<div class="error-box" style="margin:0 0 16px">' + icon("alert", "sm") + "<div><b>Generation failed.</b> " + esc(s.error || "") +
        '<br><span style="color:var(--text-2)">Check the Ollama connection in Settings, then try Generate again.</span></div></div>';
    }
    if (s.instructions) html += '<blockquote class="md" style="font-size:13px;margin:0 0 16px;padding:10px 14px;border-left:3px solid var(--primary);background:var(--primary-soft);border-radius:0 8px 8px 0"><b>Custom:</b> ' + esc(s.instructions) + "</blockquote>";
    html += s.content ? '<div class="md' + (running ? " cursor" : "") + '">' + renderMD(s.content) + "</div>" :
      running ? '<div class="grid" style="gap:10px"><div class="skeleton" style="height:22px;width:60%"></div><div class="skeleton" style="height:14px"></div><div class="skeleton" style="height:14px;width:92%"></div><div class="skeleton" style="height:14px;width:80%"></div></div>' : "";
    out.innerHTML = html;
  }

  // ------------------------------------------------------------------ side tabs
  function switchTab(tab) {
    D.tab = tab;
    $$("#tabs [data-tab]").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.tab === tab); });
    var body = $("#tabBody");
    if (tab === "insights") body.innerHTML = '<div class="tab-body">' + insightsHTML(D.doc) + "</div>";
    else if (tab === "plan") body.innerHTML = '<div class="tab-body" style="padding:0">' + planCard(Object.assign({ title: "Plan overview" }, D.doc.plan), false).replace('<section class="card">', "<div>").replace(/<\/section>$/, "</div>") + "</div>";
    else if (tab === "text") renderTextTab(body);
    else if (tab === "chat") renderChatTab(body);
  }

  function insightsHTML(doc) {
    var i = doc.insights || {}, st = i.stats || {};
    var h = '<div class="kv"><div><small>Type</small><b style="font-size:13.5px">' + esc(i.doc_type || "—") + "</b></div><div><small>Reading time</small><b>" + (st.reading_minutes || 0) + " min</b></div>" +
      "<div><small>Words</small><b>" + (st.words || 0).toLocaleString("en-IN") + "</b></div><div><small>Pages</small><b>" + (doc.pages || "—") + "</b></div></div>";
    if (i.expiry) {
      var e = i.expiry, cls = e.status;
      var label = { expired: "Expired " + relDays(e.days_remaining), expiring_soon: "Expires " + relDays(e.days_remaining), valid: "Valid · " + relDays(e.days_remaining), verify: "Expiry needs verification" }[e.status];
      h += '<div class="expiry-card ' + cls + '">' + icon("clock", "lg") + "<div><b>" + esc(label) + "</b><span>" + esc(e.text) + " — " + esc(e.context) + "</span></div></div>";
    }
    var dates = i.dates || [];
    h += '<div class="section-title">' + icon("calendar", "sm") + "Key dates (" + dates.length + ")</div>";
    h += dates.length ? '<div class="timeline">' + dates.slice(0, 40).map(function (d) {
      return '<div class="tl-item ' + (d.days_from_today < 0 ? "past " : "") + esc(d.label) + '"><b>' + fmtDate(d.iso, { day: "numeric", month: "short", year: "numeric" }) + "</b> " +
        '<span class="badge">' + esc(d.label) + "</span>" + (d.ambiguous ? ' <span class="badge warn">check format</span>' : "") +
        ' <span class="muted" style="font-size:11.5px">' + relDays(d.days_from_today) + "</span><p>" + esc(d.context) + "</p></div>";
    }).join("") + "</div>" : '<p class="muted" style="font-size:13px">No dates detected.</p>';
    function chips(title, ic, arr, cls) {
      if (!arr || !arr.length) return "";
      return '<div class="section-title">' + icon(ic, "sm") + title + '</div><div class="chips">' + arr.map(function (x) { return '<span class="chip ' + (cls || "") + '">' + esc(x) + "</span>"; }).join("") + "</div>";
    }
    h += chips("Amounts", "hash", i.amounts, "money") + chips("Percentages", "activity", i.percentages) + chips("Emails", "chat", i.emails) +
      chips("Phone numbers", "info", i.phones) + chips("Links", "external", i.urls) + chips("Sections", "list", i.headings);
    return h;
  }

  async function renderTextTab(body) {
    body.innerHTML = '<div class="tab-body"><div class="row" style="margin-bottom:12px"><div class="input-icon" style="flex:1">' + icon("search", "sm") +
      '<input class="input" id="textSearch" placeholder="Find in text…"></div><span class="muted" id="hitCount" style="font-size:12px;min-width:60px"></span></div>' +
      '<div class="row" style="margin-bottom:12px;gap:6px"><button class="btn sm" id="copyText">' + icon("copy", "sm") + 'Copy text</button><a class="btn sm" href="/api/documents/' + D.doc.id + '/file?download=1">' + icon("download", "sm") + "Original</a></div>" +
      '<div class="source-text" id="srcText"><div class="skeleton" style="height:200px"></div></div></div>';
    if (D.text == null || D.textFor !== D.doc.id) {
      D.text = (await GET("/api/documents/" + D.doc.id + "/text")).text;
      D.textFor = D.doc.id;
    }
    var paint = function (q) {
      var src = $("#srcText"); if (!src) return;
      if (!q) { src.textContent = D.text; $("#hitCount").textContent = ""; return; }
      var rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), count = 0;
      src.innerHTML = esc(D.text).replace(new RegExp(esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), function (m) { count++; return "<mark>" + m + "</mark>"; });
      $("#hitCount").textContent = count + " match" + (count === 1 ? "" : "es");
      var first = $("mark", src); if (first) first.scrollIntoView({ block: "center" });
      rx.lastIndex = 0;
    };
    paint("");
    $("#textSearch").addEventListener("input", debounce(function (e) { paint(e.target.value.trim()); }, 200));
    $("#copyText").addEventListener("click", function () { navigator.clipboard.writeText(D.text).then(function () { toast("Text copied", "ok"); }); });
  }

  // ------------------------------------------------------------------ chat
  var SUGGESTIONS = ["What is this document about?", "List all deadlines and due dates", "What are the key numbers?", "What do I need to do next?", "Iska short summary Hinglish mein do"];
  async function renderChatTab(body) {
    body.innerHTML = '<div class="chat"><div class="chat-log" id="chatLog"><div class="skeleton" style="height:60px"></div></div>' +
      '<div class="suggest" id="suggest">' + SUGGESTIONS.map(function (q) { return "<button>" + esc(q) + "</button>"; }).join("") + "</div>" +
      '<form class="chat-form" id="chatForm"><textarea class="textarea" id="chatInput" rows="1" placeholder="Ask anything about this document…"></textarea>' +
      '<button class="btn primary icon-only" style="height:42px;width:42px" aria-label="Send">' + icon("send", "sm") + "</button></form>" +
      '<div class="row between" style="padding:0 14px 10px"><span class="muted" style="font-size:11.5px">Answers come only from this document.</span><button class="btn sm ghost" id="clearChat">Clear chat</button></div></div>';
    D.chat = await GET("/api/documents/" + D.doc.id + "/chat");
    paintChat();
    D.chat.filter(function (m) { return m.status === "queued" || m.status === "running"; }).forEach(function (m) { pollChat(m.id); });
    $("#suggest").addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) sendChat(b.textContent); });
    $("#chatForm").addEventListener("submit", function (e) { e.preventDefault(); sendChat($("#chatInput").value); });
    $("#chatInput").addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(e.target.value); } });
    $("#clearChat").addEventListener("click", async function () {
      await api("DELETE", "/api/documents/" + D.doc.id + "/chat"); D.chat = []; paintChat();
    });
  }
  function paintChat() {
    var log = $("#chatLog"); if (!log) return;
    $("#suggest").hidden = D.chat.length > 0;
    if (!D.chat.length) {
      log.innerHTML = '<div class="empty">' + icon("chat") + "<p>Ask a question — the AI answers using only this document.</p></div>";
      return;
    }
    log.innerHTML = D.chat.map(function (m) {
      if (m.role === "user") return '<div class="msg user">' + esc(m.content) + "</div>";
      var running = m.status === "queued" || m.status === "running";
      var inner = m.status === "failed" ? '<span style="color:var(--bad)">' + esc(m.error || "Failed") + "</span>" :
        m.content ? '<div class="md' + (running ? " cursor" : "") + '">' + renderMD(m.content) + "</div>" : '<span class="row muted"><span class="loader" style="width:14px;height:14px;border-width:2px"></span>Thinking…</span>';
      return '<div class="msg assistant">' + inner + "</div>";
    }).join("");
    log.scrollTop = log.scrollHeight;
  }
  async function sendChat(text) {
    text = (text || "").trim();
    if (!text) return;
    $("#chatInput").value = "";
    try {
      var r = await POST("/api/documents/" + D.doc.id + "/chat", { question: text, language: D.language });
      D.chat.push(r.question, r.answer);
      paintChat();
      pollChat(r.answer.id);
    } catch (e) { toast(e.message, "bad"); }
  }
  function pollChat(id) {
    var t = setInterval(async function () {
      try {
        var m = await GET("/api/chat/" + id);
        var i = D.chat.findIndex(function (x) { return x.id === id; });
        if (i < 0) { clearInterval(t); return; }
        D.chat[i] = m;
        if (D.tab === "chat") paintChat();
        if (m.status === "done" || m.status === "failed") clearInterval(t);
      } catch (e) { /* retry */ }
    }, 600);
    S.timers.push(t);
  }

  // ================================================================== SETTINGS
  async function viewSettings(view) {
    await checkHealth();
    var h = S.health, p = S.user.prefs, m = S.meta;
    var models = h.models && h.models.length ? h.models : [m.default_model];
    view.innerHTML = '<div class="page-head"><div><h1>Settings</h1><p>Profile, summary defaults and AI connection.</p></div></div>' +
      '<div class="grid g-2">' +
      '<section class="card"><div class="card-head"><h3>' + icon("server") + 'Ollama connection</h3><button class="btn sm" id="testBtn">' + icon("refresh", "sm") + "Test</button></div><div class=\"card-pad\">" +
      '<div class="expiry-card ' + (h.ok ? "valid" : "expired") + '">' + icon(h.ok ? "tick" : "alert", "lg") + "<div><b>" + (h.ok ? "Connected" : "Not reachable") + "</b><span>" + esc(h.url || "") + (h.version ? " · Ollama v" + esc(h.version) : "") + "</span></div></div>" +
      (h.ok ? "" : '<p class="muted" style="font-size:13px">' + esc(h.error || "") + "<br>Set <code>OLLAMA_URL</code> in <code>.env</code> to your VPS address (e.g. <code>http://YOUR_VPS_IP:11434</code>) and make sure port 11434 is reachable.</p>") +
      (h.ok && h.default_model_installed === false ? '<div class="error-box">' + icon("alert", "sm") + "<span>Default model <b>" + esc(h.default_model) + "</b> is not installed on the server. Run <code>ollama pull " + esc(h.default_model) + "</code> on the VPS or choose another model below.</span></div>" : "") +
      '<div class="section-title">Installed models (' + (h.models || []).length + ')</div><div class="chips">' + (h.models || []).map(function (x) { return '<span class="chip">' + esc(x) + "</span>"; }).join("") + "</div></div></section>" +

      '<section class="card"><div class="card-head"><h3>' + icon("sparkles") + 'Summary defaults</h3></div><form class="card-pad" id="prefsForm">' +
      '<div class="field"><label for="pName">Display name</label><input class="input" id="pName" value="' + esc(S.user.name) + '"></div>' +
      '<div class="field"><label for="pMode">Default summary style</label><select class="select" id="pMode">' + m.modes.filter(function (x) { return x.key !== "custom"; }).map(function (x) { return '<option value="' + x.key + '"' + (x.key === p.mode ? " selected" : "") + ">" + esc(x.label) + "</option>"; }).join("") + "</select></div>" +
      '<div class="grid g-2" style="gap:12px"><div class="field"><label for="pLen">Default length</label><select class="select" id="pLen">' + m.lengths.map(function (x) { return "<option" + (x === p.length ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></div>" +
      '<div class="field"><label for="pLang">Default language</label><select class="select" id="pLang">' + m.languages.map(function (x) { return "<option" + (x === p.language ? " selected" : "") + ">" + esc(x) + "</option>"; }).join("") + "</select></div></div>" +
      '<div class="field"><label for="pModel">Model</label><select class="select" id="pModel"><option value="">Server default (' + esc(m.default_model) + ")</option>" + models.map(function (x) { return "<option" + (x === p.model ? " selected" : "") + ">" + esc(x) + "</option>"; }).join("") + "</select></div>" +
      '<button class="btn primary">Save preferences</button></form></section>' +

      '<section class="card"><div class="card-head"><h3>' + icon("lock") + 'Change password</h3></div><form class="card-pad" id="pwForm">' +
      '<div class="field"><label for="pwCur">Current password</label><input class="input" type="password" id="pwCur" autocomplete="current-password"></div>' +
      '<div class="field"><label for="pwNew">New password</label><input class="input" type="password" id="pwNew" autocomplete="new-password" minlength="6"></div>' +
      '<button class="btn">Update password</button></form></section>' +

      '<section class="card"><div class="card-head"><h3>' + icon("user") + 'Account</h3></div><div class="card-pad"><p style="margin:0 0 6px"><b>' + esc(S.user.name) + "</b></p><p class=\"muted\" style=\"margin:0 0 14px\">" + esc(S.user.email) + " · " + esc(S.user.role) + "</p>" +
      '<button class="btn danger" id="logout2">' + icon("logout", "sm") + "Sign out</button></div></section></div>";

    $("#testBtn").addEventListener("click", function () { route(); });
    $("#prefsForm").addEventListener("submit", async function (e) {
      e.preventDefault();
      try {
        S.user = await api("PUT", "/api/auth/me", { name: $("#pName").value, mode: $("#pMode").value, length: $("#pLen").value, language: $("#pLang").value, model: $("#pModel").value });
        setUserCard(); toast("Preferences saved", "ok");
      } catch (err) { toast(err.message, "bad"); }
    });
    $("#pwForm").addEventListener("submit", async function (e) {
      e.preventDefault();
      try {
        await api("PUT", "/api/auth/me", { current_password: $("#pwCur").value, new_password: $("#pwNew").value });
        $("#pwCur").value = $("#pwNew").value = ""; toast("Password updated", "ok");
      } catch (err) { toast(err.message, "bad"); }
    });
    $("#logout2").addEventListener("click", logout);
  }

  // ------------------------------------------------------------------ global wiring
  async function logout() {
    await POST("/api/auth/logout").catch(function () {});
    location.href = "/login";
  }
  function setThemeIcon() {
    var dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    $("#themeBtn").innerHTML = icon(dark ? "sun" : "moon");
  }

  async function boot() {
    hydrateIcons();
    setUserCard();
    setThemeIcon();
    $("#themeBtn").addEventListener("click", function () {
      var dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("dm-theme", document.documentElement.dataset.theme); } catch (e) { /* storage blocked */ }
      setThemeIcon();
    });
    $("#menuBtn").addEventListener("click", function () { $("#sidebar").classList.toggle("open"); });
    $("#logoutBtn").addEventListener("click", logout);
    $("#ollamaPill").addEventListener("click", function () { location.hash = "#/settings"; });
    $("#searchForm").addEventListener("submit", function (e) {
      e.preventDefault();
      docFilter.q = $("#searchInput").value.trim();
      if (location.hash === "#/documents") route(); else location.hash = "#/documents";
    });
    S.meta = await GET("/api/meta");
    GET("/api/documents").then(function (d) { $("#navDocs").textContent = d.length; }).catch(function () {});
    checkHealth();
    setInterval(checkHealth, 60000);
    window.addEventListener("hashchange", route);
    route();
  }
  boot().catch(function (e) { $("#view").innerHTML = '<div class="card card-pad">' + esc(e.message) + "</div>"; });
})();
