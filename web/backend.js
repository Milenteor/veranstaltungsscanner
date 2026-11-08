/* Veranstaltungsscanner Steiermark: eigenständiger Betrieb (Weg A)
   Stellt der App dieselbe Schnittstelle bereit wie die Claude-Artefakt-Laufzeit (window.claude.use),
   gebaut auf Supabase. Die App selbst bleibt unverändert lauffähig im Artefakt.
   Schnittstelle, die die App nutzt:
     db.doc(p).get()/set()/delete(), db.collection(p).get(), .orderBy('ts','desc').limit(n).get(), .onSnapshot(cb,err)
     user.id(), user.canEdit(), sample.json(prompt,opts) */
(function () {
  'use strict';
  var C = window.VS_CONFIG || {};
  window.VS_SELF = true;
  window.VS_TIME = C.scanTimeLabel || '9:30 Uhr';
  var configured = !!(C.supabaseUrl && C.supabaseAnonKey && window.supabase && window.supabase.createClient);
  var sb = configured ? window.supabase.createClient(C.supabaseUrl, C.supabaseAnonKey, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false, storageKey: 'vs-auth' }
  }) : null;

  var state = { session: null, uid: null, email: null, member: false, admin: false, checked: false };
  var readyResolve, ready = new Promise(function (r) { readyResolve = r; });

  function errOf(e) {
    var m = (e && (e.message || e.error_description)) || String(e || '');
    var code = (e && e.code) || '';
    if (code === '42501' || /row-level security|permission/i.test(m)) return { code: 'permission_denied', message: m };
    if (/fetch|network|Failed to fetch|timeout|Load failed/i.test(m)) return { code: 'unavailable', message: m };
    return { code: 'error', message: m };
  }
  function colOf(path) { var i = path.lastIndexOf('/'); return i < 0 ? '' : path.slice(0, i); }
  function idOf(path) { var i = path.lastIndexOf('/'); return path.slice(i + 1); }
  function snapDoc(path, data) { return { id: idOf(path), exists: data !== undefined && data !== null, data: function () { return data == null ? undefined : JSON.parse(JSON.stringify(data)); } }; }

  // ---------------------------------------------------------------- Dokument-Speicher
  var hooks = [];
  function onWrite(fn) { hooks.push(fn); }
  function docRef(path) {
    return {
      id: idOf(path), path: path,
      get: async function () {
        var r = await sb.from('docs').select('data').eq('path', path).maybeSingle();
        if (r.error) throw errOf(r.error);
        return snapDoc(path, r.data ? r.data.data : undefined);
      },
      set: async function (obj) {
        var r = await sb.from('docs').upsert({ path: path, data: obj }, { onConflict: 'path' });
        if (r.error) throw errOf(r.error);
        hooks.forEach(function (h) { try { h(path, obj); } catch (_) {} });
      },
      update: async function (obj) {
        var cur = await this.get(); var d = Object.assign({}, cur.exists ? cur.data() : {}, obj);
        return this.set(d);
      },
      delete: async function () {
        var r = await sb.from('docs').delete().eq('path', path);
        if (r.error) throw errOf(r.error);
      }
    };
  }
  function query(col, opts) {
    opts = opts || {};
    var q = {
      doc: function (id) { return docRef(col + '/' + id); },
      orderBy: function (f, dir) { return query(col, Object.assign({}, opts, { order: [f, dir || 'asc'] })); },
      limit: function (n) { return query(col, Object.assign({}, opts, { limit: n })); },
      where: function (f, op, v) { return query(col, Object.assign({}, opts, { where: (opts.where || []).concat([[f, op, v]]) })); },
      get: async function () {
        var b = sb.from('docs').select('path,data').eq('col', col);
        if (opts.order && opts.order[0] === 'ts') b = b.order('ts', { ascending: opts.order[1] !== 'desc', nullsFirst: false });
        b = b.limit(Math.min(opts.limit || 1000, 1000));
        var r = await b;
        if (r.error) throw errOf(r.error);
        var rows = (r.data || []).map(function (x) { return snapDoc(x.path, x.data); });
        (opts.where || []).forEach(function (w) {
          rows = rows.filter(function (d) { var v = (d.data() || {})[w[0]];
            switch (w[1]) { case '==': return v === w[2]; case '!=': return v !== w[2]; case '<': return v < w[2]; case '<=': return v <= w[2];
              case '>': return v > w[2]; case '>=': return v >= w[2]; case 'in': return (w[2] || []).indexOf(v) >= 0;
              case 'array-contains': return Array.isArray(v) && v.indexOf(w[2]) >= 0; default: return true; } });
        });
        if (opts.order && opts.order[0] !== 'ts') {
          var f = opts.order[0], s = opts.order[1] === 'desc' ? -1 : 1;
          rows.sort(function (a, b) { var x = (a.data() || {})[f], y = (b.data() || {})[f]; return x < y ? -s : x > y ? s : 0; });
        }
        return { docs: rows, size: rows.length, empty: !rows.length };
      },
      onSnapshot: function (cb, errcb) {
        var alive = true, t = null, self = this;
        function pull() { if (!alive) return; self.get().then(function (s) { if (alive) cb(s); }, function (e) { if (errcb) errcb(e); }); }
        function soon() { clearTimeout(t); t = setTimeout(pull, 250); }
        pull();
        var ch = sb.channel('vs-' + col.replace(/[^\w-]/g, '_') + '-' + Math.random().toString(36).slice(2, 7))
          .on('postgres_changes', { event: '*', schema: 'public', table: 'docs', filter: 'col=eq.' + col }, soon)
          .subscribe();
        // Sicherheitsnetz, falls die Live-Verbindung im Hintergrund schläft (iOS)
        var iv = setInterval(function () { if (document.visibilityState === 'visible') pull(); }, 120000);
        function vis() { if (document.visibilityState === 'visible') soon(); }
        document.addEventListener('visibilitychange', vis);
        return function () { alive = false; clearInterval(iv); document.removeEventListener('visibilitychange', vis); try { sb.removeChannel(ch); } catch (_) {} };
      }
    };
    return q;
  }
  var db = { doc: docRef, collection: function (p) { return query(p); } };

  var userNs = {
    id: async function () { return state.uid; },
    me: async function () { return { id: state.uid, name: '', guest: false }; },
    isOwner: function () { return state.admin; },
    canEdit: async function () { return state.admin; },
    can: function (n) { return n === 'data.write' ? state.member : null; },
    profiles: async function () { return {}; }
  };

  // ---------------------------------------------------------------- KI über eigene Edge Function
  async function callFn(name, body) {
    var s = (await sb.auth.getSession()).data.session;
    var r = await fetch(C.supabaseUrl + '/functions/v1/' + name, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (s ? s.access_token : ''), 'apikey': C.supabaseAnonKey },
      body: JSON.stringify(body || {})
    });
    var j = null; try { j = await r.json(); } catch (_) {}
    if (!r.ok) throw { code: (j && j.code) || (r.status === 429 ? 'rate_limited' : 'error'), message: (j && j.message) || ('HTTP ' + r.status) };
    return j;
  }
  function sampleFn(input, opts) {
    return callFn('ask', { input: input, tier: (opts && opts.modelTier) || 'quick', json: false }).then(function (j) { return { text: j.text || '', truncated: !!j.truncated }; });
  }
  sampleFn.json = function (input, opts) {
    return callFn('ask', { input: input, tier: (opts && opts.modelTier) || 'quick', json: true }).then(function (j) { return j.json; });
  };
  sampleFn.limits = async function () { return { images: false }; };

  // ---------------------------------------------------------------- window.claude-Ersatz
  window.claude = {
    use: function (name) {
      if (!configured) return Promise.resolve(null);
      if (name === 'db') return ready.then(function () { return state.member ? db : null; });
      if (name === 'user') return ready.then(function () { return state.member ? userNs : null; });
      if (name === 'sample') return ready.then(function () { return state.member ? sampleFn : null; });
      return Promise.resolve(null);
    }
  };

  // ---------------------------------------------------------------- Anmeldung mit Code per Mail
  async function afterLogin(session) {
    state.session = session; state.uid = session.user.id; state.email = session.user.email || '';
    try {
      var a = await sb.rpc('is_member'); var b = await sb.rpc('is_admin');
      state.member = !!a.data; state.admin = !!b.data;
    } catch (_) {}
    state.checked = true;
    if (!state.member) { sheet('nomember'); return; }
    closeSheet();
    readyResolve();
    ensureIcsToken();
    refreshPushSub(false);
  }
  if (configured) {
    sb.auth.getSession().then(function (r) {
      var s = r.data && r.data.session;
      if (s) afterLogin(s);
      else if (!flag('vs_later')) setTimeout(function () { sheet('email'); }, 400);
    });
    sb.auth.onAuthStateChange(function (ev, s) { if (ev === 'SIGNED_OUT') { state.member = false; state.uid = null; } });
  }
  function flag(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } }

  var css = '#vsSheet{position:fixed;inset:0;z-index:9999;background:rgba(20,20,19,.45);display:flex;align-items:flex-end;justify-content:center;padding:0 0 env(safe-area-inset-bottom,0)}' +
    '#vsSheet .in{background:#fff;width:100%;max-width:440px;border-radius:18px 18px 0 0;padding:22px 20px 26px;box-shadow:0 -6px 30px rgba(0,0,0,.15);font:15px/1.45 "Inter Tight",-apple-system,sans-serif;color:#141413}' +
    '@media (min-width:600px){#vsSheet{align-items:center}#vsSheet .in{border-radius:18px}}' +
    '#vsSheet h2{margin:0 0 6px;font-size:20px}#vsSheet p{margin:6px 0 12px;color:#4a4a46}#vsSheet input{width:100%;box-sizing:border-box;font:inherit;font-size:17px;padding:12px 14px;border:1.5px solid #c9c7bd;border-radius:12px;margin:4px 0 12px}' +
    '#vsSheet input.code{letter-spacing:.3em;text-align:center;font-size:22px}#vsSheet .row{display:flex;gap:10px;flex-wrap:wrap}' +
    '#vsSheet button{font:inherit;font-weight:600;padding:12px 16px;border-radius:12px;border:0;cursor:pointer;touch-action:manipulation}#vsSheet .pri{background:#CB1967;color:#fff;flex:1}#vsSheet .sec{background:#f0eee6;color:#141413}' +
    '#vsSheet .err{color:#b42318;font-size:14px;min-height:1.2em;margin:0 0 6px}';
  function closeSheet() { var e = document.getElementById('vsSheet'); if (e) e.remove(); }
  var pendingEmail = '';
  function sheet(step, msg) {
    closeSheet();
    if (!document.getElementById('vsCss')) { var st = document.createElement('style'); st.id = 'vsCss'; st.textContent = css; document.head.appendChild(st); }
    var w = document.createElement('div'); w.id = 'vsSheet'; w.setAttribute('role', 'dialog'); w.setAttribute('aria-modal', 'true');
    var h = '';
    if (step === 'email') h = '<h2>Anmelden</h2><p>Deine Mail-Adresse. Du bekommst einen 6-stelligen Code, kein Passwort nötig.</p>' +
      '<input id="vsMail" type="email" inputmode="email" autocomplete="email" placeholder="name@beispiel.at"><div class="err" id="vsErr">' + (msg || '') + '</div>' +
      '<div class="row"><button class="pri" id="vsSend">Code schicken</button><button class="sec" id="vsLater">Später</button></div>';
    else if (step === 'code') h = '<h2>Code eingeben</h2><p>Wir haben einen Code an <b>' + pendingEmail.replace(/[<>&"]/g, '') + '</b> geschickt. Er gilt eine Stunde.</p>' +
      '<input id="vsCode" class="code" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="000000"><div class="err" id="vsErr">' + (msg || '') + '</div>' +
      '<div class="row"><button class="pri" id="vsOk">Anmelden</button><button class="sec" id="vsBack">Andere Adresse</button></div>';
    else if (step === 'nomember') h = '<h2>Noch kein Zugang</h2><p>Du bist als <b>' + String(state.email).replace(/[<>&"]/g, '') + '</b> angemeldet, aber diese Adresse ist nicht freigeschaltet. Bitte melde dich bei der Person, die die App verwaltet.</p>' +
      '<div class="row"><button class="sec" id="vsOut">Abmelden</button><button class="sec" id="vsLater">Ohne Anmeldung weiter</button></div>';
    w.innerHTML = '<div class="in">' + h + '</div>';
    document.body.appendChild(w);
    var $ = function (id) { return document.getElementById(id); };
    var err = function (t) { var e = $('vsErr'); if (e) e.textContent = t; };
    if ($('vsMail')) { $('vsMail').value = pendingEmail || ''; setTimeout(function () { $('vsMail').focus(); }, 50);
      $('vsMail').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('vsSend').click(); }); }
    if ($('vsCode')) { setTimeout(function () { $('vsCode').focus(); }, 50);
      $('vsCode').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('vsOk').click(); }); }
    if ($('vsLater')) $('vsLater').onclick = function () { flag('vs_later', '1'); closeSheet(); };
    if ($('vsBack')) $('vsBack').onclick = function () { sheet('email'); };
    if ($('vsOut')) $('vsOut').onclick = function () { sb.auth.signOut().then(function () { sheet('email'); }); };
    if ($('vsSend')) $('vsSend').onclick = async function () {
      var m = ($('vsMail').value || '').trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(m)) { err('Bitte eine gültige Mail-Adresse eingeben.'); return; }
      this.disabled = true; err('');
      var r = await sb.auth.signInWithOtp({ email: m, options: { shouldCreateUser: true } });
      this.disabled = false;
      if (r.error) { err(/rate|seconds/i.test(r.error.message) ? 'Bitte kurz warten und noch einmal versuchen.' : 'Code konnte nicht geschickt werden.'); return; }
      pendingEmail = m; sheet('code');
    };
    if ($('vsOk')) $('vsOk').onclick = async function () {
      var c = ($('vsCode').value || '').replace(/\D/g, '');
      if (c.length < 6) { err('Bitte den Code aus der Mail eingeben.'); return; }
      this.disabled = true; err('');
      var r = await sb.auth.verifyOtp({ email: pendingEmail, token: c, type: 'email' });
      this.disabled = false;
      if (r.error || !r.data.session) { err('Der Code stimmt nicht oder ist abgelaufen.'); return; }
      afterLogin(r.data.session);
    };
  }

  // ---------------------------------------------------------------- Kalender-Abo (webcal)
  function rnd(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return Array.prototype.map.call(a, function (x) { return ('0' + x.toString(16)).slice(-2); }).join(''); }
  var icsTok = null;
  async function ensureIcsToken() {
    try {
      var p = 'data/users/' + state.uid + '/icstok'; var d = await docRef(p).get();
      if (d.exists && d.data().token) icsTok = d.data().token; else { icsTok = rnd(20); await docRef(p).set({ token: icsTok, ts: new Date().toISOString() }); }
      rerenderEinst();
    } catch (_) {}
  }
  function icsUrl(scheme) { if (!icsTok) return ''; var u = C.supabaseUrl.replace(/^https?:\/\//, '') + '/functions/v1/ics?t=' + icsTok; return (scheme || 'https') + '://' + u; }

  // Zusagen als kleine Liste ablegen, aus der das Kalender-Abo gebaut wird
  var feedT = null;
  function scheduleFeed() { clearTimeout(feedT); feedT = setTimeout(writeFeed, 1500); }
  function writeFeed() {
    try {
      if (!state.member || typeof EVENTS === 'undefined' || typeof Store === 'undefined') return;
      var go = {}, keys = Object.keys(Store.L.u || {}).filter(function (k) { return k.indexOf('live_') === 0; });
      keys.forEach(function (k) { var st = (Store.L.u[k] || {}).st || {}; Object.keys(st).forEach(function (id) { if (st[id] && st[id].s === 'go') go[id] = 1; }); });
      var byId = {}; EVENTS.forEach(function (e) { byId[e.id] = e; });
      keys.forEach(function (k) { ((Store.L.u[k] || {}).own || []).forEach(function (e) { if (e && e.id) byId[e.id] = byId[e.id] || e; }); });
      var out = Object.keys(go).map(function (id) { var e = byId[id]; if (!e) return null;
        var src = Array.isArray(e.src) && e.src[0] && e.src[0].u ? String(e.src[0].u).slice(0, 500) : '';
        return { id: id, d: e.d, d2: e.d2 || null, s: e.s || null, e: e.e || null, title: String(e.title || '').slice(0, 200), venue: String(e.venue || '').slice(0, 200),
          gem: e.gem || '', org: String(e.org || '').slice(0, 120), sum: String(e.sum || '').slice(0, 600), url: src, online: e.online || null }; }).filter(Boolean)
        .sort(function (a, b) { return a.d < b.d ? -1 : 1; }).slice(-400);
      docRef('data/users/' + state.uid + '/calfeed').set({ ts: new Date().toISOString(), events: out }).catch(function () {});
    } catch (_) {}
  }
  onWrite(function (path) { if (state.uid && path.indexOf('data/users/' + state.uid + '/live_') === 0) scheduleFeed(); });

  // ---------------------------------------------------------------- Web Push
  function b64u(s) { var p = '='.repeat((4 - s.length % 4) % 4); var b = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')); var a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a; }
  var standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
  var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  function pushSupported() { return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && !!C.vapidPublicKey; }
  async function refreshPushSub(ask) {
    if (!pushSupported() || !state.uid) return 'unsupported';
    try {
      var perm = Notification.permission;
      if (perm === 'default' && ask) perm = await Notification.requestPermission();
      if (perm !== 'granted') return perm;
      var reg = await navigator.serviceWorker.ready;
      var sub = await reg.pushManager.getSubscription();
      if (!sub) { if (!ask) return 'none'; sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64u(C.vapidPublicKey) }); }
      var p = 'data/users/' + state.uid + '/websub'; var cur = await docRef(p).get(); var list = cur.exists ? (cur.data().subs || []) : [];
      var j = sub.toJSON(); if (!list.some(function (x) { return x.endpoint === j.endpoint; })) { list.push({ endpoint: j.endpoint, keys: j.keys, ua: navigator.userAgent.slice(0, 120), ts: new Date().toISOString() }); }
      list = list.slice(-5);
      await docRef(p).set({ subs: list, ts: new Date().toISOString() });
      return 'granted';
    } catch (e) { return 'error'; }
  }
  // Erlaubnis muss direkt aus dem Antippen kommen (iOS), darum hier im Capture-Schritt
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (t && t.id === 'pPush' && t.checked && state.member) {
      if (isIOS && !standalone) { toastSoon('Auf dem iPhone kommen Mitteilungen nur, wenn die App über „Zum Home-Bildschirm“ geöffnet ist.'); return; }
      refreshPushSub(true).then(function (r) {
        if (r === 'denied') toastSoon('Mitteilungen sind in den iPhone-Einstellungen für diese App ausgeschaltet.');
        else if (r === 'granted') toastSoon('Mitteilungen erlaubt');
      });
    }
  }, true);
  function toastSoon(t) { setTimeout(function () { try { if (typeof toast === 'function') toast(t); } catch (_) {} }, 400); }

  // ---------------------------------------------------------------- Neue Suche starten
  async function scanNow(btn) {
    if (!state.member) { sheet('email'); return; }
    if (btn) btn.disabled = true;
    try {
      var r = await callFn('scan-now', {});
      var el = document.getElementById('vsScanMsg');
      if (el) el.textContent = r.message || 'Gestartet. Dauert etwa 10 bis 20 Minuten; du bekommst eine Mitteilung, wenn sie an ist.';
    } catch (e) {
      var el2 = document.getElementById('vsScanMsg');
      if (el2) el2.textContent = e.code === 'rate_limited' ? (e.message || 'Es läuft gerade schon eine Suche.') : 'Konnte die Suche nicht starten. Später noch einmal versuchen.';
      if (btn) btn.disabled = false;
    }
  }
  // Link aus „＋ Termin“ sofort lesen lassen statt bis zum nächsten Lauf zu warten
  onWrite(function (path, obj) {
    if (path.indexOf('linkq/') === 0 && obj && obj.u) {
      callFn('fetch-link', { h: obj.h, u: obj.u }).then(function () {
        try { if (typeof checkPend === 'function') checkPend(); } catch (_) {}
      }).catch(function () {});
    }
  });

  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-vs]'); if (!b) return;
    var a = b.getAttribute('data-vs');
    e.preventDefault(); e.stopPropagation();
    if (a === 'scan') scanNow(b);
    else if (a === 'login') sheet('email');
    else if (a === 'logout') sb.auth.signOut().then(function () { try { localStorage.removeItem('vs_later'); } catch (_) {} location.reload(); });
    else if (a === 'copyics') { var u = icsUrl('https'); if (navigator.clipboard) navigator.clipboard.writeText(u).then(function () { toastSoon('Adresse kopiert'); }); }
    else if (a === 'pushtest') { refreshPushSub(true).then(function (r) { if (r !== 'granted') { toastSoon('Erst Mitteilungen erlauben'); return; }
      callFn('scan-now', { mode: 'pushtest' }).then(function () { toastSoon('Test-Mitteilung kommt in etwa einer Minute'); }, function (e) { toastSoon(e && e.code === 'rate_limited' ? 'Bitte ein paar Minuten warten' : 'Test nicht möglich'); }); }); }
  }, true);

  function rerenderEinst() { try { if (typeof S !== 'undefined' && S.view === 'einst' && typeof renderEinst === 'function') renderEinst(); } catch (_) {} }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  // ---------------------------------------------------------------- Bausteine, die die App einbindet
  window.VS = {
    state: state,
    scanNote: function () {
      return 'Automatisch gesucht wird um ' + (window.VS_TIME || '') + ', ' + (typeof rhyLabel === 'function' ? rhyLabel() : 'einmal pro Woche') + '. Dieser Knopf holt den neuesten fertigen Lauf; eine ganz neue Suche startest du unten.';
    },
    scanBtnHtml: function () {
      if (!state.member) return '';
      return '<div style="margin:12px 0;padding:10px 12px;border-left:5px solid var(--yellow,#F6D000);background:#fff8cc;border-radius:0 8px 8px 0"><b>Ganz neu im Netz suchen?</b><br><span class="small">Liest alle Quellen jetzt neu ein. Dauert etwa 10 bis 20 Minuten. Danach kommt eine Mitteilung, wenn du sie eingeschaltet hast.</span>' +
        '<div class="acts" style="margin-top:8px"><button class="btn sm" data-vs="scan">Neue Suche starten</button></div><p class="xs muted" id="vsScanMsg" style="margin:6px 0 0"></p></div>';
    },
    einstHtml: function () {
      var h = '<h3>Konto</h3><div class="pushbox">';
      if (!configured) h += '<p class="small">Die App ist noch nicht mit der Datenbank verbunden (config.js).</p>';
      else if (!state.uid) h += '<p class="small">Nicht angemeldet. Ohne Anmeldung bleiben deine Klicks nur auf diesem Gerät, Mitteilungen und Kalender-Abo gehen nicht.</p><div class="acts"><button class="btn sm pri" data-vs="login">Anmelden</button></div>';
      else h += '<p class="small">Angemeldet als <b>' + esc(state.email) + '</b>' + (state.admin ? ' (verwaltet die App)' : '') + '. Deine Zusagen und Einstellungen liegen auf allen deinen Geräten gleich.</p><div class="acts"><button class="btn sm" data-vs="logout">Abmelden</button></div>';
      h += '</div>';
      if (state.member) {
        var https = icsUrl('https'), webcal = icsUrl('webcal');
        h += '<h3>Kalender-Abo: Zusagen automatisch im Kalender</h3><div class="pushbox">';
        if (!icsTok) h += '<p class="small">Wird vorbereitet …</p>';
        else h += '<p class="small">Einmal einrichten, danach erscheint jede Zusage von selbst in deinem Kalender, und abgesagte Termine verschwinden wieder. iPhone und Outlook holen das Abo alle paar Stunden neu.</p>' +
          '<div class="acts"><a class="btn sm pri" href="' + esc(webcal) + '">📅 iPhone-Kalender abonnieren</a>' +
          '<a class="btn sm" target="_blank" rel="noopener" href="https://outlook.office.com/calendar/0/addfromweb?url=' + encodeURIComponent(https) + '&name=' + encodeURIComponent('NEOS Termine') + '">📅 Outlook abonnieren</a>' +
          '<button class="btn sm" data-vs="copyics">Adresse kopieren</button></div>' +
          '<p class="xs muted" style="margin:8px 0 0">Die Adresse ist persönlich. Wer sie hat, sieht deine Zusagen. Nicht weitergeben.</p>';
        h += '</div>';
        h += '<h3>Mitteilungen auf diesem Gerät</h3><div class="pushbox">';
        if (!pushSupported()) h += '<p class="small">Dieses Gerät oder dieser Browser kann keine Mitteilungen von Web-Apps empfangen.</p>';
        else if (isIOS && !standalone) h += '<p class="small"><b>Auf dem iPhone:</b> In Safari unten auf Teilen tippen, dann <b>„Zum Home-Bildschirm“</b>. Die App dann über das neue Symbol öffnen und hier Mitteilungen einschalten. Aus Safari heraus erlaubt Apple keine Mitteilungen.</p>';
        else h += '<p class="small">Stand: <b>' + ({ granted: 'erlaubt', denied: 'blockiert (in den Geräte-Einstellungen änderbar)', 'default': 'noch nicht gefragt' }[Notification.permission] || Notification.permission) + '</b>. Eingeschaltet wird oben unter „Aufs Handy“. Mitteilungen kommen nach dem Suchlauf um ' + esc(window.VS_TIME || '') + ' und nie zwischen 21 und 8 Uhr.</p><div class="acts"><button class="btn sm" data-vs="pushtest">Test-Mitteilung schicken</button></div>';
        h += '</div>';
      }
      return h;
    },
    faq: {
      'Wie bekomme ich Benachrichtigungen aufs Handy?':
        '<ol class="small"><li><b>iPhone:</b> Die App in Safari öffnen, unten auf Teilen tippen, <b>„Zum Home-Bildschirm“</b>. Ab jetzt die App über dieses Symbol öffnen (Mitteilungen gehen auf dem iPhone nur so, ab iOS 16.4).</li>' +
        '<li>Anmelden mit deiner Mail-Adresse und dem Code aus der Mail.</li><li><b>Einstellungen › Aufs Handy</b> einschalten und die Rückfrage des iPhones mit „Erlauben“ beantworten.</li>' +
        '<li>Mit <b>Test-Mitteilung schicken</b> prüfen, ob es ankommt.</li></ol><p class="small">Mitteilungen kommen nach jedem Suchlauf (um ' + esc(window.VS_TIME || '') + '), wenn es etwas Neues gibt, eine Anmeldefrist abläuft oder morgen eine Zusage ansteht. Android und Computer funktionieren genauso, dort ohne den Schritt mit dem Home-Bildschirm.</p>',
      'Wie kommt ein Termin in meinen Outlook- oder iPhone-Kalender?':
        '<p class="small"><b>Am einfachsten, einmal einrichten:</b> Einstellungen › <b>Kalender-Abo</b>. Auf dem iPhone „iPhone-Kalender abonnieren“ antippen und bestätigen, in Outlook „Outlook abonnieren“. Ab dann erscheint jede Zusage von selbst im Kalender. Das Abo wird alle paar Stunden aktualisiert.</p>' +
        '<p class="small"><b>Einzeln:</b> Bei jedem Termin stehen „📅 Outlook“, „📅 Google“ und die .ics-Datei. Ein Tippen öffnet den fertig ausgefüllten Termin.</p>' +
        '<p class="small"><b>Später in Microsoft 365:</b> Dort schreibt ein Power-Automate-Ablauf Zusagen direkt in den Dienstkalender. Das Abo hier ist die Lösung bis dahin.</p>',
      'Warum startet „Suche jetzt“ keinen neuen Lauf?': null,
      'Kann ich die App aufs iPhone laden?':
        '<p class="small">Ja. In Safari öffnen, Teilen, <b>„Zum Home-Bildschirm“</b>. Die App startet dann wie eine eigene App im Vollbild, mit Mitteilungen. Ein Eintrag im App Store ist dafür nicht nötig.</p>',
      'Wie sieht es mit dem Datenschutz in dieser App aus?':
        '<ul class="small"><li><b>Zugang:</b> Nur freigeschaltete Mail-Adressen sehen Termine und Daten. Anmeldung mit Einmal-Code.</li>' +
        '<li><b>Deine Klicks und Einstellungen</b> liegen in deinem privaten Bereich der Datenbank (Supabase, Rechenzentrum in der EU). Andere Mitglieder sehen sie nicht.</li>' +
        '<li><b>Kalender:</b> Die App liest deinen Kalender nicht. Das Kalender-Abo enthält nur deine Zusagen.</li>' +
        '<li><b>KI:</b> Für Suchfragen und das Taggen gehen Termintexte an die Anthropic-API. Über die API geschickte Daten nutzt Anthropic laut eigenen Bedingungen nicht zum Training.</li>' +
        '<li><b>Mitteilungen</b> laufen über den Push-Dienst deines Geräts (Apple, Google, Mozilla), Inhalt verschlüsselt.</li>' +
        '<li>Keine Telefonnummern, keine Werbe-Tracker.</li></ul>'
    },
    scanNow: scanNow, refreshPushSub: refreshPushSub
  };

  // ---------------------------------------------------------------- Service Worker
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('sw.js').catch(function () {}); });
    navigator.serviceWorker && navigator.serviceWorker.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'open' && e.data.view && typeof setView === 'function') { try { setView(e.data.view); } catch (_) {} }
    });
  }
})();
