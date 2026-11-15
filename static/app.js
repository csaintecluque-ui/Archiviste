/* ═══════════════════════════════════════════════════════════
   Archiviste — interface
   Fichiers · Tri intelligent · Discussion · Agents · Prompts
   ═══════════════════════════════════════════════════════════ */
'use strict';

// ───────────────────────── Utilitaires ─────────────────────────
const TOKEN = document.querySelector('meta[name="archiviste-token"]').content;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const enc = encodeURIComponent;
const basename = (p) => String(p || '').replace(/\/+$/, '').split('/').pop() || p;
const dirname = (p) => { const s = String(p || '').replace(/\/+$/, ''); const i = s.lastIndexOf('/'); return i > 0 ? s.slice(0, i) : '/'; };
const joinPath = (a, b) => (a.endsWith('/') ? a : a + '/') + b;
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const tildify = (p) => (S.home && p && (p === S.home || p.startsWith(S.home + '/')) ? '~' + p.slice(S.home.length) : p || '');

const ICONS = {
  folder: 'M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.2h7.5A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z',
  file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5',
  sparkles: 'M12 3l1.9 4.6 4.6 1.9-4.6 1.9L12 16l-1.9-4.6-4.6-1.9 4.6-1.9zM19 15.5l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z',
  chat: 'M20.5 11.5a8 8 0 0 1-11.7 7.1L4 19.8l1.2-4.4A8 8 0 1 1 20.5 11.5z',
  bot: 'M12 3.5V7M7.5 7h9A3.5 3.5 0 0 1 20 10.5v5a3.5 3.5 0 0 1-3.5 3.5h-9A3.5 3.5 0 0 1 4 15.5v-5A3.5 3.5 0 0 1 7.5 7zM9.5 12.5v1M14.5 12.5v1M2 12v3M22 12v3',
  prompt: 'M4 5h16v11H9.5L5 20v-4H4zM8 9h8M8 12.5h5',
  trash: 'M4 6.5h16M9 6.5v-2h6v2M6.5 6.5l.9 13a1.5 1.5 0 0 0 1.5 1.4h6.2a1.5 1.5 0 0 0 1.5-1.4l.9-13M10 10.5v6M14 10.5v6',
  sliders: 'M4 7h9M17 7h3M15 5v4M4 12h3M11 12h9M9 10v4M4 17h11M19 17h1M17 15v4',
  upload: 'M12 15V4M7.5 8.5L12 4l4.5 4.5M5 15v3.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V15',
  download: 'M12 4v11M7.5 10.5L12 15l4.5-4.5M5 15v3.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V15',
  plus: 'M12 5v14M5 12h14',
  folderPlus: 'M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.2h7.5A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5zM12 10.5v6M9 13.5h6',
  filePlus: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M12 11.5v6M9 14.5h6',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM20 20l-4.8-4.8',
  up: 'M12 19V5M6 11l6-6 6 6',
  down: 'M12 5v14M6 13l6 6 6-6',
  refresh: 'M20 12a8 8 0 1 1-2.6-5.9M20 4v5h-5',
  pencil: 'M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3zM14.5 7.5l3 3',
  move: 'M4 12h12M12 7l5 5-5 5M20 5v14',
  copy: 'M9 9h10.5v10.5H9zM5 15V4.5h10.5',
  x: 'M6 6l12 12M18 6L6 18',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  send: 'M21 3L10 14M21 3l-6.5 18-4.5-7-7-4.5z',
  stop: 'M7 7h10v10H7z',
  clip: 'M20 11.5l-8 8a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7L9.7 17.2a1.7 1.7 0 0 1-2.4-2.4l7.6-7.6',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  home: 'M3.5 11L12 4l8.5 7M6 9.5V20h12V9.5',
  undo: 'M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
  star: 'M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z',
  external: 'M14 4h6v6M20 4l-9 9M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10',
  save: 'M5 3.5h11l3.5 3.5v13H5zM8 3.5V8h7V3.5M8 20.5V14h8v6.5',
  wand: 'M15 4V2M15 10V8M11 6h2M17 6h2M4 20l9.5-9.5M12.5 9.5l2 2',
  play: 'M7 4.5l12.5 7.5L7 19.5z',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5.5M12 7.5v.5',
  alert: 'M12 9v4.5M12 17v.5M10.3 4.2L2.6 17.6A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-2.9L13.7 4.2a2 2 0 0 0-3.4 0z',
  panel: 'M4 5h16v14H4zM15 5v14',
  quill: 'M20 4C13 4.5 7.5 9 6 16.5L4.5 20 8 18.5C15.5 17 19.5 11 20 4zM6 16.5l5-5M9.5 14.5h4.5M12 11h5',
  cpu: 'M7 7h10v10H7zM10 10h4v4h-4zM10 2.5v3M14 2.5v3M10 18.5v3M14 18.5v3M2.5 10h3M2.5 14h3M18.5 10h3M18.5 14h3',
  image: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M8 17l3-3.5 2 2 1.5-1.5L17 17M9.5 10.5h.01',
  video: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M10 11.5v5l4-2.5z',
  music: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M11 17.5v-6l4-1M11 17.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z',
  archive: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M10 5h1M10 8h1M10 11h1M9.5 14h2v3h-2z',
  code: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M10 12l-2 2 2 2M14 12l2 2-2 2',
  doc: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M8.5 12h7M8.5 15h7M8.5 18h4',
  sheet: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M8 12h8v6H8zM8 15h8M12 12v6',
  app: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6v5H9z',
};
const KIND_ICON = { image: 'image', video: 'video', audio: 'music', archive: 'archive', code: 'code', doc: 'doc',
  text: 'doc', book: 'doc', sheet: 'sheet', slides: 'doc', app: 'app' };
function ic(name, cls = '') {
  const d = ICONS[name] || ICONS.file;
  const sw = name === 'more' ? ' style="stroke-width:3.2"' : '';
  return `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true"${sw}><path d="${d}"/></svg>`;
}
function kindColor(e) {
  if (e.dir) return 'var(--accent)';
  if (e.ext === 'pdf') return 'var(--k-pdf)';
  return `var(--k-${e.kind || 'file'})`;
}
function fileIcon(e) {
  if (e.dir) return `<span class="ficon folder">${ic('folder')}</span>`;
  return `<span class="ficon" style="color:${kindColor(e)}">${ic(KIND_ICON[e.kind] || 'file')}</span>`;
}

function fmtSize(n) {
  if (n === null || n === undefined) return '';
  if (n < 1024) return `${n} o`;
  const u = ['Ko', 'Mo', 'Go', 'To'];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return `${n < 10 ? n.toFixed(1).replace('.', ',') : Math.round(n)} ${u[i]}`;
}
const DF_DAY = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
const DF_TIME = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });
const DF_FULL = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'long', timeStyle: 'short' });
function toDate(ts) { return typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts); }
function fmtDate(ts) {
  if (!ts) return '';
  const d = toDate(ts);
  const now = new Date();
  const day0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (d.getTime() >= day0) return `Aujourd'hui ${DF_TIME.format(d)}`;
  if (d.getTime() >= day0 - 864e5) return `Hier ${DF_TIME.format(d)}`;
  return DF_DAY.format(d);
}

async function copyText(t) {
  try { await navigator.clipboard.writeText(t); }
  catch {
    const ta = document.createElement('textarea'); ta.value = t; document.body.append(ta); ta.select();
    document.execCommand('copy'); ta.remove();
  }
  toast('Copié', 'ok');
}

// ───────────────────────── API ─────────────────────────
async function api(path, { method = 'GET', body } = {}) {
  const opt = { method, headers: { 'X-Archiviste-Token': TOKEN } };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let j = null;
  try { j = await r.json(); } catch { /* vide */ }
  if (r.status === 403 && j && j.error === 'token') { location.reload(); throw new Error('Session expirée'); }
  if (!r.ok) throw new Error((j && j.message) || `Erreur ${r.status}`);
  return j;
}
const post = (path, body = {}) => api(path, { method: 'POST', body });

async function streamApi(path, body, onEvent, signal) {
  const r = await fetch(path, {
    method: 'POST', signal,
    headers: { 'X-Archiviste-Token': TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let j = null; try { j = await r.json(); } catch { /* */ }
    if (r.status === 403 && j && j.error === 'token') { location.reload(); return; }
    throw new Error((j && j.message) || `Erreur ${r.status}`);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}
const rawUrl = (p, dl) => `/api/fs/raw?t=${enc(TOKEN)}&path=${enc(p)}${dl ? '&dl=1' : ''}`;
const thumbUrl = (p) => `/api/fs/thumb?t=${enc(TOKEN)}&path=${enc(p)}`;
// ── Grimoire (appli de bureau) ──
const GRIM_EXTS = new Set(['docx', 'xlsx', 'xlsm', 'xls', 'ods', 'csv', 'txt', 'md', 'pdf']);
const GRIM_FIRST = new Set(['docx', 'xlsx', 'xlsm', 'xls', 'ods']);
const hasGrimoire = () => !!(S.status && S.status.grimoire);
const grimOk = (e) => hasGrimoire() && !e.dir && GRIM_EXTS.has(e.ext);
const hasMdTable = (t) => /^\s*\|?.*\|.*\n\s*\|?\s*:?-{2,}/m.test(t || '');
async function openInGrimoire(path) {
  try { await post('/api/fs/open', { path, app: 'grimoire' }); toast(`Ouverture de « ${basename(path)} » dans Grimoire…`); }
  catch (e) { toast(e.message, 'err'); }
}
async function newOffice(kind, dir = F.path) {
  const word = kind === 'docx';
  const name = await promptText({
    title: word ? 'Nouveau document Word' : 'Nouveau classeur Excel',
    label: `Dans ${tildify(dir)}${hasGrimoire() ? ' — il s\'ouvrira dans Grimoire' : ''}`,
    value: word ? 'Nouveau document.docx' : 'Nouveau classeur.xlsx', selectStem: true, ok: 'Créer',
  });
  if (!name) return;
  try {
    const r = await post('/api/office/new', { dir, name, kind, open: true });
    toast(r.ouvert === 'grimoire' ? `Créé et ouvert dans Grimoire : ${basename(r.path)}` : `Créé : ${basename(r.path)}`, 'ok');
    if (F.path === dirname(r.path)) { await loadDir(); selectPath(r.path); }
  } catch (e) { toast(e.message, 'err'); }
}
const cleanName = (t) => String(t || '').replace(/[#*_`>|\[\]]/g, '').replace(/[\\/:*?"<>|]/g, '').trim().slice(0, 60);
async function sendToOffice(text, kind, suggested) {
  const word = kind === 'docx';
  const first = (String(text).match(/^#{1,3}\s+(.+)$/m) || [])[1];
  const base = cleanName(first || suggested) || `Archiviste ${stamp()}`;
  let start = S.home;
  try { start = (await api(`/api/fs/list?path=${enc(joinPath(S.home, 'Documents'))}`)).path; } catch { /* pas de ~/Documents */ }
  const target = await pickPath({
    mode: 'save', start, filename: `${base}.${kind}`,
    title: word ? 'Enregistrer en document Word' : 'Enregistrer les tableaux en classeur',
    okLabel: hasGrimoire() ? 'Créer et ouvrir dans Grimoire' : 'Créer',
  });
  if (!target) return;
  let r;
  try { r = await post('/api/office/new', { path: target, kind, content: text, open: true }); }
  catch (e) {
    if (!/existe déjà/.test(e.message)) return toast(e.message, 'err');
    if (!(await ask(`« ${basename(target)} » existe déjà. Créer une copie avec un autre nom ?`, { ok: 'Créer une copie' }))) return;
    try { r = await post('/api/office/new', { path: target, kind, content: text, open: true, unique: true }); }
    catch (e2) { return toast(e2.message, 'err'); }
  }
  toast(r.ouvert === 'grimoire' ? `Ouvert dans Grimoire : ${basename(r.path)}` : `Créé : ${tildify(r.path)}`, 'ok',
    { label: 'Voir', action: () => go('files', { path: dirname(r.path), select: r.path }) });
}
async function openWithSystem(path, reveal = false) {
  try {
    await post('/api/fs/open', { path, reveal });
    toast(reveal ? 'Ouverture dans le gestionnaire de fichiers…' : `Ouverture de « ${basename(path)} »…`);
  } catch (e) { toast(e.message, 'err'); }
}

// ───────────────────────── Notifications ─────────────────────────
function toast(msg, type = 'info', opts = {}) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="msg"></span>`;
  $('.msg', el).textContent = msg;
  if (opts.label) {
    const b = document.createElement('button');
    b.className = 'btn sm act'; b.textContent = opts.label;
    b.onclick = () => { opts.action?.(); close(); };
    el.append(b);
  }
  $('#toasts').append(el);
  let timer;
  const close = () => { clearTimeout(timer); el.remove(); };
  if (!opts.sticky) timer = setTimeout(close, opts.timeout || (type === 'err' ? 7000 : opts.label ? 8000 : 3200));
  return { el, close, set: (t) => { $('.msg', el).textContent = t; } };
}

// ───────────────────────── Fenêtres ─────────────────────────
function openModal({ title, body = '', footer = '', cls = '', onClose, beforeClose }) {
  const ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML = `<div class="modal ${cls}" role="dialog" aria-modal="true">
      <div class="mh"><h2></h2><button class="icon-btn" data-close title="Fermer (Échap)">${ic('x')}</button></div>
      <div class="mb"></div>${footer !== null ? '<div class="mf"></div>' : ''}</div>`;
  $('h2', ov).textContent = title;
  const mb = $('.mb', ov);
  const mf = $('.mf', ov);
  if (typeof body === 'string') mb.innerHTML = body; else mb.append(body);
  if (mf) mf.innerHTML = footer;
  document.body.append(ov);
  let closed = false;
  const close = async (force) => {
    if (closed) return;
    if (!force && beforeClose && !(await beforeClose())) return;
    closed = true;
    ov.remove();
    document.removeEventListener('keydown', onKey, true);
    onClose?.();
  };
  const onKey = (e) => {
    if (e.key === 'Escape' && $$('.overlay').pop() === ov && !$('.menu')) { e.preventDefault(); e.stopPropagation(); close(); }
  };
  ov.addEventListener('mousedown', (e) => { if (e.target === ov) close(); });
  ov.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });
  document.addEventListener('keydown', onKey, true);
  setTimeout(() => { const f = $('[autofocus]', ov) || $('input:not([type=checkbox]):not([type=range]), textarea', mb); f?.focus(); }, 30);
  return { el: ov, mb, mf, close };
}

function ask(message, { title = 'Confirmer', ok = 'Confirmer', danger = false } = {}) {
  return new Promise((resolve) => {
    let res = false;
    const m = openModal({
      title, body: `<p style="margin:0;white-space:pre-wrap">${esc(message)}</p>`,
      footer: `<button class="btn" data-close>Annuler</button><button class="btn ${danger ? 'danger solid' : 'primary'}" data-ok autofocus>${esc(ok)}</button>`,
      onClose: () => resolve(res),
    });
    $('[data-ok]', m.el).onclick = () => { res = true; m.close(true); };
    setTimeout(() => $('[data-ok]', m.el).focus(), 40);
  });
}

function promptText({ title, label = '', value = '', placeholder = '', ok = 'Valider', selectStem = false, multiline = false, password = false }) {
  return new Promise((resolve) => {
    let res = null;
    const input = multiline
      ? `<textarea rows="6" data-v placeholder="${esc(placeholder)}">${esc(value)}</textarea>`
      : `<input type="${password ? 'password' : 'text'}" data-v value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off">`;
    const m = openModal({
      title, body: `<label class="field">${label ? `<span>${esc(label)}</span>` : ''}${input}</label>`,
      footer: `<button class="btn" data-close>Annuler</button><button class="btn primary" data-ok>${esc(ok)}</button>`,
      onClose: () => resolve(res),
    });
    const inp = $('[data-v]', m.el);
    const submit = () => { res = password ? inp.value : inp.value.trim(); if (!res) return; m.close(true); };
    $('[data-ok]', m.el).onclick = submit;
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (!multiline || e.ctrlKey)) { e.preventDefault(); submit(); } });
    setTimeout(() => {
      inp.focus();
      if (selectStem && !multiline) { const dot = value.lastIndexOf('.'); inp.setSelectionRange(0, dot > 0 ? dot : value.length); }
      else if (!multiline) inp.select();
    }, 40);
  });
}

// ── Menu contextuel ──
let openMenuEl = null;
function closeMenu() { openMenuEl?.remove(); openMenuEl = null; }
function showMenu(x, y, items, { search = false } = {}) {
  closeMenu();
  const el = document.createElement('div');
  el.className = 'menu';
  const draw = (filter = '') => {
    const f = filter.toLowerCase();
    el.innerHTML = (search ? `<input type="search" placeholder="Filtrer…" value="${esc(filter)}">` : '') + items.map((it, i) => {
      if (it === 'sep') return f ? '' : '<div class="sep"></div>';
      if (it.header) return f ? '' : `<div class="mh">${esc(it.header)}</div>`;
      if (f && !(it.label + ' ' + (it.sub || '')).toLowerCase().includes(f)) return '';
      return `<button data-i="${i}" class="${it.danger ? 'danger' : ''}" ${it.disabled ? 'disabled' : ''}>${it.emoji ? `<span>${esc(it.emoji)}</span>` : it.icon ? ic(it.icon, 'sm') : ''}<span class="grow ellipsis">${esc(it.label)}${it.sub ? `<br><small class="faint">${esc(it.sub)}</small>` : ''}</span>${it.kbd ? `<span class="kbd">${esc(it.kbd)}</span>` : ''}</button>`;
    }).join('');
    if (search) {
      const inp = $('input', el);
      inp.oninput = () => { const v = inp.value; draw(v); const n = $('input', el); n.focus(); n.setSelectionRange(v.length, v.length); };
    }
  };
  draw();
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-i]');
    if (!b) return;
    const it = items[+b.dataset.i];
    closeMenu();
    it.act?.();
  });
  document.body.append(el);
  const r = el.getBoundingClientRect();
  el.style.left = Math.max(6, Math.min(x, innerWidth - r.width - 8)) + 'px';
  el.style.top = Math.max(6, Math.min(y, innerHeight - r.height - 8)) + 'px';
  openMenuEl = el;
  if (search) setTimeout(() => $('input', el)?.focus(), 20);
  return el;
}
document.addEventListener('mousedown', (e) => { if (openMenuEl && !openMenuEl.contains(e.target)) closeMenu(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && openMenuEl) { closeMenu(); e.stopPropagation(); } }, true);
window.addEventListener('resize', closeMenu);
function menuAt(el, items, opts) {
  const r = el.getBoundingClientRect();
  const m = showMenu(r.left, r.bottom + 4, items, opts);
  // Pas la place en dessous (bouton en bas de l'écran) : le menu s'ouvre au-dessus au lieu de recouvrir le bouton.
  const h = m.getBoundingClientRect().height;
  if (r.bottom + 4 + h > innerHeight - 8 && r.top - 4 - h >= 6) m.style.top = (r.top - 4 - h) + 'px';
  return m;
}

// ───────────────────────── Markdown ─────────────────────────
function inline(t) {
  const codes = [];
  t = String(t).replace(/`([^`\n]+)`/g, (_, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0001`; });
  t = esc(t);
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  t = t.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  t = t.replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>').replace(/__([^_\n]+?)__/g, '<strong>$1</strong>');
  t = t.replace(/(^|[^*\w])\*([^*\s][^*\n]*?)\*(?!\*)/g, '$1<em>$2</em>');
  t = t.replace(/(^|[\s(])_([^_\s][^_\n]*?)_(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>');
  t = t.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
  return t.replace(/\u0001(\d+)\u0001/g, (_, n) => `<code>${esc(codes[+n])}</code>`);
}
const codeHtml = (lang, code) => `<div class="codeb"><div class="ch"><span>${esc(lang || 'texte')}</span><button class="icon-btn sm" data-copy title="Copier">${ic('copy', 'sm')}</button></div><pre><code>${esc(code)}</code></pre></div>`;
const LIST_RE = /^(\s*)([-*+•]|\d+[.)])\s+(.*)$/;
function listHtml(lines) {
  const items = [];
  for (const l of lines) {
    const m = l.match(LIST_RE);
    if (m) items.push({ ind: m[1].replace(/\t/g, '    ').length, ord: /\d/.test(m[2]), start: parseInt(m[2], 10), text: m[3] });
    else if (items.length) items[items.length - 1].text += '\n' + l.trim();
  }
  const build = (from, ind) => {
    const ord = items[from].ord;
    let html = ord ? `<ol${items[from].start > 1 ? ` start="${items[from].start}"` : ''}>` : '<ul>';
    let k = from;
    while (k < items.length && items[k].ind >= ind) {
      if (items[k].ind > ind) {
        const [sub, nk] = build(k, items[k].ind);
        html = html.endsWith('</li>') ? html.slice(0, -5) + sub + '</li>' : html + sub;
        k = nk; continue;
      }
      let txt = items[k].text;
      const task = txt.match(/^\[([ xX])\]\s+(.*)$/s);
      if (task) txt = (task[1] === ' ' ? '☐ ' : '☑ ') + task[2];
      html += `<li>${txt.split('\n').map(inline).join('<br>')}</li>`;
      k++;
    }
    return [html + (ord ? '</ol>' : '</ul>'), k];
  };
  let html = ''; let k = 0;
  while (k < items.length) { const [h, nk] = build(k, items[k].ind); html += h; k = nk; }
  return html;
}
function md(src) {
  if (!src) return '';
  let s = String(src).replace(/\r\n?/g, '\n').replace(/<think>[\s\S]*?(<\/think>|$)/g, '');
  const blocks = [];
  s = s.replace(/^[ \t]*```[ \t]*([\w#+.-]*)[^\n]*\n([\s\S]*?)(?:^[ \t]*```[ \t]*$|(?![\s\S]))/gm,
    (_, lang, code) => { blocks.push([lang, code.replace(/\n$/, '')]); return `\u0000B${blocks.length - 1}\u0000`; });
  const lines = s.split('\n');
  const out = [];
  const isSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
  const isTable = (i) => lines[i].includes('|') && i + 1 < lines.length && isSep(lines[i + 1]);
  const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  const blockStart = (i) => /^(#{1,6})\s|^\s*>|^\u0000B/.test(lines[i]) || LIST_RE.test(lines[i]) || isTable(i);
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    let m;
    if ((m = l.trim().match(/^\u0000B(\d+)\u0000$/))) { const [lang, code] = blocks[+m[1]]; out.push(codeHtml(lang, code)); i++; continue; }
    if (!l.trim()) { i++; continue; }
    if ((m = l.match(/^(#{1,6})\s+(.*)$/))) { const n = Math.min(m[1].length, 4); out.push(`<h${n}>${inline(m[2])}</h${n}>`); i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)) { out.push('<hr>'); i++; continue; }
    if (/^\s*>/.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++; }
      out.push(`<blockquote>${md(buf.join('\n'))}</blockquote>`); continue;
    }
    if (isTable(i)) {
      const head = cells(l); i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(cells(lines[i])); i++; }
      out.push(`<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${head.map((_, k) => `<td>${inline(r[k] || '')}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    if (LIST_RE.test(l)) {
      const buf = [];
      while (i < lines.length && (LIST_RE.test(lines[i]) || (lines[i].trim() && /^\s{2,}\S/.test(lines[i])))) { buf.push(lines[i]); i++; }
      out.push(listHtml(buf)); continue;
    }
    const buf = [l]; i++;
    while (i < lines.length && lines[i].trim() && !blockStart(i)) { buf.push(lines[i]); i++; }
    out.push(`<p>${buf.map(inline).join('<br>')}</p>`);
  }
  return out.join('');
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-copy]');
  if (b) copyText($('code', b.closest('.codeb')).textContent);
});

// ───────────────────────── État ─────────────────────────
const S = {
  view: 'files', settings: null, status: null, home: '', tools: [], agents: [], prompts: [],
  files: { path: null, root: null, parent: null, entries: [], sel: new Set(), anchor: null, focus: null, search: null,
    sortBy: 'name', sortDir: 1, preview: true, hidden: false, built: false },
  sort: { path: '', mode: 'ai', consignes: '', content: false, recursive: false, plan: [], scan: null,
    running: false, cancel: false, filter: null, result: null, journal: [], built: false },
  chat: { convs: [], conv: null, draft: null, atts: [], busy: false, ctrl: null, filter: '', built: false },
  trash: { items: [], sel: new Set() },
};
const agentById = (id) => S.agents.find((a) => a.id === id) || null;
const toolLabel = (n) => S.tools.find((t) => t.name === n)?.label || n;
const freshDraft = (o = {}) => ({ agent_id: null, modele: '', workspace: '', think: null, ...o });

// ───────────────────────── Navigation ─────────────────────────
const RENDER = {};
function go(view, opts = {}) {
  closeMenu();
  S.view = view;
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + view));
  $$('#nav button').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
  RENDER[view]?.(opts);
  updateHash();
}
function updateHash() {
  let h = '#/' + S.view;
  if (S.view === 'files' && S.files.path) h += '?p=' + enc(S.files.path);
  if (S.view === 'chat' && S.chat.conv) h += '/' + S.chat.conv.id;
  if (location.hash !== h) history.replaceState(null, '', h);
}
function routeFromHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [main, query = ''] = h.split('?');
  const [view, sub] = main.split('/');
  const params = new URLSearchParams(query);
  if (view === 'files') return go('files', { path: params.get('p'), select: params.get('s'), props: params.get('i') === '1' });
  if (view === 'sort') return go('sort', { path: params.get('p') });
  if (view === 'chat') return go('chat', { conv: sub });
  if (RENDER[view]) return go(view);
  go('files');
}

// Appelé par la fenêtre GTK quand le bureau demande d'ouvrir une vue
window.archivisteNaviguer = (d = {}) => {
  if (d.vue === 'files') return go('files', { path: d.chemin, select: d.select, props: !!d.proprietes });
  if (d.vue === 'sort') return go('sort', { path: d.chemin });
  if (d.vue === 'chat') return go('chat', { conv: d.conv });
  if (RENDER[d.vue]) go(d.vue);
};

// ── Raccourcis du volet du bureau ──
async function pinShortcut(type, cible, nom) {
  try {
    const r = await post('/api/raccourcis/ajouter', { type, cible, nom });
    toast(r.deja ? `« ${r.raccourci.titre} » est déjà dans les raccourcis` : `« ${r.raccourci.titre} » épinglé aux raccourcis du bureau`, r.deja ? 'info' : 'ok');
    return r;
  } catch (e) { toast(e.message, 'err'); return null; }
}
const pinItem = (e) => pinShortcut(e.ext === 'desktop' && !e.dir ? 'app' : e.dir ? 'dossier' : 'fichier', e.path);

// ───────────────────────── Statut Ollama ─────────────────────────
async function refreshStatus() {
  try { S.status = await api('/api/status'); } catch (e) { S.status = { ok: false, error: e.message, models: [] }; }
  const st = S.status;
  const pill = $('#statusPill');
  pill.classList.remove('ok', 'bad', 'warn');
  if (st.ok && st.model_present) {
    pill.classList.add('ok');
    $('#statusText').textContent = st.model;
    $('#statusSub').textContent = `Ollama ${st.version || ''} · prêt`;
  } else if (st.ok) {
    pill.classList.add('warn');
    $('#statusText').textContent = 'Modèle absent';
    $('#statusSub').textContent = `ollama pull ${st.model}`;
  } else {
    pill.classList.add('bad');
    $('#statusText').textContent = 'Ollama hors ligne';
    $('#statusSub').textContent = 'Clique pour les réglages';
  }
  $('#brandModel').textContent = `${S.settings?.model || ''} · local`;
  return st;
}
function ollamaBanner() {
  const st = S.status;
  if (!st) return '';
  if (!st.ok) {
    return `<div class="banner danger">${ic('alert')}<div><b>Ollama ne répond pas.</b> Lance-le dans un terminal : <code>systemctl start ollama</code> (ou <code>ollama serve</code>), puis réessaie.<br><small class="muted">${esc(st.error || '')}</small></div></div>`;
  }
  if (!st.model_present) {
    return `<div class="banner">${ic('info')}<div><b>Le modèle ${esc(st.model)} n'est pas encore téléchargé.</b> Dans un terminal : <code>ollama pull ${esc(st.model)}</code></div></div>`;
  }
  return '';
}

// ───────────────────────── Sélecteur de chemin ─────────────────────────
function pickPath({ title = 'Choisir', mode = 'dir', start, filename = '', okLabel } = {}) {
  return new Promise((resolve) => {
    let done = false;
    let cur = start || S.files.path || S.home;
    let list = [];
    let parent = null;
    let root = null;
    const sel = new Set();
    const label = okLabel || (mode === 'dir' ? 'Choisir ce dossier' : mode === 'save' ? 'Enregistrer' : 'Joindre');
    const m = openModal({
      title, cls: 'wide',
      body: `<div class="crumbs" data-pk="crumbs" style="flex:none"></div>
        <div class="picker-list" data-pk="list"></div>
        ${mode === 'save' ? `<label class="field"><span>Nom du fichier</span><input type="text" data-pk="name" value="${esc(filename)}"></label>` : ''}
        <div class="muted" data-pk="info" style="font-size:12.5px"></div>`,
      footer: `<button class="btn ghost" data-pk="newdir">${ic('folderPlus', 'sm')} Nouveau dossier</button><span class="grow"></span>
        <button class="btn" data-close>Annuler</button><button class="btn primary" data-pk="ok">${esc(label)}</button>`,
      onClose: () => { if (!done) resolve(null); },
    });
    const box = m.el;
    const listEl = $('[data-pk=list]', box);
    const info = () => {
      const n = sel.size;
      $('[data-pk=info]', box).textContent = mode === 'dir'
        ? `Dossier choisi : ${tildify(n ? [...sel][0] : cur)}`
        : mode === 'files' ? (n ? `${n} élément(s) sélectionné(s)` : 'Clique pour sélectionner, double-clic pour ouvrir un dossier.')
          : `Sera enregistré dans : ${tildify(cur)}`;
    };
    const render = () => {
      const segs = [];
      if (root) {
        segs.push(`<button data-go="${esc(root)}">${root === S.home ? 'Dossier personnel' : esc(basename(root))}</button>`);
        const rest = cur.slice(root.length).split('/').filter(Boolean);
        let acc = root;
        for (const r of rest) { acc = joinPath(acc, r); segs.push(`<span class="slash">›</span><button data-go="${esc(acc)}">${esc(r)}</button>`); }
      }
      $('[data-pk=crumbs]', box).innerHTML = segs.join('');
      listEl.innerHTML = (parent ? `<div class="pick-row" data-up>${ic('up', 'sm')} <span class="muted">Dossier parent</span></div>` : '')
        + list.map((e, i) => `<div class="pick-row ${sel.has(e.path) ? 'sel' : ''}" data-i="${i}">${fileIcon(e)}<span class="grow ellipsis">${esc(e.name)}</span><span class="faint" style="font-size:12px">${e.dir ? '' : fmtSize(e.size)}</span></div>`).join('')
        + (list.length ? '' : '<div class="empty" style="padding:30px">Dossier vide</div>');
      info();
    };
    const load = async (p) => {
      try {
        const r = await api(`/api/fs/list?path=${enc(p)}${S.files.hidden ? '&hidden=1' : ''}`);
        cur = r.path; parent = r.parent; root = r.root;
        list = mode === 'dir' ? r.entries.filter((e) => e.dir) : r.entries;
        sel.clear();
        render();
      } catch (e) {
        toast(e.message, 'err');
        if (p !== S.home) load(S.home);
      }
    };
    box.addEventListener('click', async (e) => {
      const go2 = e.target.closest('[data-go]');
      if (go2) return load(go2.dataset.go);
      if (e.target.closest('[data-up]')) return load(parent);
      const row = e.target.closest('.pick-row[data-i]');
      if (row) {
        const it = list[+row.dataset.i];
        if (mode === 'dir') { sel.clear(); sel.add(it.path); }
        else if (mode === 'save') { if (!it.dir) $('[data-pk=name]', box).value = it.name; }
        else { sel.has(it.path) ? sel.delete(it.path) : sel.add(it.path); }
        render();
        return;
      }
      const pk = e.target.closest('[data-pk]')?.dataset.pk;
      if (pk === 'newdir') {
        const name = await promptText({ title: 'Nouveau dossier', label: `Dans ${tildify(cur)}`, value: 'Nouveau dossier' });
        if (!name) return;
        try { const r = await post('/api/fs/mkdir', { dir: cur, name }); await load(cur); if (mode === 'dir') { sel.add(r.path); render(); } }
        catch (err) { toast(err.message, 'err'); }
      }
      if (pk === 'ok') {
        if (mode === 'dir') { done = true; resolve(sel.size ? [...sel][0] : cur); m.close(true); }
        else if (mode === 'files') {
          if (!sel.size) return toast('Sélectionne au moins un élément.', 'err');
          done = true; resolve([...sel]); m.close(true);
        } else {
          const n = $('[data-pk=name]', box).value.trim();
          if (!n || n.includes('/')) return toast('Nom de fichier invalide.', 'err');
          done = true; resolve(joinPath(cur, n)); m.close(true);
        }
      }
    });
    listEl.addEventListener('dblclick', (e) => {
      const row = e.target.closest('.pick-row[data-i]');
      if (!row) return;
      const it = list[+row.dataset.i];
      if (it.dir) load(it.path);
      else if (mode === 'files') { done = true; resolve([it.path]); m.close(true); }
    });
    if (mode === 'save') $('[data-pk=name]', box).addEventListener('keydown', (e) => { if (e.key === 'Enter') $('[data-pk=ok]', box).click(); });
    load(cur);
  });
}

async function saveTextToFile(text, suggested) {
  const target = await pickPath({ mode: 'save', title: 'Enregistrer dans un fichier', filename: suggested });
  if (!target) return;
  try { await post('/api/fs/write', { path: target, content: text, create_only: true }); }
  catch (e) {
    if (!/existe déjà/.test(e.message)) return toast(e.message, 'err');
    if (!(await ask(`« ${basename(target)} » existe déjà. Le remplacer ?\n(L'ancienne version est sauvegardée.)`, { ok: 'Remplacer' }))) return;
    try { await post('/api/fs/write', { path: target, content: text }); } catch (e2) { return toast(e2.message, 'err'); }
  }
  toast(`Enregistré : ${tildify(target)}`, 'ok', { label: 'Voir', action: () => { go('files', { path: dirname(target), select: target }); } });
}
const stamp = () => { const d = new Date(); const p = (n) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}h${p(d.getMinutes())}`; };

// ═════════════════════════════════════════════════════════════
//  FICHIERS
// ═════════════════════════════════════════════════════════════
const F = S.files;
function buildFiles() {
  const v = $('#view-files');
  v.innerHTML = `
    <div class="vhead">
      <h1>Fichiers</h1>
      <div class="crumbs" id="fCrumbs"></div>
      <div class="fsearch" title="Recherche dans ce dossier et ses sous-dossiers">
        ${ic('search', 'sm')}<input type="search" id="fSearch" placeholder="Rechercher ici…">
        <label class="check" title="Chercher aussi dans le texte des fichiers (plus lent)"><input type="checkbox" id="fSearchContent"><span class="muted" style="font-size:12px">contenu</span></label>
      </div>
    </div>
    <div class="ftoolbar">
      <select id="fRoot" title="Dossiers autorisés"></select>
      <button class="icon-btn" data-act="back" id="fBack" title="Précédent (Alt+←)" disabled>${ic('up', 'rot-l')}</button>
      <button class="icon-btn" data-act="fwd" id="fFwd" title="Suivant (Alt+→)" disabled>${ic('up', 'rot-r')}</button>
      <button class="icon-btn" data-act="up" title="Dossier parent (Alt+↑ ou Retour arrière)">${ic('up')}</button>
      <button class="icon-btn" data-act="refresh" title="Actualiser (F5)">${ic('refresh')}</button>
      <button class="icon-btn" data-act="terminal" title="Ouvrir un terminal ici">${ic('code')}</button>
      <span class="tbsep"></span>
      <button class="btn ghost sm" data-act="newFolder">${ic('folderPlus', 'sm')} Dossier</button>
      <button class="btn ghost sm" data-act="newMenu" title="Nouveau fichier texte, document Word ou classeur">${ic('filePlus', 'sm')} Fichier ▾</button>
      <button class="btn ghost sm" data-act="upload">${ic('upload', 'sm')} Importer</button>
      <span class="tbsep"></span>
      <button class="btn ghost sm" data-act="sortHere">${ic('sparkles', 'sm')} Trier ce dossier</button>
      <button class="btn ghost sm" data-act="agentHere">${ic('bot', 'sm')} Agent ici</button>
      <button class="btn ghost sm" data-act="chatHere">${ic('chat', 'sm')} En discuter</button>
      <span class="grow"></span>
      <button class="icon-btn" data-act="toggleHidden" id="fHiddenBtn" title="Afficher les fichiers cachés">${ic('eye')}</button>
      <button class="icon-btn on" data-act="togglePreview" id="fPrevBtn" title="Panneau d'aperçu">${ic('panel')}</button>
      <input type="file" id="fUpload" multiple hidden>
    </div>
    <div class="selbar hidden" id="fSelbar"></div>
    <div class="fwrap" id="fWrap">
      <div class="flist" id="fList" tabindex="0"></div>
      <aside class="preview" id="fPreview"></aside>
    </div>`;
  F.hidden = !!S.settings.show_hidden;
  $('#fHiddenBtn').classList.toggle('on', F.hidden);

  v.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b || !v.contains(b)) return;
    const act = b.dataset.act;
    const fn = FILE_ACTS[act];
    if (fn) { e.preventDefault(); fn(b, e); }
  });
  $('#fRoot').addEventListener('change', (e) => openDir(e.target.value));
  // un clic dans le vide de la barre de chemin : on peut le taper
  $('#fCrumbs').addEventListener('click', (e) => { if (e.target.id === 'fCrumbs') editAddress(); });
  // raccourcis de Nemo, valables partout dans la vue Fichiers (sauf pendant une saisie)
  document.addEventListener('keydown', (e) => {
    if (S.view !== 'files' || $('.overlay') || openMenuEl) return;
    const typing = e.target.matches('input, textarea, select, [contenteditable]');
    const k = e.key;
    const ctrl = e.ctrlKey || e.metaKey;
    let fn = null;
    if (e.altKey && k === 'ArrowLeft') fn = () => histGo(-1);
    else if (e.altKey && k === 'ArrowRight') fn = () => histGo(1);
    else if (e.altKey && k === 'ArrowUp') fn = FILE_ACTS.up;
    else if (e.altKey && k === 'Home') fn = () => openDir(S.home);
    else if (k === 'F5' || (ctrl && (k === 'r' || k === 'R') && !typing)) fn = () => (F.search ? runSearch(F.search.query) : loadDir());
    else if (ctrl && (k === 'l' || k === 'L')) fn = editAddress;
    else if (ctrl && (k === 'f' || k === 'F')) fn = () => { $('#fSearch').focus(); $('#fSearch').select(); };
    else if (ctrl && (k === 'h' || k === 'H') && !typing) fn = FILE_ACTS.toggleHidden;
    else if (ctrl && e.shiftKey && (k === 'n' || k === 'N') && !typing) fn = FILE_ACTS.newFolder;
    else if (ctrl && e.altKey && (k === 't' || k === 'T')) fn = () => openTerminal(F.path);
    if (!fn || (typing && !['F5', 'l', 'L', 'f', 'F'].includes(k) && !e.altKey)) return;
    e.preventDefault();
    fn();
  });
  // boutons « précédent / suivant » de la souris
  v.addEventListener('mouseup', (e) => { if (e.button === 3) { e.preventDefault(); histGo(-1); } else if (e.button === 4) { e.preventDefault(); histGo(1); } });
  $('#fUpload').addEventListener('change', (e) => { uploadFiles(e.target.files, F.path); e.target.value = ''; });
  const doSearch = () => {
    const q = $('#fSearch').value.trim();
    if (!q) { if (F.search) { F.search = null; renderFileList(); renderPreview(); } return; }
    runSearch(q);
  };
  $('#fSearch').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); if (e.key === 'Escape') { e.target.value = ''; doSearch(); } });
  // index prêt : la recherche répond tout de suite, donc elle suit la frappe (Entrée vérifie en plus le disque)
  $('#fSearch').addEventListener('input', debounce(() => {
    const q = $('#fSearch').value.trim();
    if (!q) return doSearch();
    if (q.length >= 2 && S.index?.pret && !F.hidden) runSearch(q, true);
    return null;
  }, 260));

  const list = $('#fList');
  list.addEventListener('click', onRowClick);
  list.addEventListener('dblclick', (e) => { const r = e.target.closest('.frow[data-i]'); if (r && !e.target.closest('[data-act]')) openEntry(curList()[+r.dataset.i]); });
  list.addEventListener('contextmenu', (e) => {
    const r = e.target.closest('.frow[data-i]');
    e.preventDefault();
    if (r) {
      const it = curList()[+r.dataset.i];
      if (!F.sel.has(it.path)) { F.sel = new Set([it.path]); F.anchor = +r.dataset.i; refreshSelection(); }
      rowMenu(e.clientX, e.clientY);
    } else {
      showMenu(e.clientX, e.clientY, [
        { label: CLIP.paths.length ? `Coller ici (${CLIP.paths.length} élément${CLIP.paths.length > 1 ? 's' : ''} ${CLIP.mode === 'couper' ? 'coupé' : 'copié'}${CLIP.paths.length > 1 ? 's' : ''})` : 'Coller', icon: 'download', kbd: 'Ctrl+V', disabled: !CLIP.paths.length, act: () => pasteHere() },
        'sep',
        { label: 'Nouveau dossier', icon: 'folderPlus', act: FILE_ACTS.newFolder },
        { label: 'Nouveau fichier texte', icon: 'filePlus', act: FILE_ACTS.newFile },
        { label: 'Nouveau document Word', icon: 'quill', act: () => newOffice('docx') },
        { label: 'Nouveau classeur Excel', icon: 'sheet', act: () => newOffice('xlsx') },
        { label: 'Importer des fichiers…', icon: 'upload', act: FILE_ACTS.upload },
        'sep',
        { label: 'Trier ce dossier avec l\'IA', icon: 'sparkles', act: FILE_ACTS.sortHere },
        'sep',
        { label: 'Ouvrir un terminal ici', icon: 'code', act: () => openTerminal(F.path) },
        { label: 'Actualiser', icon: 'refresh', kbd: 'F5', act: () => loadDir() },
        { label: 'Propriétés du dossier', icon: 'info', kbd: 'Alt+Entrée', act: () => showProperties([F.path]) },
      ]);
    }
  });
  list.addEventListener('keydown', onFileKey);
  // glisser-déposer
  const wrap = $('#fWrap');
  let dragDepth = 0;
  const overlay = () => $('.drop-overlay', wrap);
  // Glisser un fichier dans un dossier le DÉPLACE (Ctrl : copie), d'où qu'il vienne : cette liste, le bureau
  // Archiviste, Nemo… Il n'est importé (copié) que si son emplacement sur le disque est inconnu ou hors des
  // dossiers autorisés.
  let ownDrag = false;  // une ligne de cette liste est en train d'être glissée
  const own = () => ownDrag;
  const outside = (dt) => !ownDrag && ['Files', 'application/x-archiviste-paths', 'text/uri-list'].some((t) => dt.types.includes(t));
  const located = (dt) => dt.types.includes('application/x-archiviste-paths') || dt.types.includes('text/uri-list');
  const folderRow = (e) => {
    const r = e.target.closest?.('.frow[data-i]');
    const it = r && curList()[+r.dataset.i];
    return it?.dir && !(own() && F.sel.has(it.path)) ? { r, it } : null;
  };
  const dropHint = (e) => {
    const t = folderRow(e);
    const verb = !located(e.dataTransfer) ? 'Importer' : dragCopy(e) ? 'Copier' : 'Déplacer';
    const where = t ? `dans « ${t.it.name} »` : `ici — ${tildify(F.path)}`;
    const o = overlay();
    if (o) o.innerHTML = `${ic(verb === 'Importer' ? 'upload' : verb === 'Copier' ? 'copy' : 'move')}<b>${verb} ${esc(where)}</b>${verb === 'Déplacer' ? '<span class="muted">Ctrl : copier</span>' : ''}`;
  };
  wrap.addEventListener('dragenter', (e) => {
    if (!outside(e.dataTransfer)) return;
    e.preventDefault(); dragDepth++;
    if (!overlay()) wrap.insertAdjacentHTML('beforeend', '<div class="drop-overlay"></div>');
    dropHint(e);
  });
  wrap.addEventListener('dragleave', (e) => { if (!outside(e.dataTransfer)) return; if (--dragDepth <= 0) { dragDepth = 0; overlay()?.remove(); $$('.frow.drop', list).forEach((x) => x.classList.remove('drop')); } });
  wrap.addEventListener('dragover', (e) => {
    const dt = e.dataTransfer;
    const t = folderRow(e);
    $$('.frow.drop', list).forEach((x) => x !== t?.r && x.classList.remove('drop'));
    if (outside(dt)) {
      e.preventDefault();
      dt.dropEffect = !located(dt) || dragCopy(e) ? 'copy' : 'move';
      t?.r.classList.add('drop');
      dropHint(e);
    } else if (own() && t) {
      e.preventDefault(); dt.dropEffect = dragCopy(e) ? 'copy' : 'move'; t.r.classList.add('drop');
    }
  });
  wrap.addEventListener('drop', async (e) => {
    const dt = e.dataTransfer;
    const t = folderRow(e);
    $$('.frow.drop', list).forEach((x) => x.classList.remove('drop'));
    dragDepth = 0; overlay()?.remove();
    if (own()) {  // une ligne de cette liste, lâchée sur un dossier
      if (!t || !DRAG_PATHS) return;
      e.preventDefault();
      const info = await dropInfo(e);
      const paths = info.paths.filter((p) => p !== t.it.path);
      if (paths.length) moveItems(paths, t.it.path, info.copy);
      return;
    }
    if (!outside(dt)) return;
    e.preventDefault();
    const dest = t ? t.it.path : F.path;
    const items = [...(dt.items || [])];
    const isDir = (i) => { try { return !!items[i]?.webkitGetAsEntry?.()?.isDirectory; } catch { return false; } };
    const files = [...dt.files].map((f, i) => ({ f, dir: isDir(i) }));  // lus tout de suite : après un « await » ils ne sont plus accessibles
    const { paths, copy } = await dropInfo(e);
    if (paths.length) {
      const todo = paths.filter((p) => p !== dest && (copy || dirname(p) !== dest));
      if (!todo.length) return toast('Déjà dans ce dossier.');
      let r;
      try { r = await post('/api/fs/move', { paths: todo, dest_dir: dest, copy }); } catch (err) { return toast(err.message, 'err'); }
      // refusé parce que hors des dossiers autorisés (clé USB non ajoutée, /tmp…) : on l'importe, l'original reste où il est
      const refused = r.erreurs.filter((x) => /autoris/i.test(x.erreur));
      const names = new Set(refused.map((x) => basename(x.path)));
      const others = r.erreurs.filter((x) => !refused.includes(x));
      if (others.length) toast(others.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
      if (r.tache) taskStarted(r.tache);
      if (r.ok.length) toast(`${r.ok.length} élément(s) ${copy ? 'copié(s)' : 'déplacé(s)'} ${t ? `dans ${t.it.name}` : 'ici'}`, 'ok', t ? { label: 'Y aller', action: () => openDir(dest) } : undefined);
      const imp = files.filter((x) => !x.dir && names.has(x.f.name)).map((x) => x.f);
      if (imp.length) { await uploadFiles(imp, dest); toast(`${imp.length} fichier(s) copié(s) : l'original est hors des dossiers autorisés d'Archiviste, il n'a pas été déplacé.`, 'info', { timeout: 8000 }); }
      else if (refused.length) toast(refused.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
      return F.search ? runSearch(F.search.query) : loadDir();
    }
    // emplacement inconnu (image glissée depuis une page web, pièce jointe…) : importé, comme avant
    if (!files.length) return toast('Rien à déplacer : ce qui a été glissé n\'est pas un fichier de ton PC.');
    const dirs = files.filter((x) => x.dir).length;
    if (dirs) toast(`${dirs} dossier(s) ignoré(s) : seuls les fichiers peuvent être importés par glisser-déposer.`, 'err');
    return uploadFiles(files.filter((x) => !x.dir).map((x) => x.f), dest);
  });
  list.addEventListener('dragstart', (e) => {
    const r = e.target.closest('.frow[data-i]');
    if (!r) return;
    const it = curList()[+r.dataset.i];
    if (!F.sel.has(it.path)) { F.sel = new Set([it.path]); refreshSelection(); }
    ownDrag = true;
    dragBegin([...F.sel]);
    e.dataTransfer.setData('application/x-archiviste', JSON.stringify([...F.sel]));
    // pour le bureau Archiviste et les autres applis (Nemo) : les mêmes fichiers, par leur adresse
    try { e.dataTransfer.setData('application/x-archiviste-paths', JSON.stringify([...F.sel])); } catch { /* */ }
    try { e.dataTransfer.setData('text/uri-list', [...F.sel].map((p) => `file://${p.split('/').map(encodeURIComponent).join('/')}`).join('\r\n')); } catch { /* */ }
    e.dataTransfer.effectAllowed = 'copyMove';
  });
  list.addEventListener('dragend', () => { ownDrag = false; dragEnd(); $$('.frow.drop', list).forEach((x) => x.classList.remove('drop')); });
  F.built = true;
}

const FILE_ACTS = {
  up: () => { if (F.search) { clearSearch(); return; } if (F.parent) openDir(F.parent, { select: F.path }); },
  back: () => histGo(-1),
  fwd: () => histGo(1),
  terminal: () => openTerminal(F.path),
  refresh: () => loadDir(),
  newFolder: async () => {
    const name = await promptText({ title: 'Nouveau dossier', label: `Dans ${tildify(F.path)}`, value: 'Nouveau dossier' });
    if (!name) return;
    try { const r = await post('/api/fs/mkdir', { dir: F.path, name }); await loadDir(); selectPath(r.path); }
    catch (e) { toast(e.message, 'err'); }
  },
  newFile: async () => {
    const name = await promptText({ title: 'Nouveau fichier', label: `Dans ${tildify(F.path)}`, value: 'nouveau.md', selectStem: true });
    if (!name) return;
    const path = joinPath(F.path, name);
    try { await post('/api/fs/write', { path, content: '', create_only: true }); await loadDir(); selectPath(path); openEditor(path); }
    catch (e) { toast(e.message, 'err'); }
  },
  upload: () => $('#fUpload').click(),
  sortHere: () => go('sort', { path: F.path }),
  agentHere: (b, e) => agentPicker(b || null, F.path, e),
  chatHere: () => startChat({ atts: [{ path: F.path, name: basename(F.path), kind: 'folder' }], text: 'Voici le contenu de ce dossier. ' }),
  toggleHidden: () => { F.hidden = !F.hidden; $('#fHiddenBtn').classList.toggle('on', F.hidden); loadDir(); },
  togglePreview: () => { F.preview = !F.preview; $('#fPrevBtn').classList.toggle('on', F.preview); $('#fWrap').classList.toggle('nopreview', !F.preview); $('#fPreview').classList.toggle('hidden', !F.preview); renderSelbar(); },
  crumb: (b) => openDir(b.dataset.path),
  sortCol: (b) => { const c = b.dataset.col; if (F.sortBy === c) F.sortDir *= -1; else { F.sortBy = c; F.sortDir = c === 'name' ? 1 : -1; } renderFileList(); },
  rowMenu: (b, e) => {
    const r = b.closest('.frow[data-i]');
    const it = curList()[+r.dataset.i];
    if (!F.sel.has(it.path)) { F.sel = new Set([it.path]); F.anchor = +r.dataset.i; refreshSelection(); }
    const rect = b.getBoundingClientRect();
    rowMenu(rect.left - 180, rect.bottom + 2);
  },
  clearSel: () => { F.sel.clear(); refreshSelection(); },
  selMove: () => moveDialog([...F.sel], false),
  selCopy: () => moveDialog([...F.sel], true),
  selTrash: () => trashItems([...F.sel]),
  selChat: () => startChat({ atts: selectedEntries().map((e) => ({ path: e.path, name: e.name, kind: e.dir ? 'folder' : e.kind })) }),
  clearSearch: () => clearSearch(),
  // panneau d'aperçu
  pvOpen: () => { const e = selectedEntries()[0]; if (e) openEntry(e); },
  pvEdit: () => openEditor(selectedEntries()[0].path),
  pvRaw: () => openWithSystem(selectedEntries()[0].path),
  pvExtract: () => extractArchive(selectedEntries()[0].path),
  pvExtractTo: () => extractTo(selectedEntries()[0].path),
  pvDownload: () => openWithSystem(selectedEntries()[0].path, true),
  openHere: () => openWithSystem(F.path),
  pvRename: () => renameItem(selectedEntries()[0]),
  pvSummary: () => summarizeFile(selectedEntries()[0]),
  pvChat: () => { const e = selectedEntries()[0]; startChat({ atts: [{ path: e.path, name: e.name, kind: e.dir ? 'folder' : e.kind }] }); },
  pvSort: () => go('sort', { path: selectedEntries()[0].path }),
  pvAgent: (b, e) => agentPicker(b, selectedEntries()[0].path, e),
  pvStop: () => { pvAbort?.abort(); },
  pvGrim: () => openInGrimoire(selectedEntries()[0].path),
  newMenu: (b) => menuAt(b, [
    { label: 'Fichier texte', sub: '.md, .txt, script… modifiable ici', icon: 'filePlus', act: FILE_ACTS.newFile },
    { label: 'Document Word (.docx)', sub: hasGrimoire() ? 's\'ouvre dans Grimoire' : 'document vide', icon: 'quill', act: () => newOffice('docx') },
    { label: 'Classeur Excel (.xlsx)', sub: hasGrimoire() ? 's\'ouvre dans Grimoire' : 'classeur vide', icon: 'sheet', act: () => newOffice('xlsx') },
  ]),
};

function curList() { return F.search ? F.search.results : sortedEntries(); }
function sortedEntries() {
  const arr = [...F.entries];
  const k = F.sortBy;
  const d = F.sortDir;
  arr.sort((a, b) => {
    if (a.dir !== b.dir) return a.dir ? -1 : 1;
    if (k === 'size') return d * ((a.size || 0) - (b.size || 0)) || a.name.localeCompare(b.name, 'fr', { numeric: true });
    if (k === 'mtime') return d * (a.mtime - b.mtime);
    return d * a.name.localeCompare(b.name, 'fr', { numeric: true, sensitivity: 'base' });
  });
  return arr;
}
function selectedEntries() { const l = curList(); return l.filter((e) => F.sel.has(e.path)); }

// Historique de navigation, comme Nemo : précédent / suivant (Alt+← / Alt+→, boutons de la souris)
F.back = []; F.fwd = [];
async function openDir(path, { select, history = true } = {}) {
  if (history && F.path && path !== F.path) { F.back.push(F.path); F.back = F.back.slice(-100); F.fwd = []; }
  F.path = path; F.sel.clear(); F.anchor = null; F.focus = null; F.search = null;
  const si = $('#fSearch'); if (si) si.value = '';
  await loadDir();
  if (select) selectPath(select);
  updateHash();
}
async function loadDir() {
  try {
    const r = await api(`/api/fs/list?path=${enc(F.path || '')}${F.hidden ? '&hidden=1' : ''}`);
    F.path = r.path; F.parent = r.parent; F.root = r.root; F.entries = r.entries; F.volumes = r.volumes || [];
    const exists = new Set(r.entries.map((e) => e.path));
    F.sel = new Set([...F.sel].filter((p) => exists.has(p)));
  } catch (e) {
    toast(e.message, 'err');
    if (F.path !== S.home) { F.path = S.home; return loadDir(); }
  }
  renderCrumbs(); renderFileList(); renderPreview(); renderSelbar(); updateHash();
  const bb = $('#fBack'); if (bb) { bb.disabled = !F.back.length; $('#fFwd').disabled = !F.fwd.length; }
}
function histGo(dir) {
  const from = dir < 0 ? F.back : F.fwd;
  const to = dir < 0 ? F.fwd : F.back;
  if (!from.length) return;
  const prev = F.path;
  const target = from.pop();
  to.push(prev);
  openDir(target, { history: false, select: prev && dirname(prev) === target ? prev : undefined });  // en remontant, le dossier d'où l'on vient reste choisi
}
// Barre d'adresse : Ctrl+L, ou un clic à droite du chemin. On peut y taper ~/Documents, un chemin relatif, un fichier.
function editAddress() {
  const c = $('#fCrumbs');
  if (!c || $('input', c)) return;
  c.innerHTML = `<input type="text" class="addr" spellcheck="false" value="${esc(tildify(F.path))}">`;
  const inp = $('input', c);
  inp.focus(); inp.select();
  const done = () => { if (c.contains(inp)) renderCrumbs(); };
  inp.addEventListener('blur', () => setTimeout(done, 120));
  inp.addEventListener('keydown', async (e) => {
    if (e.key === 'Escape') { e.preventDefault(); done(); $('#fList').focus(); return; }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    let v = inp.value.trim().replace(/^file:\/\//, '');
    if (!v) return;
    try { v = decodeURIComponent(v); } catch { /* */ }
    if (v === '~' || v.startsWith('~/')) v = S.home + v.slice(1);
    else if (!v.startsWith('/')) v = joinPath(F.path, v);
    v = v.replace(/\/+$/, '') || '/';
    try { await api(`/api/fs/list?path=${enc(v)}`); }
    catch {
      try { await api(`/api/fs/list?path=${enc(dirname(v))}`); } catch (err) { toast(err.message, 'err'); inp.select(); return; }
      await openDir(dirname(v), { select: v }); $('#fList').focus(); return;  // un fichier : son dossier, le fichier choisi
    }
    await openDir(v);
    $('#fList').focus();
  });
}
function selectPath(p) {
  const i = curList().findIndex((e) => e.path === p);
  if (i < 0) return;
  F.sel = new Set([p]); F.anchor = i; F.focus = i;
  refreshSelection();
  $(`.frow[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest' });
}
function clearSearch() { F.search = null; $('#fSearch').value = ''; F.sel.clear(); renderFileList(); renderPreview(); renderSelbar(); }
let searchSeq = 0;
async function runSearch(q, typing = false) {
  const content = $('#fSearchContent').checked;
  const seq = ++searchSeq;
  if (!typing) $('#fList').innerHTML = `<div class="empty"><span class="spinner"></span><p>Recherche de « ${esc(q)} »${content ? ' (contenu compris)' : ''}…</p></div>`;
  try {
    const r = await api(`/api/fs/search?path=${enc(F.path)}&q=${enc(q)}${content ? '&content=1' : ''}${typing ? '&frais=0' : ''}`);
    if (seq !== searchSeq) return;  // une recherche plus récente est partie entre-temps
    F.search = r; F.sel.clear();
  } catch (e) { if (seq !== searchSeq) return; toast(e.message, 'err'); F.search = null; }
  renderFileList(); renderPreview(); renderSelbar();
}

function renderCrumbs() {
  const roots = S.settings.roots;
  const vols = (F.volumes || []).filter((v) => !roots.includes(v.path));  // clés USB et disques branchés
  $('#fRoot').innerHTML = roots.map((r) => `<option value="${esc(r)}" ${r === F.root ? 'selected' : ''}>${r === S.home ? '🏠 Dossier personnel' : '📁 ' + esc(basename(r))}</option>`).join('')
    + vols.map((v) => `<option value="${esc(v.path)}" ${v.path === F.root ? 'selected' : ''}>💾 ${esc(v.nom)}</option>`).join('');
  const root = F.root || S.home;
  const segs = [`<button data-act="crumb" data-path="${esc(root)}">${root === S.home ? ic('home', 'sm') : esc(basename(root))}</button>`];
  const rest = (F.path || '').slice(root.length).split('/').filter(Boolean);
  let acc = root;
  for (const r of rest) { acc = joinPath(acc, r); segs.push(`<span class="slash">›</span><button data-act="crumb" data-path="${esc(acc)}">${esc(r)}</button>`); }
  $('#fCrumbs').innerHTML = segs.join('');
  $('#fCrumbs').scrollLeft = 9999;
}

// Une recherche arrêtée avant la fin le dit, au lieu de laisser croire qu'il n'y a rien d'autre.
function searchCutText(r) {
  if (!r || !r.incomplet) return '';
  if (r.incomplet === 'contenu') return `Le texte de ${r.a_lire} fichier(s) n'est pas encore indexé : d'autres documents peuvent contenir ce mot (l'index se complète tout seul).`;
  if (r.incomplet === 'temps') return `Recherche arrêtée au bout de ${String(r.delai).replace('.', ',')} s : tout n'a pas été parcouru. Ouvre un sous-dossier plus précis et relance.`;
  return 'Seuls les premiers résultats sont affichés : précise le mot cherché.';
}
function renderFileList() {
  const list = curList();
  const el = $('#fList');
  const arrow = (c) => (F.sortBy === c ? (F.sortDir > 0 ? ' ↑' : ' ↓') : '');
  let html = '';
  if (F.search) {
    const why = searchCutText(F.search);
    html += `<div class="banner" style="margin:8px 4px">${ic('search')}<div class="grow"><b>${list.length}${F.search.tronque ? '+' : ''} résultat(s)</b> pour « ${esc(F.search.query)} » dans ${esc(tildify(F.search.base))}${why ? `<br><span class="search-cut">${ic('alert', 'sm')} ${esc(why)}</span>` : ''}</div><button class="btn sm" data-act="clearSearch">Effacer</button></div>`;
  }
  html += `<div class="frow head"><span></span><span></span><span class="sortable" data-act="sortCol" data-col="name">Nom${arrow('name')}</span><span class="sortable size" data-act="sortCol" data-col="size">Taille${arrow('size')}</span><span class="sortable date" data-act="sortCol" data-col="mtime">Modifié${arrow('mtime')}</span><span></span></div>`;
  if (!list.length) {
    html += `<div class="empty">${ic(F.search ? 'search' : 'folder')}<p>${F.search ? (F.search.incomplet ? 'Rien trouvé pour l\'instant : la recherche n\'a pas pu tout parcourir.' : 'Aucun résultat.') : 'Ce dossier est vide.'}</p>${F.search ? '' : '<p class="faint">Glisse des fichiers ici pour les importer.</p>'}</div>`;
  }
  html += list.map((e, i) => `<div class="frow ${F.sel.has(e.path) ? 'sel' : ''} ${e.hidden ? 'hiddenf' : ''}" data-i="${i}" draggable="true" title="${esc(e.name)}">
      <input type="checkbox" data-act="chk" ${F.sel.has(e.path) ? 'checked' : ''} tabindex="-1">
      ${fileIcon(e)}
      <div class="name"><span>${esc(e.name)}</span>${F.search ? `<span class="where ellipsis">${esc(tildify(dirname(e.path)))}</span>` : ''}${e.link ? '<span class="faint" title="Lien symbolique">↪</span>' : ''}</div>
      <div class="size">${e.dir ? '' : fmtSize(e.size)}</div>
      <div class="date">${fmtDate(e.mtime)}</div>
      <button class="icon-btn sm more" data-act="rowMenu" tabindex="-1" title="Actions">${ic('more')}</button>
    </div>${e.extrait ? `<div class="extract">… ${esc(e.extrait)} …</div>` : ''}`).join('');
  el.innerHTML = html;
}
function refreshSelection() {
  const list = curList();
  $$('#fList .frow[data-i]').forEach((r) => {
    const e = list[+r.dataset.i];
    const on = F.sel.has(e.path);
    r.classList.toggle('sel', on);
    r.classList.toggle('cut', clipCut(e.path));
    r.classList.toggle('focus', +r.dataset.i === F.focus);
    const c = $('input', r); if (c) c.checked = on;
  });
  renderPreview(); renderSelbar();
}
function onRowClick(e) {
  const r = e.target.closest('.frow[data-i]');
  if (!r) { if (e.target === $('#fList')) { F.sel.clear(); refreshSelection(); } return; }
  if (e.target.closest('[data-act="rowMenu"]')) return;
  const i = +r.dataset.i;
  const it = curList()[i];
  if (e.target.closest('[data-act="chk"]')) {
    F.sel.has(it.path) ? F.sel.delete(it.path) : F.sel.add(it.path);
    F.anchor = i;
  } else if (e.shiftKey && F.anchor !== null) {
    const [a, b] = [Math.min(F.anchor, i), Math.max(F.anchor, i)];
    F.sel = new Set(curList().slice(a, b + 1).map((x) => x.path));
  } else if (e.ctrlKey || e.metaKey) {
    F.sel.has(it.path) ? F.sel.delete(it.path) : F.sel.add(it.path);
    F.anchor = i;
  } else {
    F.sel = new Set([it.path]); F.anchor = i;
  }
  F.focus = i;
  refreshSelection();
}
function onFileKey(e) {
  if (e.target.matches('input, textarea, select')) return;
  const list = curList();
  const sel = selectedEntries();
  if (e.key === 'Delete' && sel.length) { e.preventDefault(); trashItems(sel.map((x) => x.path)); }
  else if (e.key === 'F2' && sel.length === 1) { e.preventDefault(); renameItem(sel[0]); }
  else if (e.key === 'Enter' && e.altKey) { e.preventDefault(); showProperties(sel.length ? sel.map((x) => x.path) : [F.path]); }
  else if (e.key === 'Enter' && sel.length === 1) { e.preventDefault(); openEntry(sel[0]); }
  else if (e.key === 'Backspace') { e.preventDefault(); FILE_ACTS.up(); }
  else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); F.sel = new Set(list.map((x) => x.path)); refreshSelection(); }
  else if ((e.ctrlKey || e.metaKey) && 'xXcC'.includes(e.key) && e.key.length === 1 && sel.length && !String(getSelection()).trim()) {
    e.preventDefault(); clipSet(sel.map((x) => x.path), e.key.toLowerCase() === 'x' ? 'couper' : 'copier');
  } else if ((e.ctrlKey || e.metaKey) && (e.key === 'v' || e.key === 'V')) { e.preventDefault(); pasteHere(); }
  else if (e.key === 'Escape') { F.sel.clear(); refreshSelection(); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    if (!list.length) return;
    let i = F.focus ?? -1;
    i = e.key === 'ArrowDown' ? Math.min(list.length - 1, i + 1) : Math.max(0, i - 1);
    F.focus = i;
    if (e.shiftKey && F.anchor !== null) {
      const [a, b] = [Math.min(F.anchor, i), Math.max(F.anchor, i)];
      F.sel = new Set(list.slice(a, b + 1).map((x) => x.path));
    } else { F.sel = new Set([list[i].path]); F.anchor = i; }
    refreshSelection();
    $(`#fList .frow[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest' });
  }
}
const EDITABLE_KINDS = new Set(['text', 'code', 'file']);
const isEditable = (e) => !e.dir && (EDITABLE_KINDS.has(e.kind) || ['md', 'txt', 'csv', 'tsv', 'json', 'svg', 'html', 'xml'].includes(e.ext));
function openEntry(e) {
  if (!e) return;
  if (e.dir) return openDir(e.path);
  if (hasGrimoire() && GRIM_FIRST.has(e.ext)) return openInGrimoire(e.path);
  if (isEditable(e) && (e.size || 0) < 2e6) return openEditor(e.path);
  if (e.kind === 'archive') return openArchive(e.path);  // zip, rar, 7z, tar… (une BD .cbz s'ouvre dans sa liseuse)
  openWithSystem(e.path);
}
// Coller dans le dossier affiché (ou dans un dossier précis, depuis son menu)
async function pasteHere(dest = F.path) {
  const r = await clipPaste(dest, dest === F.path ? 'ici' : null);
  if (!r) return;
  if (dest === F.path && r.ok.length) F.sel = new Set(r.ok.map((x) => x.vers));
  F.search ? runSearch(F.search.query) : loadDir();
}
function rowMenu(x, y) {
  const sel = selectedEntries();
  if (!sel.length) return;
  const one = sel.length === 1 ? sel[0] : null;
  const items = [];
  if (one) {
    items.push({ label: one.dir ? 'Ouvrir' : isEditable(one) ? 'Modifier' : 'Ouvrir', icon: one.dir ? 'folder' : isEditable(one) ? 'pencil' : 'external', kbd: 'Entrée', act: () => openEntry(one) });
    if (!one.dir && isEditable(one)) items.push({ label: 'Ouvrir avec l\'application par défaut', icon: 'external', act: () => openWithSystem(one.path) });
    if (!one.dir) items.push({ label: 'Ouvrir avec…', icon: 'app', act: () => openWithAt(one.path, x, y) });
    if (isArchive(one)) {
      items.push({ label: 'Extraire ici', icon: 'archive', act: () => extractArchive(one.path) });
      items.push({ label: 'Extraire vers…', icon: 'archive', act: () => extractTo(one.path) });
    }
    items.push({ label: 'Afficher dans le gestionnaire de fichiers', icon: 'folder', act: () => openWithSystem(one.path, true) });
    if (grimOk(one) && !GRIM_FIRST.has(one.ext)) items.push({ label: 'Ouvrir dans Grimoire', icon: 'quill', act: () => openInGrimoire(one.path) });
    items.push({ label: 'Renommer', icon: 'pencil', kbd: 'F2', act: () => renameItem(one) });
    if (!one.dir) items.push({ label: 'Versions précédentes…', icon: 'undo', act: () => showVersions(one.path, () => (F.search ? runSearch(F.search.query) : loadDir())) });
  }
  items.push('sep');
  items.push({ label: 'Couper', icon: 'move', kbd: 'Ctrl+X', act: () => clipSet(sel.map((x) => x.path), 'couper') });
  items.push({ label: 'Copier', icon: 'copy', kbd: 'Ctrl+C', act: () => clipSet(sel.map((x) => x.path), 'copier') });
  if (one?.dir && CLIP.paths.length) items.push({ label: `Coller dans ce dossier (${CLIP.paths.length})`, icon: 'download', act: () => pasteHere(one.path) });
  items.push({ label: 'Déplacer vers…', icon: 'move', act: () => moveDialog(sel.map((x) => x.path), false) });
  items.push({ label: 'Copier vers…', icon: 'copy', act: () => moveDialog(sel.map((x) => x.path), true) });
  items.push({ label: 'Copier le chemin', icon: 'copy', act: () => copyText(sel.map((x) => x.path).join('\n')) });
  if (one) items.push({ label: 'Épingler aux raccourcis', icon: 'star', act: () => pinItem(one) });
  items.push('sep');
  if (one && !one.dir) items.push({ label: 'Résumer avec l\'IA', icon: 'sparkles', act: () => summarizeFile(one) });
  items.push({ label: sel.length > 1 ? 'En discuter (joindre)' : 'En discuter', icon: 'chat', act: FILE_ACTS.selChat });
  items.push({ label: 'Compresser…', icon: 'archive', act: () => compressDialog(sel.map((x) => x.path)) });
  if (one && one.dir) items.push({ label: 'Ouvrir un terminal ici', icon: 'code', act: () => openTerminal(one.path) });
  if (one && one.dir) {
    items.push({ label: 'Trier avec l\'IA', icon: 'sparkles', act: () => go('sort', { path: one.path }) });
    items.push({ label: 'Lancer un agent ici…', icon: 'bot', act: () => agentPicker(null, one.path, { clientX: x, clientY: y }) });
  }
  items.push({ label: 'Propriétés', icon: 'info', kbd: 'Alt+Entrée', act: () => showProperties(sel.map((x) => x.path)) });
  items.push('sep');
  items.push({ label: 'Mettre à la corbeille', icon: 'trash', kbd: 'Suppr', danger: true, act: () => trashItems(sel.map((x) => x.path)) });
  showMenu(x, y, items);
}
function renderSelbar() {
  const n = F.sel.size;
  const bar = $('#fSelbar');
  if (!bar) return;
  const show = n > 1 || (n === 1 && !F.preview);
  bar.classList.toggle('hidden', !show);
  if (!show) return;
  const size = selectedEntries().reduce((s, e) => s + (e.size || 0), 0);
  bar.innerHTML = `<b>${n} sélectionné(s)</b><span class="muted">${fmtSize(size)}</span><span class="tbsep"></span>
    <button class="btn sm" data-act="selMove">${ic('move', 'sm')} Déplacer…</button>
    <button class="btn sm" data-act="selCopy">${ic('copy', 'sm')} Copier…</button>
    <button class="btn sm" data-act="selChat">${ic('chat', 'sm')} En discuter</button>
    <button class="btn sm danger" data-act="selTrash">${ic('trash', 'sm')} Corbeille</button>
    <span class="grow"></span><button class="btn ghost sm" data-act="clearSel">Tout désélectionner</button>`;
}

let pvSeq = 0;
let pvAbort = null;
async function renderPreview() {
  const pv = $('#fPreview');
  if (!pv || !F.preview) return;
  const seq = ++pvSeq;
  pvAbort?.abort(); pvAbort = null;
  const sel = selectedEntries();
  if (!sel.length) {
    const list = F.search ? F.search.results : F.entries;
    const dirs = list.filter((e) => e.dir).length;
    const files = list.length - dirs;
    const size = list.reduce((s, e) => s + (e.size || 0), 0);
    pv.innerHTML = `<div class="pv-title"><span class="ficon folder">${ic('folder')}</span><div class="grow"><h3>${esc(F.search ? 'Résultats de recherche' : basename(F.path) || '/')}</h3><span class="muted" style="font-size:12.5px">${dirs} dossier(s), ${files} fichier(s) · ${fmtSize(size)}</span></div></div>
      <div class="pv-actions">
        <button class="btn sm" data-act="sortHere">${ic('sparkles', 'sm')} Trier ce dossier</button>
        <button class="btn sm" data-act="agentHere">${ic('bot', 'sm')} Agent ici</button>
        <button class="btn sm" data-act="chatHere">${ic('chat', 'sm')} En discuter</button>
        <button class="btn sm" data-act="openHere" title="Ouvrir ce dossier dans le gestionnaire de fichiers">${ic('external', 'sm')} Nemo</button>
      </div>
      <div class="muted" style="font-size:12.5px;line-height:1.7;margin-top:6px">
        <b>Astuces</b><br>
        Double-clic : ouvrir · clic droit : actions<br>
        <span class="kbd">Suppr</span> corbeille · <span class="kbd">F2</span> renommer · <span class="kbd">⌫</span> dossier parent<br>
        <span class="kbd">Ctrl</span> / <span class="kbd">Maj</span> + clic : sélection multiple<br>
        <span class="kbd">Ctrl</span>+<span class="kbd">X</span> couper · <span class="kbd">Ctrl</span>+<span class="kbd">C</span> copier · <span class="kbd">Ctrl</span>+<span class="kbd">V</span> coller ici<br>
        Glisse un fichier sur un dossier pour l'y déplacer (<span class="kbd">Ctrl</span> pour le copier) — depuis cette liste, le bureau ou Nemo.
      </div>`;
    return;
  }
  if (sel.length > 1) {
    const size = sel.reduce((s, e) => s + (e.size || 0), 0);
    pv.innerHTML = `<div class="pv-title"><span class="ficon">${ic('copy')}</span><div><h3>${sel.length} éléments</h3><span class="muted">${fmtSize(size)}</span></div></div>
      <div class="pv-actions"><button class="btn sm" data-act="selMove">${ic('move', 'sm')} Déplacer…</button><button class="btn sm" data-act="selCopy">${ic('copy', 'sm')} Copier…</button><button class="btn sm" data-act="selChat">${ic('chat', 'sm')} En discuter</button><button class="btn sm danger" data-act="selTrash">${ic('trash', 'sm')} Corbeille</button></div>
      <div class="col" style="gap:3px">${sel.slice(0, 40).map((e) => `<div class="row" style="font-size:12.5px">${fileIcon(e)}<span class="ellipsis">${esc(e.name)}</span></div>`).join('')}${sel.length > 40 ? `<span class="faint">… et ${sel.length - 40} autres</span>` : ''}</div>`;
    return;
  }
  const e = sel[0];
  const typeLbl = e.dir ? 'Dossier' : (e.ext ? e.ext.toUpperCase() : 'Fichier');
  const actions = e.dir
    ? `<button class="btn sm primary" data-act="pvOpen">${ic('folder', 'sm')} Ouvrir</button>
       <button class="btn sm" data-act="pvSort">${ic('sparkles', 'sm')} Trier</button>
       <button class="btn sm" data-act="pvAgent">${ic('bot', 'sm')} Agent ici</button>
       <button class="btn sm" data-act="pvChat">${ic('chat', 'sm')} En discuter</button>`
    : `${grimOk(e) && GRIM_FIRST.has(e.ext) ? `<button class="btn sm primary" data-act="pvGrim">${ic('quill', 'sm')} Ouvrir dans Grimoire</button>`
        : isEditable(e) ? `<button class="btn sm primary" data-act="pvEdit">${ic('pencil', 'sm')} Modifier</button>` : `<button class="btn sm primary" data-act="pvRaw">${ic('external', 'sm')} Ouvrir</button>`}
       ${grimOk(e) && !GRIM_FIRST.has(e.ext) ? `<button class="btn sm" data-act="pvGrim" title="Ouvrir dans Grimoire">${ic('quill', 'sm')} Grimoire</button>` : ''}
       <button class="btn sm" data-act="pvSummary">${ic('sparkles', 'sm')} Résumer</button>
       <button class="btn sm" data-act="pvChat">${ic('chat', 'sm')} En discuter</button>
       ${isEditable(e) ? `<button class="btn sm" data-act="pvRaw" title="Ouvrir avec l'application par défaut">${ic('external', 'sm')}</button>` : ''}
       <button class="btn sm" data-act="pvDownload" title="Afficher dans le gestionnaire de fichiers">${ic('folder', 'sm')}</button>`;
  pv.innerHTML = `<div class="pv-title">${fileIcon(e)}<div class="grow"><h3>${esc(e.name)}</h3></div></div>
    <div class="pv-actions">${actions}
      <button class="btn sm" data-act="pvRename" title="Renommer (F2)">${ic('pencil', 'sm')}</button>
      <button class="btn sm" data-act="selMove" title="Déplacer">${ic('move', 'sm')}</button>
      <button class="btn sm danger" data-act="selTrash" title="Corbeille (Suppr)">${ic('trash', 'sm')}</button>
    </div>
    <dl><dt>Type</dt><dd>${esc(typeLbl)}</dd>${e.dir ? '' : `<dt>Taille</dt><dd>${fmtSize(e.size)}</dd>`}<dt>Modifié</dt><dd>${DF_FULL.format(toDate(e.mtime))}</dd><dt>Chemin</dt><dd class="mono">${esc(tildify(e.path))}</dd></dl>
    <div id="pvAi"></div>
    <div id="pvBody"></div>`;
  if (e.dir) return;
  const body = $('#pvBody', pv);
  const url = rawUrl(e.path);
  if (e.kind === 'image') body.innerHTML = `<div class="pv-media"><img src="${url}" alt=""></div>`;
  else if (e.kind === 'video') body.innerHTML = `<div class="pv-media"><video src="${url}" controls preload="metadata"></video></div>`;
  else if (e.kind === 'audio') body.innerHTML = `<div class="pv-media"><audio src="${url}" controls preload="metadata"></audio></div>`;
  else if (e.ext === 'pdf') {
    body.innerHTML = `<div class="pv-media" style="cursor:zoom-in" title="Ouvrir dans le lecteur PDF"><img src="${thumbUrl(e.path)}" alt="Première page"></div><p class="faint" style="font-size:12px;margin:6px 0 0">Première page — clique pour ouvrir le PDF.</p>`;
    const img = $('img', body);
    img.onerror = () => { body.innerHTML = '<p class="muted">Aperçu indisponible (installe poppler-utils, ou le PDF est protégé).</p>'; };
    $('.pv-media', body).onclick = () => openWithSystem(e.path);
  }
  else if (isArchive(e) && e.kind === 'archive') {
    body.innerHTML = '<div class="row muted"><span class="spinner"></span> Lecture de l\'archive…</div>';
    try {
      const a = await api(`/api/archive?path=${enc(e.path)}`);
      if (seq !== pvSeq) return;
      body.innerHTML = `${archiveSummary(a)}${a.outil ? '' : `<div class="row" style="gap:6px;margin-bottom:8px"><button class="btn sm primary" data-act="pvExtract">${ic('archive', 'sm')} Extraire ici</button><button class="btn sm" data-act="pvExtractTo">Extraire vers…</button></div>${archiveListHtml({ ...a, entrees: a.entrees.slice(0, 300) })}`}`;
    } catch (err) { if (seq === pvSeq) body.innerHTML = `<p class="muted">${esc(err.message)}</p>`; }
  }
  else if ((e.size || 0) < 25e6 && !['archive', 'app', 'font'].includes(e.kind)) {
    body.innerHTML = '<div class="row muted"><span class="spinner"></span> Lecture…</div>';
    try {
      const r = await api(`/api/fs/read?path=${enc(e.path)}`);
      if (seq !== pvSeq) return;
      if (r.content) {
        const txt = r.content.length > 20000 ? r.content.slice(0, 20000) + '\n…' : r.content;
        body.innerHTML = `${r.format && r.format !== 'texte' ? `<span class="badge">${esc(r.format)} — texte extrait</span>` : ''}<pre class="pv-text"></pre>`;
        $('.pv-text', body).textContent = txt;
      } else body.innerHTML = `<p class="muted">${r.content === '' ? 'Document vide.' : esc(r.format || 'Pas d\'aperçu disponible.')}</p>`;
    } catch (err) { if (seq === pvSeq) body.innerHTML = `<p class="muted">${esc(err.message)}</p>`; }
  } else body.innerHTML = '<p class="muted">Pas d\'aperçu pour ce type de fichier.</p>';
}

async function summarizeFile(e) {
  if (!F.preview) FILE_ACTS.togglePreview();
  if (!F.sel.has(e.path) || F.sel.size !== 1) { F.sel = new Set([e.path]); refreshSelection(); await new Promise((r) => setTimeout(r, 30)); }
  const box = $('#pvAi');
  if (!box) return;
  box.innerHTML = `<div class="pv-ai"><div class="row" style="margin-bottom:6px"><b class="grow">${ic('sparkles', 'sm')} Résumé</b><span class="spinner"></span><button class="btn ghost sm" data-act="pvStop">Arrêter</button></div><div class="md"></div></div>`;
  const out = $('.md', box);
  let txt = '';
  pvAbort = new AbortController();
  try {
    await streamApi('/api/ai/run', {
      prompt: 'Résume ce fichier en français : de quoi il s\'agit, puis les points clés en liste courte. Si c\'est un document administratif, indique les dates, montants et actions à mener.',
      attachments: [e.path],
    }, (ev) => {
      if (ev.t === 'content') { txt += ev.d; out.innerHTML = md(txt); }
      if (ev.t === 'error') out.innerHTML = `<div class="err-box">${esc(ev.d)}</div>`;
    }, pvAbort.signal);
  } catch (err) { if (err.name !== 'AbortError') out.innerHTML = `<div class="err-box">${esc(err.message)}</div>`; }
  $('.spinner', box)?.remove(); $('[data-act=pvStop]', box)?.remove();
  if (txt) {
    const row = document.createElement('div');
    row.className = 'row'; row.style.marginTop = '8px';
    row.innerHTML = `<button class="btn sm">${ic('copy', 'sm')} Copier</button><button class="btn sm">${ic('save', 'sm')} Enregistrer</button>`;
    row.children[0].onclick = () => copyText(txt);
    row.children[1].onclick = () => saveTextToFile(txt, `Résumé - ${e.name.replace(/\.[^.]+$/, '')}.md`);
    $('.pv-ai', box).append(row);
  }
  pvAbort = null;
}

async function renameItem(e) {
  const name = await promptText({ title: 'Renommer', label: tildify(dirname(e.path)), value: e.name, selectStem: !e.dir, ok: 'Renommer' });
  if (!name || name === e.name) return;
  try { const r = await post('/api/fs/rename', { path: e.path, new_name: name }); await (F.search ? runSearch(F.search.query) : loadDir()); selectPath(r.vers); }
  catch (err) { toast(err.message, 'err'); }
}
async function moveDialog(paths, copy) {
  if (!paths.length) return;
  const dest = await pickPath({ title: `${copy ? 'Copier' : 'Déplacer'} ${paths.length} élément(s) vers…`, mode: 'dir', okLabel: copy ? 'Copier ici' : 'Déplacer ici' });
  if (dest) moveItems(paths, dest, copy);
}
async function moveItems(paths, dest, copy) {
  try {
    const r = await post('/api/fs/move', { paths, dest_dir: dest, copy });
    if (r.erreurs.length) toast(r.erreurs.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
    if (r.tache) taskStarted(r.tache);  // grosse copie : elle se suit en bas à droite
    if (r.ok.length) toast(`${r.ok.length} élément(s) ${copy ? 'copié(s)' : 'déplacé(s)'} vers ${basename(dest)}`, 'ok', { label: 'Y aller', action: () => openDir(dest) });
  } catch (e) { toast(e.message, 'err'); }
  F.search ? runSearch(F.search.query) : loadDir();
}
async function trashItems(paths) {
  if (!paths.length) return;
  const anyDir = paths.some((p) => curList().find((e) => e.path === p)?.dir);
  if (paths.length > 1 || anyDir) {
    const ok = await ask(`Mettre ${paths.length > 1 ? `ces ${paths.length} éléments` : `« ${basename(paths[0])} »`} à la corbeille ?\nTu pourras les restaurer depuis la Corbeille (ici ou dans Nemo).`, { ok: 'Mettre à la corbeille', danger: true });
    if (!ok) return;
  }
  try {
    const r = await post('/api/fs/trash', { paths });
    if (r.erreurs.length) toast(r.erreurs.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
    if (r.ok.length) {
      const ids = r.ok.map((x) => x.corbeille);
      toast(`${r.ok.length} élément(s) mis à la corbeille`, 'ok', {
        label: 'Annuler', action: async () => { reportRestore(await post('/api/trash/restore', { ids })); loadDir(); },
      });
    }
  } catch (e) { toast(e.message, 'err'); }
  F.sel.clear();
  F.search ? runSearch(F.search.query) : loadDir();
}
// ── Tâches de fond : extractions, compressions, longues copies (commun aux deux fenêtres) ──
// Elles s'affichent en bas à droite avec leur progression ; la page est prévenue quand l'une se termine
// (taskDone) pour rafraîchir ce qu'elle montre.
const TK = { list: [], timer: 0, hidden: new Set(), running: new Set(), loaded: false };
let taskDone = null;    // la page : rafraîchir ce qui a changé
let taskReveal = (p) => go('files', { path: dirname(p), select: p });  // « Afficher » : le bureau la remplace
window.archivisteTaches = () => tasksPoll();
const TASK_ICON = { extraction: 'archive', compression: 'archive', copie: 'copy', deplacement: 'move' };
function taskStarted(t) {
  if (!t) return;
  TK.list = [...TK.list.filter((x) => x.id !== t.id), t];
  TK.running.add(t.id);
  renderTasks();
  clearTimeout(TK.timer);
  TK.timer = setTimeout(tasksPoll, 400);
}
async function tasksPoll() {
  clearTimeout(TK.timer);
  let r;
  try { r = await api('/api/taches'); } catch { TK.timer = setTimeout(tasksPoll, 3000); return; }
  const first = !TK.loaded;
  TK.loaded = true;
  for (const t of r.taches) {
    if (t.etat === 'en cours') TK.running.add(t.id);
    else if (TK.running.has(t.id)) {
      TK.running.delete(t.id);
      taskDone?.(t);
      // comme Nemo : une tâche réussie s'efface d'elle-même ; une erreur reste jusqu'à ce qu'on la ferme
      if (t.etat !== 'erreur') setTimeout(() => { TK.hidden.add(t.id); TK.list = TK.list.filter((x) => x.id !== t.id); renderTasks(); }, t.etat === 'finie' ? 15000 : 6000);
    } else if (first) TK.hidden.add(t.id);  // terminée avant l'ouverture de la page
  }
  TK.list = r.taches.filter((t) => !TK.hidden.has(t.id));
  renderTasks();
  if (TK.list.some((t) => t.etat === 'en cours')) TK.timer = setTimeout(tasksPoll, 500);
}
const pct = (t) => (t.total > 0 ? Math.min(100, Math.round((100 * t.fait) / t.total)) : null);
function taskLine(t) {
  const el = Math.max(0.5, (t.maintenant || Date.now() / 1000) - t.debut);
  if (t.etat === 'finie') return t.resultat.length ? `Terminé : « ${esc(basename(t.resultat[0]))} »${t.resultat.length > 1 ? ` et ${t.resultat.length - 1} autre(s)` : ''}` : 'Terminé.';
  if (t.etat === 'annulee') return 'Annulé : rien n\'a été laissé à moitié.';
  if (t.etat === 'erreur') return esc(t.erreur || 'Erreur.');
  if (t.pourcent) return `${pct(t) ?? 0} %${t.detail ? ` · ${esc(t.detail)}` : ''}`;
  const speed = t.fait / el;
  const parts = [t.total > 0 ? `${fmtSize(t.fait)} sur ${fmtSize(t.total)}` : fmtSize(t.fait)];
  if (el > 2 && speed > 0) parts.push(`${fmtSize(speed)}/s`);
  if (t.total > 0 && el > 2 && speed > 0) {
    const left = Math.max(0, (t.total - t.fait) / speed);
    parts.push(left < 60 ? `reste ${Math.ceil(left)} s` : `reste ${Math.ceil(left / 60)} min`);
  }
  return esc(parts.join(' · '));
}
function renderTasks() {
  let box = $('#taches');
  if (!TK.list.length) { box?.remove(); return; }
  if (!box) {
    box = document.createElement('div');
    box.id = 'taches';
    $('#toasts').append(box);
    box.addEventListener('click', onTaskClick);
  }
  const shown = TK.list.slice(-4);  // les plus récentes ; les autres sont résumées
  const more = TK.list.length - shown.length;
  box.innerHTML = (more ? `<div class="tache tk-more">${more} autre${more > 1 ? 's' : ''} tâche${more > 1 ? 's' : ''} : ${TK.list.slice(0, more).filter((t) => t.etat === 'en cours').length} en cours</div>` : '') + shown.map((t) => {
    const p = pct(t);
    const run = t.etat === 'en cours';
    return `<div class="tache ${t.etat === 'en cours' ? 'run' : t.etat}" data-tk="${t.id}">
      <div class="row"><span class="tk-ic">${ic(t.etat === 'erreur' ? 'alert' : t.etat === 'finie' ? 'check' : TASK_ICON[t.genre] || 'file', 'sm')}</span>
        <b class="grow ellipsis" title="${esc(t.titre)}">${esc(t.titre)}</b>
        ${run ? '<button class="btn sm ghost" data-tka="annuler">Annuler</button>' : `<button class="icon-btn sm" data-tka="fermer" title="Fermer">${ic('x', 'sm')}</button>`}</div>
      ${run ? `<div class="tk-bar ${p === null ? 'indet' : ''}"><i style="width:${p ?? 30}%"></i></div>` : ''}
      <div class="tk-sub">${taskLine(t)}</div>
      ${run && t.detail && !t.pourcent ? `<div class="tk-sub faint ellipsis">${esc(t.detail)}</div>` : ''}
      ${t.etat === 'finie' && t.resultat.length ? `<div class="row tk-acts"><button class="btn sm" data-tka="afficher">${ic('folder', 'sm')} Afficher</button>${t.genre === 'extraction' ? `<button class="btn sm" data-tka="ouvrir">${ic('external', 'sm')} Ouvrir</button>` : ''}</div>` : ''}
      ${t.etat === 'erreur' && t.mdp ? `<div class="row tk-acts"><button class="btn sm primary" data-tka="mdp">Saisir le mot de passe…</button></div>` : ''}
    </div>`;
  }).join('');
}
async function onTaskClick(ev) {
  const b = ev.target.closest('[data-tka]');
  if (!b) return;
  const id = b.closest('[data-tk]').dataset.tk;
  const t = TK.list.find((x) => x.id === id);
  if (!t) return;
  const forget = () => { TK.hidden.add(id); TK.list = TK.list.filter((x) => x.id !== id); renderTasks(); post('/api/taches/oublier', { id }).catch(() => {}); };
  switch (b.dataset.tka) {
    case 'annuler': b.disabled = true; b.textContent = 'Arrêt…'; post('/api/taches/annuler', { id }).then(tasksPoll).catch((e) => toast(e.message, 'err')); break;
    case 'fermer': forget(); break;
    case 'afficher': taskReveal(t.resultat[0]); break;
    case 'ouvrir': post('/api/fs/open', { path: t.resultat[0] }).catch((e) => toast(e.message, 'err')); break;
    case 'mdp': {
      const pwd = await promptText({ title: 'Archive protégée', label: `Mot de passe de « ${basename(t.source)} »`, ok: 'Extraire', password: true });
      if (pwd === null) return;
      forget();
      extractArchive(t.source, t.dossier, pwd);
      break;
    }
    default: break;
  }
}

// ── Archives : voir le contenu, extraire, compresser ──
const ARCHIVE_RE = /\.(zip|cbz|cbr|cb7|7z|rar|tar|tgz|tbz2?|txz|tzst|gz|bz2|xz|zst|lz|lzma)$/i;
const isArchive = (e) => !!e && !e.dir && ARCHIVE_RE.test(e.name || basename(e.path || ''));
async function extractArchive(path, dest = dirname(path), mdp = undefined) {
  try { taskStarted((await post('/api/archive/extraire', { path, dest, mdp })).tache); } catch (e) { toast(e.message, 'err'); }
}
async function extractTo(path) {
  const dest = await pickPath({ title: `Extraire « ${basename(path)} » vers…`, mode: 'dir', start: dirname(path), okLabel: 'Extraire ici' });
  if (dest) extractArchive(path, dest);
}
function archiveListHtml(a) {
  const rows = a.entrees.map((x) => {
    const depth = x.nom.split('/').length - 1;
    return `<div class="arc-row" style="padding-left:${8 + depth * 16}px">${ic(x.dossier ? 'folder' : 'file', 'sm')}<span class="grow ellipsis">${esc(basename(x.nom))}</span>${x.dossier || x.taille == null ? '' : `<span class="faint">${fmtSize(x.taille)}</span>`}</div>`;
  }).join('');
  const more = a.nombre > a.entrees.length ? `<div class="faint" style="padding:6px 8px">… et d'autres (seuls les ${a.entrees.length} premiers éléments sont listés)</div>` : '';
  return `<div class="arc-list">${rows}${more}</div>`;
}
function archiveSummary(a) {
  if (a.outil) return `<div class="banner">${ic('info')}<div>${esc(a.outil)}</div></div>`;
  const what = `${a.nombre.toLocaleString('fr-FR')} fichier${a.nombre > 1 ? 's' : ''}${a.taille_connue && a.taille ? ` · ${fmtSize(a.taille)} une fois extrait${a.nombre > 1 ? 's' : ''}` : ''}`;
  return `<p style="margin:0 0 4px">${esc(what)}${a.chiffree ? ` · ${ic('alert', 'sm')} protégée par un mot de passe` : ''}</p>
    <p class="muted" style="margin:0 0 10px;font-size:12.5px">« Extraire ici » crée ${a.dossier_unique ? 'directement' : 'le dossier'} « ${esc(a.dossier_final)} » à côté de l'archive.</p>`;
}
// Double-clic sur une archive : son contenu, et de quoi l'extraire
async function openArchive(path, { launch } = {}) {
  const m = openModal({
    title: basename(path), cls: 'wide',
    body: '<div class="row muted"><span class="spinner"></span> Lecture de l\'archive…</div>',
    footer: `<button class="btn ghost" data-ar="avec">${ic('external', 'sm')} Ouvrir avec…</button><span class="grow"></span>
      <button class="btn" data-ar="vers">Extraire vers…</button><button class="btn primary" data-ar="ici">${ic('archive', 'sm')} Extraire ici</button>`,
  });
  let a = null;
  try { a = await api(`/api/archive?path=${enc(path)}`); m.mb.innerHTML = archiveSummary(a) + (a.outil ? '' : archiveListHtml(a)); }
  catch (e) { m.mb.innerHTML = `<div class="banner danger">${ic('alert')}<div>${esc(e.message)}</div></div>`; }
  if (!a || a.outil) $$('[data-ar="ici"], [data-ar="vers"]', m.el).forEach((b) => { b.disabled = true; });
  m.el.addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-ar]');
    if (!b) return;
    if (b.dataset.ar === 'avec') { const r = b.getBoundingClientRect(); openWithAt(path, r.left, r.top - 8, launch); return; }
    m.close(true);
    if (b.dataset.ar === 'ici') extractArchive(path);
    else extractTo(path);
  });
  return m;
}
function compressDialog(paths) {
  if (!paths.length) return;
  const name = paths.length === 1 ? basename(paths[0]).replace(/\.[^.\/]{1,5}$/, '') || basename(paths[0]) : basename(dirname(paths[0])) || 'Archive';
  const m = openModal({
    title: paths.length === 1 ? `Compresser « ${basename(paths[0])} »` : `Compresser ${paths.length} éléments`,
    body: `<label class="field"><span>Nom de l'archive</span><input type="text" data-cn value="${esc(name)}"></label>
      <label class="field"><span>Format</span><select data-cf><option value="zip">.zip — s'ouvre partout (Windows, Mac, téléphone)</option><option value="tar.gz">.tar.gz — habituel sous Linux, garde les droits des fichiers</option></select></label>
      <p class="muted" style="font-size:12.5px;margin:4px 0 0">L'archive est créée à côté, dans ${esc(tildify(dirname(paths[0])))}.</p>`,
    footer: `<button class="btn" data-close>Annuler</button><button class="btn primary" data-cok>${ic('archive', 'sm')} Compresser</button>`,
  });
  const go2 = async () => {
    const nom = $('[data-cn]', m.el).value.trim();
    if (!nom) return;
    m.close(true);
    try { taskStarted((await post('/api/archive/compresser', { paths, nom, format: $('[data-cf]', m.el).value })).tache); } catch (e) { toast(e.message, 'err'); }
  };
  $('[data-cok]', m.el).onclick = go2;
  $('[data-cn]', m.el).addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); go2(); } });
  setTimeout(() => $('[data-cn]', m.el).select(), 40);
  return m;
}

// ── Ouvrir avec… (et choisir l'application par défaut d'un type de fichier) ──
async function openWithAt(path, x, y, launch) {
  let r;
  try { r = await api(`/api/apps/pour?path=${enc(path)}`); } catch (err) { return toast(err.message, 'err'); }
  if (!r.apps.length) return toast('Aucune application installée ne déclare savoir ouvrir ce type de fichier.');
  const run = launch || (async (a) => {
    try { await post('/api/apps/lancer', { id: a.id, fichiers: [path] }); toast(`Ouverture avec ${a.nom}…`); } catch (e) { toast(e.message, 'err'); }
  });
  showMenu(x, y, [{ header: 'Ouvrir avec' }, ...r.apps.map((a) => ({
    label: a.nom + (a.id === r.defaut ? ' — par défaut' : ''), sub: a.generique || '', icon: 'app', act: () => run(a),
  })), 'sep', { label: 'Toujours ouvrir ce type avec…', icon: 'star', act: () => showMenu(x, y, [
    { header: 'Application par défaut pour ce type' },
    ...r.apps.map((a) => ({ label: a.nom, icon: a.id === r.defaut ? 'check' : 'app', act: async () => {
      try { const d = await post('/api/apps/defaut', { path, id: a.id }); toast(`Les fichiers « ${d.type} » s'ouvriront avec ${d.nom}`, 'ok'); } catch (e) { toast(e.message, 'err'); }
    } })),
  ], { search: r.apps.length > 8 }) }], { search: r.apps.length > 8 });
  return null;
}

// ── Propriétés : taille (aussi d'un dossier), dates, droits ──
const MODE_BITS = [['Propriétaire', 0o400, 0o200, 0o100], ['Groupe', 0o040, 0o020, 0o010], ['Autres', 0o004, 0o002, 0o001]];
async function showProperties(paths) {
  if (!paths.length) return null;
  const m = openModal({ title: paths.length > 1 ? `Propriétés de ${paths.length} éléments` : `Propriétés — ${basename(paths[0])}`, body: '<div class="row muted"><span class="spinner"></span> Calcul…</div>', footer: '<button class="btn" data-close>Fermer</button>' });
  let p;
  try { p = await api(`/api/fs/proprietes?${paths.map((x) => `path=${enc(x)}`).join('&')}`); } catch (e) { m.mb.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return m; }
  const nb = (n) => n.toLocaleString('fr-FR');
  const content = `${fmtSize(p.taille)} (${nb(p.taille)} octets)${p.fichiers + p.dossiers > 1 || p.dossier ? ` — ${nb(p.fichiers)} fichier${p.fichiers > 1 ? 's' : ''}, ${nb(p.dossiers)} dossier${p.dossiers > 1 ? 's' : ''}` : ''}${p.complet ? '' : ' (calcul arrêté au bout de 5 s : au moins)'}`;
  const when = (d) => new Date(d).toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' });
  const rows = [];
  if (p.nombre === 1) {
    rows.push(['Type', `${p.dossier ? 'Dossier' : esc(p.type)}${p.appli ? ` — s'ouvre avec ${esc(p.appli)}` : ''}`]);
    rows.push(['Emplacement', `<span class="mono">${esc(tildify(dirname(p.chemin)))}</span>`]);
    if (p.lien) rows.push(['Lien vers', `<span class="mono">${esc(p.lien)}</span>`]);
  }
  rows.push([p.dossier || p.nombre > 1 ? 'Contenu' : 'Taille', content]);
  if (p.nombre === 1) {
    rows.push(['Modifié', when(p.modifie)], ['Consulté', when(p.acces)], ['Propriétaire', `${esc(p.proprietaire)} (groupe ${esc(p.groupe)})`]);
  }
  if (p.disque) rows.push(['Disque', `${fmtSize(p.disque.libre)} libres sur ${fmtSize(p.disque.total)}`]);
  let perms = '';
  if (p.nombre === 1 && !p.lien) {
    const dis = p.modifiable ? '' : 'disabled';
    perms = `<h3 class="prop-h">Droits${p.modifiable ? '' : ' <span class="faint" style="font-weight:400">(seul le propriétaire peut les changer)</span>'}</h3>
      <div class="perm-grid"><span></span><span>Lecture</span><span>Écriture</span><span>${p.dossier ? 'Ouvrir' : 'Exécution'}</span>
      ${MODE_BITS.map(([who, r, w, x]) => `<span>${who}</span>${[r, w, x].map((bit) => `<label class="check"><input type="checkbox" data-bit="${bit}" ${p.mode & bit ? 'checked' : ''} ${dis || (bit === 0o400 ? 'disabled' : '')}></label>`).join('')}`).join('')}</div>
      ${p.dossier ? '' : `<label class="switch" style="margin-top:10px"><input type="checkbox" data-exe ${p.mode & 0o100 ? 'checked' : ''} ${dis}><i></i>Autoriser l'exécution du fichier comme un programme</label>`}`;
  }
  m.mb.innerHTML = `<dl class="props">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${perms}`;
  let mode = p.mode;
  const apply = async (next) => {
    try { mode = (await post('/api/fs/droits', { path: p.chemin, mode: next })).mode; } catch (e) { toast(e.message, 'err'); }
    $$('[data-bit]', m.el).forEach((c) => { c.checked = !!(mode & +c.dataset.bit); });
    const exe = $('[data-exe]', m.el); if (exe) exe.checked = !!(mode & 0o100);
  };
  m.el.addEventListener('change', (e) => {
    if (e.target.dataset.bit) apply(e.target.checked ? mode | +e.target.dataset.bit : mode & ~+e.target.dataset.bit);
    if (e.target.dataset.exe !== undefined) apply(e.target.checked ? mode | ((mode & 0o444) >> 2) | 0o100 : mode & ~0o111);
  });
  return m;
}
async function openTerminal(path) {
  try { const r = await post('/api/terminal', { path }); toast(`Terminal ouvert dans ${tildify(path)}`); return r; } catch (e) { toast(e.message, 'err'); return null; }
}

// ── Couper / copier / coller des fichiers (commun au bureau et à la fenêtre principale) ──
// Le presse-papiers est tenu par le serveur : ce qui est coupé sur le bureau se colle dans la fenêtre principale,
// et inversement. Sous l'appli, ce qui a été coupé ou copié dans Nemo se colle aussi ici.
const CLIP = { paths: [], mode: 'copier', source: null };
let clipListener = null;  // la page dit comment montrer ce qui est « coupé »
function clipApply(c) { Object.assign(CLIP, { paths: [], mode: 'copier', source: null }, c || {}); clipListener?.(); }
async function clipLoad() { try { clipApply(await api('/api/presse-papiers')); } catch { /* */ } }
const clipCut = (path) => CLIP.mode === 'couper' && CLIP.source === 'archiviste' && CLIP.paths.includes(path);
async function clipSet(paths, mode) {
  if (!paths.length) return;
  try {
    clipApply(await post('/api/presse-papiers', { paths, mode }));
    const n = paths.length > 1;
    const what = n ? `${paths.length} éléments` : `« ${basename(paths[0])} »`;
    toast(mode === 'couper' ? `${what} ${n ? 'coupés' : 'coupé'} — Ctrl+V là où tu veux ${n ? 'les' : 'le'} déplacer`
      : `${what} ${n ? 'copiés' : 'copié'} — Ctrl+V là où tu veux ${n ? 'les' : 'le'} coller`, 'info', { timeout: 3500 });
  } catch (e) { toast(e.message, 'err'); }
}
async function clipPaste(dest, label) {
  let r;
  try { r = await post('/api/presse-papiers/coller', { dest }); } catch (e) { toast(e.message, e.message.startsWith('Rien à coller') ? 'info' : 'err'); return null; }
  if (r.erreurs.length) toast(r.erreurs.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
  if (r.tache) taskStarted(r.tache);
  if (r.ok.length) toast(`${r.ok.length} élément(s) ${r.mode === 'couper' ? 'déplacé(s)' : 'copié(s)'} ${label || `dans ${basename(dest)}`}`, 'ok');
  else if (r.deja && !r.erreurs.length && !r.tache) toast('Déjà dans ce dossier.');
  await clipLoad();
  return r;
}
// Chemins d'une liste d'adresses file:// (ce que donnent Nemo et les autres applis quand on glisse un fichier)
function pathsFromUris(list) {
  return String(list || '').split(/\r?\n/).map((l) => l.trim()).filter((l) => l.startsWith('file://'))
    .map((u) => { try { return decodeURIComponent(new URL(u).pathname); } catch { return null; } }).filter(Boolean);
}
// Glisser-déposer de fichiers. Sous WebKitGTK, la page qui reçoit ne peut lire ni les formats maison ni les
// adresses file:// : les chemins sont donc gardés ici pour un dépôt dans la même page (DRAG_PATHS), et notés
// auprès du serveur pour un dépôt dans l'autre fenêtre ; pour un fichier venu d'une autre appli (Nemo), c'est
// la fenêtre GTK qui les note. dropInfo() les retrouve dans cet ordre.
let DRAG_PATHS = null;
function dragBegin(paths) { DRAG_PATHS = paths.slice(); post('/api/glisse', { paths }).catch(() => {}); }
function dragEnd() { setTimeout(() => { DRAG_PATHS = null; }, 400); }
// Touche Ctrl pendant un glisser (Ctrl = copier, sinon déplacer). WebKitGTK en donne un état périmé dans ses
// événements de glisser : après un premier Ctrl, tous les dépôts suivants se croyaient « avec Ctrl » et copiaient.
// La fenêtre GTK lit donc le clavier elle-même : elle prévient la page (archivisteCtrl) pour l'affichage, et
// note l'état au moment du dépôt, que dropInfo() relit. Hors de l'appli (navigateur), on garde l'événement.
let DRAG_CTRL = null;
window.archivisteCtrl = (on) => { DRAG_CTRL = !!on; };
const dragCopy = (ev) => (DRAG_CTRL === null ? ev.ctrlKey : DRAG_CTRL);
// À appeler au tout début d'un « drop » : { paths, copy }
async function dropInfo(ev) {
  const dt = ev.dataTransfer;
  const local = DRAG_PATHS && DRAG_PATHS.length ? DRAG_PATHS.slice() : draggedPaths(dt);
  const located = [...dt.types].some((t) => t === 'text/uri-list' || t === 'application/x-archiviste-paths');
  const key = dragCopy(ev);
  let g = null;
  try { g = await api('/api/glisse'); } catch { /* */ }
  return { paths: local.length ? local : located ? (g?.paths || []) : [], copy: typeof g?.ctrl === 'boolean' ? g.ctrl : key };
}
function draggedPaths(dt) {
  try { const j = dt.getData('application/x-archiviste-paths'); if (j) return JSON.parse(j); } catch { /* */ }
  let p = pathsFromUris(dt.getData('text/uri-list'));
  if (!p.length) {
    p = String(dt.getData('text/plain') || '').split(/\r?\n/).map((l) => l.trim()).filter((l) => l.startsWith('/') || l.startsWith('file://'))
      .map((l) => (l.startsWith('file://') ? pathsFromUris(l)[0] : l)).filter(Boolean);
  }
  return p;
}

// Restauration depuis la corbeille : ce qui a pu revenir revient, le reste est expliqué.
function reportRestore(r) {
  if (r.ok.length) toast(`${r.ok.length} élément(s) restauré(s)`, 'ok');
  if (r.erreurs.length) toast(`${r.erreurs.length} élément(s) non restauré(s) : ${r.erreurs[0].erreur}`, 'err');
}
async function uploadFiles(fileList, dir) {
  const files = [...fileList];
  if (!files.length) return;
  const t = toast(`Import de ${files.length} fichier(s)…`, 'info', { sticky: true });
  const failed = [];
  for (let k = 0; k < files.length; k++) {
    const f = files[k];
    await new Promise((res) => {
      const x = new XMLHttpRequest();
      x.open('POST', `/api/fs/upload?dir=${enc(dir)}&name=${enc(f.name)}`);
      x.setRequestHeader('X-Archiviste-Token', TOKEN);
      x.upload.onprogress = (ev) => { if (ev.lengthComputable) t.set(`Import ${k + 1}/${files.length} — ${f.name} (${Math.round((ev.loaded / ev.total) * 100)} %)`); };
      x.onload = () => { if (x.status >= 400) failed.push(f.name); res(); };
      x.onerror = () => { failed.push(f.name); res(); };
      x.send(f);
    });
  }
  t.close();
  toast(failed.length ? `Import terminé, ${failed.length} échec(s) : ${failed.join(', ')}` : `${files.length} fichier(s) importé(s)`, failed.length ? 'err' : 'ok');
  if (F.path === dir) loadDir();
}
function agentPicker(btn, folder, ev) {
  const toolAgents = S.agents.filter((a) => a.outils?.length);
  const items = [{ header: `Agent dans ${basename(folder)}` }, ...toolAgents.map((a) => ({
    emoji: a.icone, label: a.nom, sub: a.description, act: () => startChat({ agent_id: a.id, workspace: folder }),
  }))];
  if (!toolAgents.length) items.push({ label: 'Aucun agent avec des outils — crée-en un', act: () => go('agents') });
  if (btn) menuAt(btn, items); else showMenu(ev?.clientX || 200, ev?.clientY || 200, items);
}

// ── Versions précédentes ──
// Archiviste garde une copie d'un fichier chaque fois qu'il le modifie (éditeur, agents, import qui remplace).
// Cette fenêtre les liste, permet de les lire et d'en remettre une ; l'état remplacé est gardé lui aussi.
async function showVersions(path, onRestored) {
  let v;
  try { v = await api(`/api/fs/versions?path=${enc(path)}`); } catch (e) { return toast(e.message, 'err'); }
  const m = openModal({
    title: `Versions précédentes — ${v.nom}`, cls: 'wide',
    body: v.versions.length
      ? `<p class="muted" style="margin:0 0 8px;font-size:13px">Archiviste garde une copie de ce fichier chaque fois qu'il le modifie. Remettre une version ne fait rien perdre : l'état actuel devient lui-même une version.</p>
         <div class="ver-list" data-l></div><div data-pv></div>`
      : `<div class="empty" style="padding:26px 10px">${ic('undo')}<p>Aucune ancienne version de ce fichier.</p><p class="faint">Archiviste en garde une chaque fois qu'il le modifie : éditeur, agents, import qui remplace un fichier.</p></div>`,
    footer: '<button class="btn" data-close>Fermer</button>',
  });
  const list = $('[data-l]', m.el);
  if (!list) return null;
  const when = (d) => new Date(d).toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'medium' });  // à la seconde : deux versions peuvent se suivre de près
  list.innerHTML = (v.actuelle ? `<div class="ver cur"><span class="grow"><b>Version actuelle</b><small>${when(v.actuelle.date)} · ${fmtSize(v.actuelle.taille)}</small></span></div>` : '')
    + v.versions.map((x, i) => `<div class="ver" data-id="${esc(x.id)}"><span class="grow"><b>${when(x.date)}</b><small>${fmtSize(x.taille)}${i === 0 ? ' · la plus récente' : ''}</small></span>
      <button class="btn sm" data-ver="voir">${ic('eye', 'sm')} Voir</button><button class="btn sm primary" data-ver="remettre">${ic('undo', 'sm')} Remettre</button></div>`).join('');
  list.addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-ver]');
    if (!b) return;
    const row = b.closest('.ver');
    const id = row.dataset.id;
    if (b.dataset.ver === 'voir') {
      const pv = $('[data-pv]', m.el);
      pv.innerHTML = '<div class="row muted" style="margin-top:10px"><span class="spinner"></span> Lecture…</div>';
      $$('.ver.on', list).forEach((x) => x.classList.remove('on'));
      row.classList.add('on');
      try {
        const t = await api(`/api/fs/versions/texte?id=${enc(id)}`);
        pv.innerHTML = t.content ? '<pre class="pv-text" style="max-height:300px;margin-top:10px"></pre>' : `<p class="muted" style="margin-top:10px">${t.content === '' ? 'Fichier vide.' : esc(t.format || 'Pas d\'aperçu pour ce type de fichier.')}</p>`;
        if (t.content) $('pre', pv).textContent = t.content + (t.tronque ? '\n…' : '');
      } catch (e) { pv.innerHTML = `<p class="muted" style="margin-top:10px">${esc(e.message)}</p>`; }
      return;
    }
    if (!(await ask(`Remettre la version du ${$('b', row).textContent} à la place de « ${v.nom} » ?\nL'état actuel est gardé : tu pourras y revenir de la même façon.`, { ok: 'Remettre cette version' }))) return;
    try {
      await post('/api/fs/versions/restaurer', { id });
      toast(`« ${v.nom} » est revenu à sa version du ${$('b', row).textContent}`, 'ok');
      m.close(true);
      onRestored?.();
    } catch (e) { toast(e.message, 'err'); }
  });
  return m;
}

// ── Éditeur ──
async function openEditor(path) {
  let r;
  try { r = await api(`/api/fs/read?path=${enc(path)}`); } catch (e) { return toast(e.message, 'err'); }
  if (!r.editable) return toast('Ce fichier ne peut pas être modifié ici (binaire, document Office ou trop gros).', 'err');
  let dirty = false;
  let aiCtrl = null;
  let aiText = '';
  let range = null;
  const m = openModal({
    title: basename(path), cls: 'xl',
    body: `<div class="row wrap">
        <span class="mono muted grow ellipsis" title="${esc(path)}">${esc(tildify(path))}</span>
        <span class="muted" data-e="status" style="font-size:12.5px"></span>
        ${/\.(md|markdown|txt)$/i.test(path) ? `<button class="btn sm" data-e="todocx" title="Crée un .docx mis en forme à côté de ce fichier${hasGrimoire() ? ' et l\'ouvre dans Grimoire' : ''}">${ic('quill', 'sm')} En document Word</button>` : ''}
        <label class="switch"><input type="checkbox" data-e="wrap" checked><i></i>Retour à la ligne</label>
      </div>
      <textarea class="editor-area wrap" data-e="ta" spellcheck="false"></textarea>
      <div class="ai-bar">
        ${ic('wand')}
        <input type="text" data-e="instr" placeholder="Demande à l'IA de modifier le texte : « corrige les fautes », « traduis en anglais », « ajoute une conclusion »…">
        <select data-e="scope" title="Sur quoi travaille l'IA"><option value="all">Tout le texte</option><option value="sel">La sélection</option></select>
        <button class="btn" data-e="run">${ic('sparkles', 'sm')} Lancer</button>
      </div>
      <div class="hidden col" data-e="aiwrap">
        <div class="ai-out" data-e="aiout"></div>
        <div class="row"><button class="btn sm primary" data-e="replace">${ic('check', 'sm')} Remplacer</button><button class="btn sm" data-e="append">Insérer à la suite</button><button class="btn sm" data-e="aicopy">${ic('copy', 'sm')} Copier</button><span class="grow"></span><button class="btn ghost sm" data-e="aiclose">Ignorer</button></div>
      </div>`,
    footer: `<span class="muted" style="font-size:12px"><span class="kbd">Ctrl</span>+<span class="kbd">S</span> pour enregistrer — l'ancienne version est gardée dans les données d'Archiviste.</span><span class="grow"></span>
      <button class="btn ghost" data-e="versions" title="Revenir à un état d'avant">${ic('undo', 'sm')} Versions</button><button class="btn" data-close>Fermer</button><button class="btn primary" data-e="save">${ic('save', 'sm')} Enregistrer</button>`,
    beforeClose: async () => !dirty || ask('Des modifications ne sont pas enregistrées. Fermer quand même ?', { ok: 'Fermer sans enregistrer', danger: true }),
    onClose: () => aiCtrl?.abort(),
  });
  const q = (k) => $(`[data-e="${k}"]`, m.el);
  const ta = q('ta');
  ta.value = r.content;
  const status = (t) => { q('status').textContent = t; };
  status(`${r.encoding !== 'utf-8' ? `encodage ${r.encoding} · ` : ''}${fmtSize(r.size)}`);
  ta.addEventListener('input', () => { if (!dirty) { dirty = true; status('● modifié'); } });
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); ta.setRangeText('    ', ta.selectionStart, ta.selectionEnd, 'end'); ta.dispatchEvent(new Event('input')); }
  });
  q('wrap').addEventListener('change', (e) => ta.classList.toggle('wrap', e.target.checked));
  const save = async () => {
    try {
      const w = await post('/api/fs/write', { path, content: ta.value, encoding: r.encoding });
      dirty = false; status('✓ enregistré');
      if (w.encodage !== r.encoding) {  // un caractère que l'ancien encodage ne sait pas écrire (€, œ, émoji…)
        toast(`Ce fichier était en ${r.encoding} : il est maintenant enregistré en ${w.encodage.toUpperCase()}, car le texte contient des caractères que l'ancien encodage ne connaît pas.`, 'info', { timeout: 9000 });
        r.encoding = w.encodage;
      }
      if (F.path === dirname(path)) loadDir();
    } catch (e) { toast(e.message, 'err'); }
  };
  q('save').onclick = save;
  q('versions').onclick = async () => {
    if (dirty && !(await ask('Des modifications ne sont pas enregistrées. Les enregistrer avant de regarder les versions ?', { ok: 'Enregistrer' }))) return;
    if (dirty) await save();
    showVersions(path, async () => {  // version restaurée : l'éditeur montre le texte revenu
      try { const again = await api(`/api/fs/read?path=${enc(path)}`); ta.value = again.content; r.encoding = again.encoding; dirty = false; status('✓ version restaurée'); } catch { /* */ }
      if (F.path === dirname(path)) loadDir();
    });
  };
  if (q('todocx')) q('todocx').onclick = async () => {
    try {
      const r = await post('/api/office/new', { path: path.replace(/\.[^./]+$/, '') + '.docx', kind: 'docx', content: ta.value, open: true, unique: true });
      toast(r.ouvert === 'grimoire' ? `Ouvert dans Grimoire : ${basename(r.path)}` : `Créé : ${basename(r.path)}`, 'ok');
      if (F.path === dirname(path)) loadDir();
    } catch (e) { toast(e.message, 'err'); }
  };
  m.el.addEventListener('keydown', (e) => { if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } });
  const runAi = async () => {
    const instr = q('instr').value.trim();
    if (!instr) return q('instr').focus();
    const useSel = q('scope').value === 'sel' && ta.selectionEnd > ta.selectionStart;
    range = useSel ? [ta.selectionStart, ta.selectionEnd] : null;
    const text = useSel ? ta.value.slice(...range) : ta.value;
    aiText = '';
    q('aiwrap').classList.remove('hidden');
    q('aiout').textContent = '…';
    q('run').disabled = true;
    aiCtrl = new AbortController();
    try {
      await streamApi('/api/ai/run', {
        system: 'Tu es un assistant d\'écriture et de code. Tu appliques exactement la consigne au texte fourni et tu renvoies uniquement le texte résultat, sans commentaire, sans introduction et sans balises ```.',
        prompt: `Consigne : ${instr}`, texte: text, temperature: 0.3,
      }, (ev) => {
        if (ev.t === 'content') { aiText += ev.d; q('aiout').textContent = aiText; q('aiout').scrollTop = 1e9; }
        if (ev.t === 'error') q('aiout').textContent = '⚠ ' + ev.d;
      }, aiCtrl.signal);
    } catch (e) { if (e.name !== 'AbortError') q('aiout').textContent = '⚠ ' + e.message; }
    aiText = aiText.replace(/^\s*```[\w-]*\n([\s\S]*?)\n?```\s*$/, '$1');
    q('run').disabled = false;
  };
  q('run').onclick = runAi;
  q('instr').addEventListener('keydown', (e) => { if (e.key === 'Enter') runAi(); });
  q('replace').onclick = () => {
    if (!aiText) return;
    if (range) ta.setRangeText(aiText, range[0], range[1], 'select'); else ta.value = aiText;
    ta.dispatchEvent(new Event('input')); q('aiwrap').classList.add('hidden');
  };
  q('append').onclick = () => { if (!aiText) return; ta.value += (ta.value.endsWith('\n') ? '\n' : '\n\n') + aiText; ta.dispatchEvent(new Event('input')); q('aiwrap').classList.add('hidden'); };
  q('aicopy').onclick = () => copyText(aiText);
  q('aiclose').onclick = () => { aiCtrl?.abort(); q('aiwrap').classList.add('hidden'); };
  setTimeout(() => ta.focus(), 50);
}

RENDER.files = (opts = {}) => {
  if (!F.built) buildFiles();
  if (opts.path) openDir(opts.path, { select: opts.select }).then(() => { if (opts.props) showProperties([opts.select || opts.path]); });
  else if (!F.path) openDir(S.home);
  else loadDir();
  setTimeout(() => $('#fList')?.focus({ preventScroll: true }), 30);
};

// ═════════════════════════════════════════════════════════════
//  TRI INTELLIGENT
// ═════════════════════════════════════════════════════════════
const T = S.sort;
const SORT_MODES = [
  ['ai', 'Avec l\'IA'], ['type', 'Par type'], ['date', 'Par mois'], ['type_date', 'Type + année'],
];
function buildSort() {
  const v = $('#view-sort');
  v.innerHTML = `
    <div class="vhead"><h1>Tri intelligent</h1><span class="sub">L'Archiviste propose un rangement, tu valides avant que quoi que ce soit ne bouge.</span></div>
    <div class="vbody"><div class="sort-grid">
      <div id="sBanner"></div>
      <div class="card">
        <h2>Dossier à ranger</h2>
        <div class="pathbox"><input type="text" id="sPath" spellcheck="false"><button class="btn" data-act="pick">${ic('folder', 'sm')} Choisir…</button></div>
        <h3>Méthode</h3>
        <div class="seg" id="sMode">${SORT_MODES.map(([k, l]) => `<button data-act="mode" data-mode="${k}">${l}</button>`).join('')}</div>
        <p class="muted" id="sModeHelp" style="font-size:12.5px;margin:8px 0 0"></p>
        <div id="sAiOpts">
          <h3>Consignes pour l'IA</h3>
          <div class="col">
            <select id="sPrompt"></select>
            <textarea id="sConsignes" rows="3" placeholder="Ex. : range par thème (Administratif, Travail, Photos, Projets…) ; les factures dans Administratif/Factures."></textarea>
            <label class="check"><input type="checkbox" id="sContent"> Lire le début de chaque fichier (plus précis, plus lent)</label>
          </div>
        </div>
        <div style="margin-top:10px"><label class="check"><input type="checkbox" id="sRecursive"> Inclure les fichiers des sous-dossiers</label></div>
        <div class="row" style="margin-top:16px">
          <button class="btn primary" data-act="analyse" id="sGo">${ic('sparkles', 'sm')} Analyser le dossier</button>
          <button class="btn hidden" data-act="cancel" id="sCancel">Arrêter</button>
          <span id="sProgressTxt" class="muted" style="font-size:13px"></span>
        </div>
        <div class="progress hidden" id="sProgress" style="margin-top:10px"><div></div></div>
      </div>
      <div class="card hidden" id="sPlanCard"></div>
      <div class="card"><h2>${ic('undo')} Journal des tris</h2><div id="sJournal" class="muted">Chargement…</div></div>
    </div></div>
    <datalist id="sFolders"></datalist>`;
  v.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b || !v.contains(b)) return;
    const fn = SORT_ACTS[b.dataset.act];
    if (fn) { e.preventDefault(); fn(b, e); }
  });
  v.addEventListener('dblclick', (e) => {
    const chip = e.target.closest('[data-act="chipFilter"]');
    if (chip && chip.dataset.folder) renameGroup(chip.dataset.folder);
  });
  $('#sPath').addEventListener('change', (e) => { T.path = e.target.value.trim(); });
  $('#sConsignes').addEventListener('input', (e) => { T.consignes = e.target.value; });
  $('#sContent').addEventListener('change', (e) => { T.content = e.target.checked; });
  $('#sRecursive').addEventListener('change', (e) => { T.recursive = e.target.checked; });
  $('#sPrompt').addEventListener('change', (e) => {
    const p = S.prompts.find((x) => x.id === e.target.value);
    if (p) { T.consignes = p.contenu; $('#sConsignes').value = p.contenu; post(`/api/prompts/${p.id}/used`); }
    e.target.value = '';
  });
  // délégation pour le tableau du plan
  v.addEventListener('change', (e) => {
    const row = e.target.closest('tr[data-i]');
    if (!row) return;
    const p = T.plan[+row.dataset.i];
    if (e.target.type === 'checkbox') { p.on = e.target.checked; row.classList.toggle('off', !p.on); }
    else { p.dossier = e.target.value.trim(); p.on = !!p.dossier; row.classList.toggle('off', !p.on); $('input[type=checkbox]', row).checked = p.on; }
    renderPlanSummary();
  });
  T.built = true;
}
const SORT_ACTS = {
  pick: async () => { const d = await pickPath({ title: 'Dossier à ranger', start: T.path || F.path }); if (d) { T.path = d; $('#sPath').value = d; } },
  mode: (b) => { T.mode = b.dataset.mode; renderSortForm(); },
  analyse: () => analyseSort(),
  cancel: () => { T.cancel = true; },
  all: () => { T.plan.forEach((p) => { if (p.dossier) p.on = true; }); renderPlan(); },
  none: () => { T.plan.forEach((p) => { p.on = false; }); renderPlan(); },
  chipFilter: (b) => { T.filter = T.filter === b.dataset.folder ? null : b.dataset.folder; renderPlan(); },
  apply: () => applySort(),
  undo: (b) => undoSort(b.dataset.id),
  openBase: () => go('files', { path: T.path }),
  dismiss: () => { T.result = null; renderPlan(); },
};
function renderSortForm() {
  $('#sPath').value = T.path || '';
  $$('#sMode button').forEach((b) => b.classList.toggle('on', b.dataset.mode === T.mode));
  $('#sAiOpts').classList.toggle('hidden', T.mode !== 'ai');
  const model = S.settings.model;
  $('#sModeHelp').innerHTML = {
    ai: `<b>${esc(model)}</b> propose un sous-dossier pour chaque fichier (par lots de 15), en suivant tes consignes.`,
    type: 'Images, Documents, Vidéos, Musique, Archives, Logiciels, Code… selon l\'extension. Instantané, sans IA.',
    date: 'Un dossier par année puis par mois (ex. 2024/2024-05), selon la date de modification. Sans IA.',
    type_date: 'Par type puis par année (ex. Images/2024). Sans IA.',
  }[T.mode];
  $('#sConsignes').value = T.consignes;
  $('#sContent').checked = T.content;
  $('#sRecursive').checked = T.recursive;
  const tri = S.prompts.filter((p) => /tri/i.test(p.categorie));
  const others = S.prompts.filter((p) => !/tri/i.test(p.categorie));
  $('#sPrompt').innerHTML = `<option value="">📜 Charger un prompt enregistré…</option>`
    + (tri.length ? `<optgroup label="Tri">${tri.map((p) => `<option value="${p.id}">${esc(p.titre)}</option>`).join('')}</optgroup>` : '')
    + (others.length ? `<optgroup label="Autres">${others.map((p) => `<option value="${p.id}">${esc(p.titre)}</option>`).join('')}</optgroup>` : '');
  $('#sBanner').innerHTML = T.mode === 'ai' ? ollamaBanner() : '';
}
const slim = (f) => ({ name: f.name, rel: f.rel, size: f.size, mtime: f.mtime, extrait: f.extrait });
function setSortRunning(on, txt = '') {
  T.running = on;
  $('#sGo').disabled = on;
  $('#sCancel').classList.toggle('hidden', !on);
  $('#sProgress').classList.toggle('hidden', !on);
  $('#sProgressTxt').textContent = txt;
}
async function analyseSort() {
  T.path = $('#sPath').value.trim();
  if (!T.path) return toast('Choisis d\'abord un dossier.', 'err');
  T.cancel = false; T.result = null; T.filter = null; T.plan = [];
  setSortRunning(true, 'Inventaire des fichiers…');
  $('#sProgress div').style.width = '3%';
  try {
    T.scan = await post('/api/sort/scan', { path: T.path, recursive: T.recursive, content: T.mode === 'ai' && T.content });
  } catch (e) { setSortRunning(false); return toast(e.message, 'err'); }
  const files = T.scan.files;
  if (!files.length) { setSortRunning(false); renderPlan(); return toast('Aucun fichier à ranger dans ce dossier.', 'info'); }
  if (T.mode !== 'ai') {
    const rules = await post('/api/sort/rules', { files, mode: T.mode });
    T.plan = files.map((f, i) => ({ f, dossier: rules[i].dossier, raison: '', on: true }));
  } else {
    T.plan = files.map((f) => ({ f, dossier: '', raison: '', on: false, pending: true }));
    renderPlan();
    const B = 15;
    const t0 = Date.now();
    for (let i = 0; i < files.length; i += B) {
      if (T.cancel) break;
      const n = Math.min(files.length, i + B);
      const eta = i ? Math.round(((Date.now() - t0) / i) * (files.length - i) / 1000) : null;
      setSortRunning(true, `Lot ${Math.floor(i / B) + 1}/${Math.ceil(files.length / B)} — fichiers ${i + 1} à ${n} sur ${files.length}${eta ? ` · environ ${eta < 90 ? eta + ' s' : Math.round(eta / 60) + ' min'} restantes` : ''}`);
      $('#sProgress div').style.width = `${Math.max(3, (i / files.length) * 100)}%`;
      const batch = files.slice(i, n);
      const proposes = [...new Set(T.plan.map((p) => p.dossier).filter(Boolean))];
      try {
        const r = await post('/api/sort/ai', { files: batch.map(slim), consignes: T.consignes, existants: T.scan.existants, proposes });
        r.resultats.forEach((res, j) => {
          const p = T.plan[i + j];
          p.pending = false;
          if (res) { p.dossier = res.dossier; p.raison = res.raison; p.on = true; } else p.raison = 'Pas de proposition (à compléter)';
        });
      } catch (e) {
        batch.forEach((_, j) => { const p = T.plan[i + j]; p.pending = false; p.raison = '⚠ ' + e.message; });
        toast(e.message, 'err');
        if (/injoignable|introuvable|installé/i.test(e.message)) break;
      }
      renderPlan();
    }
    T.plan.forEach((p) => { if (p.pending) { p.pending = false; p.raison = 'Non analysé (arrêté)'; } });
  }
  // fichiers déjà au bon endroit
  T.plan.forEach((p) => { if (p.dossier && dirname('/' + p.f.rel).slice(1) === p.dossier) { p.on = false; p.raison = 'Déjà rangé ici'; } });
  setSortRunning(false);
  renderPlan();
}
function planGroups() {
  const g = new Map();
  T.plan.forEach((p) => { if (p.on && p.dossier) g.set(p.dossier, (g.get(p.dossier) || 0) + 1); });
  return [...g.entries()].sort((a, b) => b[1] - a[1]);
}
function renderPlanSummary() {
  const groups = planGroups();
  const n = groups.reduce((s, [, c]) => s + c, 0);
  const chips = $('#sChips');
  if (chips) {
    chips.innerHTML = groups.map(([f, c]) => `<span class="chip ${T.filter === f ? 'on' : ''}" data-act="chipFilter" data-folder="${esc(f)}" title="Clic : filtrer · double-clic : renommer ce dossier">${ic('folder', 'sm')} ${esc(f)} <b>${c}</b></span>`).join('')
      + (T.filter ? '<span class="chip" data-act="chipFilter" data-folder="">Tout afficher</span>' : '');
  }
  const btn = $('#sApply');
  if (btn) { btn.disabled = !n || T.running; btn.innerHTML = `${ic('check', 'sm')} Ranger ${n} fichier(s) dans ${groups.length} dossier(s)`; }
  const dl = $('#sFolders');
  if (dl) dl.innerHTML = [...new Set([...(T.scan?.existants || []), ...T.plan.map((p) => p.dossier).filter(Boolean)])].map((f) => `<option value="${esc(f)}">`).join('');
}
function renderPlan() {
  const card = $('#sPlanCard');
  if (T.result) {
    const r = T.result;
    card.classList.remove('hidden');
    card.innerHTML = `<h2>${ic('check')} Tri effectué</h2>
      <p><b>${r.deplaces}</b> fichier(s) rangé(s) dans ${esc(tildify(T.path))}.</p>
      ${r.erreurs.length ? `<div class="err-box" style="margin-bottom:10px">${r.erreurs.length} erreur(s) :<br>${r.erreurs.slice(0, 10).map((x) => `${esc(basename(x.fichier || ''))} — ${esc(x.erreur)}`).join('<br>')}</div>` : ''}
      <div class="row"><button class="btn primary" data-act="openBase">${ic('folder', 'sm')} Voir le dossier</button>
      ${r.journal_id ? `<button class="btn" data-act="undo" data-id="${r.journal_id}">${ic('undo', 'sm')} Annuler ce tri</button>` : ''}
      <span class="grow"></span><button class="btn ghost" data-act="dismiss">Fermer</button></div>`;
    return;
  }
  if (!T.plan.length) { card.classList.add('hidden'); return; }
  card.classList.remove('hidden');
  const rows = T.plan.map((p, i) => ({ p, i })).filter(({ p }) => !T.filter || p.dossier === T.filter);
  card.innerHTML = `<h2>Plan de rangement <span class="badge">${T.plan.length} fichier(s)</span></h2>
    <div class="row wrap" id="sChips" style="margin-bottom:12px"></div>
    <div class="row" style="margin-bottom:8px"><button class="btn sm" data-act="all">Tout cocher</button><button class="btn sm" data-act="none">Tout décocher</button>
      <span class="muted" style="font-size:12.5px">Tu peux corriger chaque dossier proposé. Double-clic sur une pastille pour renommer un dossier entier.</span></div>
    <div class="plan-scroll"><table class="plan-table"><thead><tr><th style="width:30px"></th><th>Fichier</th><th style="width:30px"></th><th style="width:34%">Ranger dans</th><th>Pourquoi</th></tr></thead><tbody>
    ${rows.map(({ p, i }) => `<tr data-i="${i}" class="${p.on ? '' : 'off'}">
      <td><input type="checkbox" ${p.on ? 'checked' : ''} ${p.pending ? 'disabled' : ''}></td>
      <td class="f"><div>${fileIcon(p.f)}<span title="${esc(p.f.rel)}">${esc(p.f.rel)}</span></div></td>
      <td class="faint">→</td>
      <td>${p.pending ? '<span class="spinner"></span>' : `<input type="text" list="sFolders" value="${esc(p.dossier)}" placeholder="(ne pas déplacer)">`}</td>
      <td class="why">${esc(p.raison || '')}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="row" style="margin-top:14px"><button class="btn primary" id="sApply" data-act="apply"></button><span class="muted" style="font-size:12.5px">Aucun fichier n'est écrasé ; chaque tri peut être annulé depuis le journal.</span></div>`;
  renderPlanSummary();
}
async function renameGroup(folder) {
  const name = await promptText({ title: 'Renommer le dossier proposé', label: `Pour tous les fichiers prévus dans « ${folder} »`, value: folder, ok: 'Renommer' });
  if (!name || name === folder) return;
  T.plan.forEach((p) => { if (p.dossier === folder) p.dossier = name; });
  if (T.filter === folder) T.filter = name;
  renderPlan();
}
async function applySort() {
  const moves = T.plan.filter((p) => p.on && p.dossier).map((p) => ({ path: p.f.path, dossier: p.dossier }));
  if (!moves.length) return;
  const groups = planGroups().length;
  if (!(await ask(`Déplacer ${moves.length} fichier(s) dans ${groups} dossier(s) de « ${basename(T.path)} » ?\nTu pourras annuler ce tri depuis le journal.`, { ok: 'Ranger' }))) return;
  try {
    T.result = await post('/api/sort/apply', { base: T.path, moves, mode: T.mode });
    T.plan = [];
    toast(`${T.result.deplaces} fichier(s) rangé(s)`, 'ok');
  } catch (e) { return toast(e.message, 'err'); }
  renderPlan(); loadJournal();
}
async function undoSort(id) {
  if (!(await ask('Remettre tous les fichiers de ce tri à leur place d\'origine ?', { ok: 'Annuler le tri' }))) return;
  try {
    const r = await post('/api/sort/undo', { id });
    toast(`${r.restaures} fichier(s) remis en place${r.erreurs.length ? `, ${r.erreurs.length} erreur(s)` : ''}`, r.erreurs.length ? 'err' : 'ok');
    if (T.result?.journal_id === id) T.result = null;
  } catch (e) { toast(e.message, 'err'); }
  renderPlan(); loadJournal();
}
async function loadJournal() {
  try { T.journal = await api('/api/sort/journal'); } catch { T.journal = []; }
  const modes = { ai: 'IA', type: 'par type', date: 'par mois', type_date: 'type + année' };
  $('#sJournal').innerHTML = T.journal.length ? T.journal.map((j) => `<div class="journal-item">
      <div class="grow"><b>${esc(tildify(j.base))}</b> <span class="badge">${modes[j.mode] || 'tri'}</span><br>
      <span class="muted" style="font-size:12.5px">${DF_FULL.format(new Date(j.date))} · ${j.nb} fichier(s) · ${esc(j.apercu.join(', '))}${j.nb > 4 ? '…' : ''}</span></div>
      ${j.annule ? '<span class="badge">annulé</span>' : `<button class="btn sm" data-act="undo" data-id="${j.id}">${ic('undo', 'sm')} Annuler</button>`}
    </div>`).join('') : '<span class="muted">Aucun tri pour l\'instant.</span>';
}
RENDER.sort = (opts = {}) => {
  if (!T.built) buildSort();
  if (opts.path) { T.path = opts.path; T.plan = []; T.result = null; }
  if (!T.path) T.path = F.path || S.home;
  renderSortForm(); renderPlan(); loadJournal();
};

// ═════════════════════════════════════════════════════════════
//  DISCUSSION
// ═════════════════════════════════════════════════════════════
const C = S.chat;
const cur = () => C.conv || C.draft;
function buildChat() {
  const v = $('#view-chat');
  v.innerHTML = `<div class="chat">
    <aside class="convs">
      <div class="top"><button class="btn primary" data-act="newConv">${ic('plus', 'sm')} Nouvelle discussion</button><input type="search" id="cFilter" placeholder="Rechercher une discussion…"></div>
      <div class="list" id="cList"></div>
    </aside>
    <div class="chat-main">
      <div class="chat-head" id="cHead"></div>
      <div class="messages" id="cMsgs"><div class="msgs-inner" id="cInner"></div></div>
      <div class="composer-wrap"><div class="composer">
        <div class="atts" id="cAtts"></div>
        <textarea id="cInput" rows="1" placeholder="Écris à l'Archiviste…"></textarea>
        <div class="bar">
          <button class="icon-btn" data-act="attach" title="Joindre des fichiers ou dossiers">${ic('clip')}</button>
          <button class="icon-btn" data-act="promptsMenu" title="Insérer un prompt enregistré">${ic('prompt')}</button>
          <span class="hint" id="cHint"><span class="kbd">Entrée</span> envoyer · <span class="kbd">Maj</span>+<span class="kbd">Entrée</span> nouvelle ligne</span>
          <span class="grow"></span>
          <button class="btn primary send-btn" data-act="send" id="cSend" title="Envoyer">${ic('send')}</button>
        </div>
      </div></div>
    </div></div>`;
  v.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b || !v.contains(b)) return;
    const fn = CHAT_ACTS[b.dataset.act];
    if (fn) { e.preventDefault(); fn(b, e); } else if (chatAction(b, { conv: () => C.conv, send: sendMessage })) e.preventDefault();
  });
  const inp = $('#cInput');
  const grow = () => { inp.style.height = 'auto'; inp.style.height = Math.min(inp.scrollHeight, 240) + 'px'; };
  inp.addEventListener('input', grow);
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(); }
  });
  $('#cFilter').addEventListener('input', (e) => { C.filter = e.target.value.toLowerCase(); renderConvList(); });
  $('#cMsgs').addEventListener('scroll', () => { const m = $('#cMsgs'); C.stick = m.scrollHeight - m.scrollTop - m.clientHeight < 120; });
  C.stick = true;
  C.built = true;
}
const CHAT_ACTS = {
  newConv: () => startChat({}),
  openConv: (b) => openConv(b.dataset.id),
  delConv: async (b, e) => {
    e.stopPropagation();
    const c = C.convs.find((x) => x.id === b.dataset.id);
    if (!(await ask(`Supprimer la discussion « ${c?.titre || ''} » ?`, { ok: 'Supprimer', danger: true }))) return;
    await post(`/api/conversations/${b.dataset.id}/delete`);
    if (C.conv?.id === b.dataset.id) { C.conv = null; C.draft = freshDraft(); renderChatAll(); }
    loadConvs();
  },
  send: () => (C.busy ? stopChat() : sendMessage()),
  attach: async () => {
    const paths = await pickPath({ title: 'Joindre à la discussion', mode: 'files' });
    if (!paths) return;
    for (const p of paths) if (!C.atts.find((a) => a.path === p)) C.atts.push({ path: p, name: basename(p), kind: guessKind(p) });
    renderAtts();
  },
  rmAtt: (b) => { C.atts.splice(+b.dataset.i, 1); renderAtts(); },
  promptsMenu: (b) => {
    if (!S.prompts.length) return toast('Aucun prompt enregistré : crée-en dans l\'onglet Prompts.');
    const sorted = [...S.prompts].sort((a, c) => (c.favori - a.favori) || (c.utilisations || 0) - (a.utilisations || 0));
    const r = b.getBoundingClientRect();
    const el = showMenu(r.left, r.top, sorted.map((p) => ({ label: (p.favori ? '★ ' : '') + p.titre, sub: p.categorie, act: () => insertPrompt(p) })), { search: true });
    el.style.top = Math.max(8, r.top - el.offsetHeight - 6) + 'px';
  },
  rename: async () => {
    if (!C.conv) return;
    const t = await promptText({ title: 'Renommer la discussion', value: C.conv.titre || '' });
    if (!t) return;
    try { C.conv = await post(`/api/conversations/${C.conv.id}`, { titre: t }); } catch (e) { return toast(e.message, 'err'); }
    renderChatHead(); loadConvs();
  },
  ws: async () => {
    const a = agentById(cur().agent_id);
    const d = await pickPath({ title: 'Dossier de travail de l\'agent', start: cur().workspace || a?.dossier || S.home });
    if (d) updateCur({ workspace: d });
  },
  convMenu: (b) => menuAt(b, [
    { label: 'Renommer', icon: 'pencil', act: CHAT_ACTS.rename },
    { label: 'Exporter en Markdown…', icon: 'save', act: exportConv },
    'sep',
    { label: 'Supprimer la discussion', icon: 'trash', danger: true, act: () => CHAT_ACTS.delConv({ dataset: { id: C.conv.id } }, { stopPropagation() {} }) },
  ]),
  sugg: (b) => {
    const s = SUGGESTIONS[+b.dataset.i];
    s.run();
  },
  // messages : copier, enregistrer, Word, Excel, régénérer, réessayer, validations → chatAction (commun au volet)
  asPrompt: (b) => editPrompt(null, { contenu: msgText(+b.dataset.m), categorie: 'Divers' }),
};
function guessKind(p) {
  const ext = (p.split('.').pop() || '').toLowerCase();
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return 'image';
  if (!p.includes('.') || p.endsWith('/')) return 'folder';
  return 'file';
}
function msgText(i) { return C.conv?.messages?.[i]?.content || ''; }

const SUGGESTIONS = [
  { t: 'Ranger mes téléchargements', d: 'Le Rangeur organise ~/Téléchargements', run: () => suggestAgent('Rangeur', 'Téléchargements', 'Range ce dossier : regarde ce qu\'il contient, propose-moi un plan clair, puis range.') },
  { t: 'Résumer un document', d: 'Choisis un PDF, un Word ou un texte', run: async () => { const p = await pickPath({ title: 'Document à résumer', mode: 'files' }); if (p) startChat({ atts: p.map((x) => ({ path: x, name: basename(x), kind: guessKind(x) })), text: 'Résume ce document en quelques points clés.' }); } },
  { t: 'Trouver les doublons', d: 'Le Nettoyeur cherche ce qui prend de la place', run: () => suggestAgent('Nettoyeur', '', 'Trouve les doublons dans ce dossier et dis-moi combien de place je peux récupérer. Ne supprime rien sans me le proposer.') },
  { t: 'Écrire une note', d: 'Le Rédacteur crée un fichier Markdown', run: () => suggestAgent('Rédacteur', 'Documents', 'Crée un fichier notes/idees.md avec une liste de mes idées de projets : ') },
];
async function suggestAgent(name, sub, text) {
  const a = S.agents.find((x) => x.nom === name);
  let ws = '';
  if (sub) { try { const r = await api(`/api/fs/list?path=${enc(joinPath(S.home, sub))}`); ws = r.path; } catch { ws = ''; } }
  startChat({ agent_id: a?.id || null, workspace: ws, text });
}
function startChat({ agent_id = null, workspace = '', text = '', atts = [] } = {}) {
  C.conv = null;
  C.draft = freshDraft({ agent_id, workspace });
  C.atts = atts;
  go('chat');
  const inp = $('#cInput');
  inp.value = text;
  inp.dispatchEvent(new Event('input'));
  inp.focus();
  inp.setSelectionRange(text.length, text.length);
}
async function loadConvs() {
  try { C.convs = await api('/api/conversations'); } catch { C.convs = []; }
  renderConvList();
}
function renderConvList() {
  const el = $('#cList');
  if (!el) return;
  const list = C.convs.filter((c) => !C.filter || (c.titre || '').toLowerCase().includes(C.filter));
  if (!list.length) { el.innerHTML = `<div class="empty" style="padding:30px 10px">${C.filter ? 'Aucune discussion trouvée.' : 'Pas encore de discussion.'}</div>`; return; }
  const now = new Date();
  const d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const group = (c) => { const t = new Date(c.modifie).getTime(); return t >= d0 ? 'Aujourd\'hui' : t >= d0 - 864e5 ? 'Hier' : t >= d0 - 7 * 864e5 ? '7 derniers jours' : t >= d0 - 30 * 864e5 ? '30 derniers jours' : 'Plus ancien'; };
  let last = '';
  el.innerHTML = list.map((c) => {
    const g = group(c);
    const head = g !== last ? `<div class="conv-group">${g}</div>` : '';
    last = g;
    const a = agentById(c.agent_id);
    return `${head}<div class="conv-item ${C.conv?.id === c.id ? 'on' : ''}" data-act="openConv" data-id="${c.id}">
      <span class="ic">${a ? esc(a.icone) : ic('chat', 'sm')}</span>
      <div class="grow" style="min-width:0"><div class="t">${esc(c.titre || 'Nouvelle discussion')}</div><small>${a ? esc(a.nom) + ' · ' : ''}${fmtDate(c.modifie)}</small></div>
      <button class="icon-btn sm" data-act="delConv" data-id="${c.id}" title="Supprimer">${ic('trash', 'sm')}</button></div>`;
  }).join('');
}
async function openConv(id) {
  if (C.busy) return toast('Attends la fin de la réponse (ou clique sur Stop).');
  try { C.conv = await api(`/api/conversations/${id}`); } catch (e) { toast(e.message, 'err'); C.conv = null; }
  C.atts = [];
  renderChatAll();
  updateHash();
}
async function updateCur(patch) {
  if (C.busy) { toast('Attends la fin de la réponse (ou clique sur Stop).'); renderChatHead(); return; }
  if (C.conv) {
    try { C.conv = await post(`/api/conversations/${C.conv.id}`, patch); } catch (e) { toast(e.message, 'err'); }
  } else Object.assign(C.draft, patch);
  renderChatHead();
  if ('agent_id' in patch) { renderMessages(); loadConvs(); }
}
function renderChatAll() { renderChatHead(); renderMessages(); renderAtts(); renderConvList(); }
function renderChatHead() {
  const c = cur();
  const a = agentById(c.agent_id);
  const models = (S.status?.models || []).map((m) => m.name);
  const defModel = a?.modele || S.settings.model;
  if (c.modele && !models.includes(c.modele)) models.push(c.modele);
  const thinkOn = c.think ?? (a ? a.think : S.settings.think);
  const ws = c.workspace || a?.dossier || '';
  $('#cHead').innerHTML = `
    <div class="title ellipsis" ${C.conv ? 'data-act="rename" title="Renommer"' : ''}>${esc(C.conv?.titre || 'Nouvelle discussion')}</div>
    ${a?.outils?.length ? `<span class="ws-chip" data-act="ws" title="Dossier dans lequel l'agent a le droit d'agir — clique pour changer">${ic('folder', 'sm')}<span class="ellipsis">${esc(ws ? tildify(ws) : 'Tous tes dossiers autorisés')}</span></span>` : ''}
    <select id="cAgent" title="Agent">
      <option value="">💬 Discussion libre</option>
      ${S.agents.map((x) => `<option value="${x.id}" ${x.id === c.agent_id ? 'selected' : ''}>${esc(x.icone)} ${esc(x.nom)}</option>`).join('')}
    </select>
    <select id="cModel" title="Modèle">
      <option value="">${esc(defModel)} (défaut)</option>
      ${models.filter((m) => m !== defModel).map((m) => `<option value="${esc(m)}" ${m === c.modele ? 'selected' : ''}>${esc(m)}</option>`).join('')}
    </select>
    <label class="switch" title="Le modèle réfléchit avant de répondre : plus lent, parfois plus juste"><input type="checkbox" id="cThink" ${thinkOn ? 'checked' : ''}><i></i>Réflexion</label>
    ${C.conv ? `<button class="icon-btn" data-act="convMenu" title="Plus d'actions">${ic('more')}</button>` : ''}`;
  $('#cAgent').onchange = (e) => updateCur({ agent_id: e.target.value || null, workspace: '' });
  $('#cModel').onchange = (e) => updateCur({ modele: e.target.value });
  $('#cThink').onchange = (e) => updateCur({ think: e.target.checked });
  $('#cInput').placeholder = a ? `Demande quelque chose à ${a.nom}…` : 'Écris à l\'Archiviste…';
}
function renderAtts() {
  const el = $('#cAtts');
  if (!el) return;
  el.innerHTML = C.atts.map((a, i) => `<span class="att" title="${esc(a.path)}">${a.kind === 'image' ? `<img src="${rawUrl(a.path)}" alt="">` : a.kind === 'folder' ? ic('folder', 'sm') : ic('file', 'sm')}<span>${esc(a.name)}</span><button class="icon-btn sm" data-act="rmAtt" data-i="${i}" title="Retirer">${ic('x', 'sm')}</button></span>`).join('');
}
async function insertPrompt(p) {
  const text = await fillVars(p.contenu, p.titre);
  if (text === null) return;
  const inp = $('#cInput');
  const s = inp.selectionStart ?? inp.value.length;
  inp.setRangeText(text, s, inp.selectionEnd ?? s, 'end');
  inp.dispatchEvent(new Event('input'));
  inp.focus();
  post(`/api/prompts/${p.id}/used`).catch(() => {});
}
const avatarHtml = (a) => `<div class="avatar">${a ? esc(a.icone) : '<img src="/favicon.svg" alt="" width="34" height="34">'}</div>`;
function stepHtml(s) {
  const st = s.pending ? '<span class="spinner"></span>' : s.waiting ? ic('alert', 'sm') : s.refuse ? ic('x', 'sm') : s.ok ? ic('check', 'sm') : ic('alert', 'sm');
  const cls = s.pending || s.waiting ? '' : s.refuse ? 'refused' : s.ok ? 'ok' : 'err';
  return `<div class="step ${cls}" data-step="${esc(s.id || '')}"><span class="st">${st}</span><span class="lbl">${esc(toolLabel(s.name))}</span><span class="desc" title="${esc(s.description || '')}">${esc(s.description || '')}</span><span class="res" title="${esc(s.summary || '')}">${esc(s.waiting ? 'en attente de ta validation' : s.summary || '')}</span></div>`;
}
// Erreur de l'IA : gardée dans la discussion (rôle « error »), donc toujours là après le rafraîchissement.
// « Réessayer » n'est proposé que sur la dernière, et seulement si recommencer peut aboutir.
function errorHtml(text, retry) {
  return `<div class="err-box err-row"><span class="err-txt">${ic('alert', 'sm')} ${esc(text)}</span>${retry ? `<button class="btn sm" data-act="retry" title="Relancer la même demande">${ic('refresh', 'sm')} Réessayer</button>` : ''}</div>`;
}
function confirmHtml(pending) {
  return `<div class="confirm-card">
    <div class="ttl">${ic('alert', 'sm')} L'agent demande ta validation avant d'agir</div>
    ${pending.map((p) => `<div class="confirm-item" data-id="${esc(p.id)}">
      <div class="d">${esc(p.description)}${p.args?.contenu ? `<details><summary class="muted" style="cursor:pointer;font-size:12px">Voir le contenu</summary><pre class="pv-text" style="max-height:220px">${esc(p.args.contenu)}</pre></details>` : ''}</div>
      <div class="seg"><button class="yes on" data-act="cfYes">Oui</button><button class="no" data-act="cfNo">Non</button></div></div>`).join('')}
    <div class="row wrap"><button class="btn primary sm" data-act="cfSend">${ic('check', 'sm')} Valider</button><button class="btn sm" data-act="cfAll">Tout autoriser</button><button class="btn ghost sm" data-act="cfNone">Tout refuser</button>
    <span class="muted" style="font-size:12px">Les suppressions vont à la corbeille ; un fichier modifié garde une copie de son ancienne version.</span></div></div>`;
}
// ── Discussion : un seul code pour la fenêtre principale, le volet du bureau et « Demander » ──
// La « peau » (skin) dit comment habiller une question et une réponse, et quels boutons proposer. Tout le reste
// — réflexion, texte mis en forme, étapes d'un agent, erreurs, validations, réponse en direct — est commun :
// une correction faite ici vaut partout.
function thinkHtml(text) {
  return `<details class="seg-think"><summary>${ic('info', 'sm')} Réflexion (${text.length} caractères)</summary><div class="tx">${esc(text)}</div></details>`;
}
function msgActsHtml(m, i, last, skin) {
  const btn = (act, icon, title) => `<button class="icon-btn sm" data-act="${act}" data-m="${i}" title="${title}">${ic(icon, 'sm')}</button>`;
  const grim = hasGrimoire();
  return `<div class="row acts">${btn('copyMsg', 'copy', 'Copier')}${skin.save ? btn('saveMsg', 'save', 'Enregistrer dans un fichier') : ''}`
    + (skin.office ? btn('toDocx', 'quill', grim ? 'Envoyer vers Grimoire (document Word)' : 'Enregistrer en document Word') : '')
    + (skin.office && hasMdTable(m.content) ? btn('toXlsx', 'sheet', grim ? 'Envoyer les tableaux vers un classeur Grimoire' : 'Enregistrer les tableaux en classeur Excel') : '')
    + (last ? btn('regen', 'refresh', 'Régénérer la réponse') : '')
    + `<span class="stats">${m.interrompu ? 'interrompu · ' : ''}${m.vitesse ? `${m.vitesse} tok/s · ` : ''}${esc(m.model || '')}</span></div>`;
}
function chatHtml(conv, skin, from = 0) {
  const msgs = conv?.messages || [];
  const a = agentById(conv?.agent_id);
  const parts = [];
  let turn = null;
  const flush = () => { if (turn) { parts.push(skin.bot(a, turn.join(''))); turn = null; } };
  msgs.forEach((m, i) => {
    if (i < from) return;
    if (m.role === 'user') { flush(); parts.push(skin.user(m, i)); return; }
    if (!turn) turn = [];
    if (m.role === 'tool') { turn.push(stepHtml({ ...m, name: m.tool_name, id: m.call_id })); return; }
    if (m.role === 'error') { turn.push(errorHtml(m.content, i === msgs.length - 1 && m.reessayer !== false && !conv.pending)); return; }
    if (m.thinking) turn.push(thinkHtml(m.thinking));
    if (m.content) turn.push(`<div class="md">${md(m.content)}</div>${msgActsHtml(m, i, i === msgs.length - 1 && !conv.pending, skin)}`);
  });
  if (conv?.pending?.length) {
    if (!turn) turn = [];
    for (const call of conv.pending) if (!call.needs) turn.push(stepHtml(call));
    for (const call of conv.pending) if (call.needs) turn.push(stepHtml({ ...call, waiting: true }));
    turn.push(confirmHtml(conv.pending.filter((x) => x.needs)));
  }
  flush();
  return parts.join('');
}
// Réponse en cours d'écriture : réflexion, texte, appels d'outils, validations, erreurs, au fil du flux.
function chatLiveTurn(container, skin, { agent, model, scroll, onChange }) {
  container.insertAdjacentHTML('beforeend', skin.bot(agent, `<div class="row muted typing"><span class="spinner"></span><span style="font-size:12.5px">${esc(model)} réfléchit…</span></div>`));
  const el = container.lastElementChild;
  const body = $('.body', el);
  let seg = null;
  let raf = 0;
  const untype = () => $('.typing', body)?.remove();
  const newSeg = () => {
    untype();
    const d = document.createElement('div');
    d.className = 'col';
    d.style.gap = '6px';
    d.innerHTML = '<details class="seg-think hidden" open><summary>Réflexion…</summary><div class="tx"></div></details><div class="md"></div><div class="stats"></div>';
    body.append(d);
    seg = { el: d, think: '', content: '' };
    return seg;
  };
  const paint = () => { raf = 0; if (seg) { $('.md', seg.el).innerHTML = md(seg.content); scroll(); } };
  const add = (html, force) => { untype(); body.insertAdjacentHTML('beforeend', html); scroll(force); };
  return {
    on(ev) {
      switch (ev.t) {
        case 'thinking': {
          if (!seg) newSeg();
          seg.think += ev.d;
          const d = $('.seg-think', seg.el); d.classList.remove('hidden');
          const tx = $('.tx', d); tx.textContent = seg.think; tx.scrollTop = tx.scrollHeight;
          scroll(); break;
        }
        case 'content':
          if (!seg) newSeg();
          seg.content += ev.d;
          if (!raf) raf = requestAnimationFrame(paint);
          break;
        case 'message_end':
          if (seg) {
            paint();
            const d = $('.seg-think', seg.el); d.open = false; $('summary', d).textContent = `Réflexion (${seg.think.length} caractères)`;
            if (ev.vitesse) $('.stats', seg.el).textContent = `${ev.vitesse} tok/s`;
          }
          seg = null; break;
        case 'tool_call':
          add(stepHtml({ id: ev.id, name: ev.name, description: ev.description, pending: !ev.needs_confirm, waiting: ev.needs_confirm })); break;
        case 'tool_result': {
          const sel = `.step[data-step="${CSS.escape(ev.id)}"]`;
          const old = $(sel, body) || $$(sel, container).pop();
          const html = stepHtml({ id: ev.id, name: ev.name, description: old ? $('.desc', old).textContent : '', ok: ev.ok, refuse: ev.refuse, summary: ev.summary });
          if (old) old.outerHTML = html; else body.insertAdjacentHTML('beforeend', html);
          scroll(); break;
        }
        case 'confirm': add(confirmHtml(ev.pending), true); break;
        case 'notice': body.insertAdjacentHTML('beforeend', `<div class="notice">${esc(ev.d)}</div>`); break;
        case 'error': add(errorHtml(ev.d, false), true); break;
        default: break;
      }
      onChange?.();
    },
    error(msg) { untype(); body.insertAdjacentHTML('beforeend', errorHtml(msg, false)); onChange?.(); },
    el,
  };
}
// Boutons d'une discussion (copier, enregistrer, Word, Excel, régénérer, réessayer, validations d'un agent).
// ctx : { conv() → la discussion affichée, send(options) → envoie au modèle }. Vrai si le bouton a été traité.
function chatAction(b, ctx) {
  const conv = ctx.conv();
  const text = () => conv?.messages?.[+b.dataset.m]?.content || '';
  const card = b.closest('.confirm-card');
  const pick = (yes) => $$('.confirm-item', card).forEach((it) => { $('.yes', it).classList.toggle('on', yes); $('.no', it).classList.toggle('on', !yes); });
  const decide = () => {
    const decisions = {};
    $$('.confirm-item', card).forEach((it) => { decisions[it.dataset.id] = $('.yes', it).classList.contains('on'); });
    $$('button', card).forEach((x) => { x.disabled = true; });
    ctx.send({ decisions });
  };
  switch (b.dataset.act) {
    case 'copyMsg': copyText(text()); return true;
    case 'saveMsg': saveTextToFile(text(), `Archiviste ${stamp()}.md`); return true;
    case 'toDocx': sendToOffice(text(), 'docx', conv?.titre); return true;
    case 'toXlsx': sendToOffice(text(), 'xlsx', conv?.titre); return true;
    case 'regen': case 'retry': ctx.send({ regenerate: true }); return true;
    case 'cfYes': case 'cfNo': $$('button', b.closest('.seg')).forEach((x) => x.classList.toggle('on', x === b)); return true;
    case 'cfAll': pick(true); decide(); return true;
    case 'cfNone': pick(false); decide(); return true;
    case 'cfSend': decide(); return true;
    default: return false;
  }
}
// Habillage de la fenêtre principale : bulles larges, avatar, nom de l'agent, tous les boutons.
const MAIN_SKIN = {
  save: true,
  office: true,
  user: (m, i) => `<div class="m-user">
        ${m.attachments?.length ? `<div class="atts">${m.attachments.map((x) => `<span class="att" title="${esc(x.path)}">${x.kind === 'image' ? `<img src="${rawUrl(x.path)}" alt="">` : x.kind === 'folder' ? ic('folder', 'sm') : ic('file', 'sm')}<span>${esc(x.name)}</span></span>`).join('')}</div>` : ''}
        ${m.content ? `<div class="bubble">${esc(m.content)}</div>` : ''}
        <div class="acts"><button class="icon-btn sm" data-act="copyMsg" data-m="${i}" title="Copier">${ic('copy', 'sm')}</button><button class="icon-btn sm" data-act="asPrompt" data-m="${i}" title="Enregistrer comme prompt">${ic('prompt', 'sm')}</button></div></div>`,
  bot: (a, inner) => `<div class="m-bot">${avatarHtml(a)}<div class="body"><div class="who">${a ? esc(a.nom) : 'Archiviste'}</div>${inner}</div></div>`,
};
function renderMessages() {
  const inner = $('#cInner');
  const msgs = C.conv?.messages || [];
  const a = agentById(cur().agent_id);
  if (!msgs.length) {
    const prenom = S.settings.prenom || '';
    inner.innerHTML = `<div class="chat-empty">
      <img class="logo" src="/static/logo-seal.svg" alt="" width="76" height="76">
      <h2>${a ? `${esc(a.icone)} ${esc(a.nom)}` : `Bonjour ${esc(prenom)}`}</h2>
      <p class="muted">${a ? esc(a.description || '') : 'Je tourne en local sur ton PC : rien ne quitte ta machine. Pose une question, joins un fichier, ou confie une tâche à un agent.'}</p>
      ${ollamaBanner()}
      ${a ? '' : `<div class="suggest">${SUGGESTIONS.map((s, i) => `<div class="sugg" data-act="sugg" data-i="${i}"><b>${esc(s.t)}</b><span>${esc(s.d)}</span></div>`).join('')}</div>`}
    </div>`;
    return;
  }
  inner.innerHTML = chatHtml(C.conv, MAIN_SKIN);
  scrollChat(true);
}
function scrollChat(force) { const m = $('#cMsgs'); if (force || C.stick) m.scrollTop = m.scrollHeight; }

function createLiveTurn() {
  const a = agentById(cur().agent_id);
  return chatLiveTurn($('#cInner'), MAIN_SKIN, { agent: a, model: cur().modele || a?.modele || S.settings.model, scroll: scrollChat });
}
function setBusy(on) {
  C.busy = on;
  const b = $('#cSend');
  if (!b) return;
  b.innerHTML = ic(on ? 'stop' : 'send');
  b.title = on ? 'Arrêter la génération' : 'Envoyer';
  b.classList.toggle('danger', on);
}
function stopChat() { C.ctrl?.abort(); }
async function sendMessage({ regenerate = false, decisions = null } = {}) {
  if (C.busy) return;
  const inp = $('#cInput');
  const text = regenerate || decisions ? '' : inp.value.trim();
  const atts = regenerate || decisions ? [] : C.atts.map((a) => a.path);
  if (!regenerate && !decisions && !text && !atts.length) return;
  if (!C.conv) {
    try { C.conv = await post('/api/conversations', C.draft); }
    catch (e) { return toast(e.message, 'err'); }
    updateHash();
  }
  const body = { conv_id: C.conv.id };
  const inner = $('#cInner');
  if (!C.conv.messages.length) inner.innerHTML = '';
  if (text || atts.length) {
    body.message = text; body.attachments = atts;
    const shown = C.atts.slice();
    inner.insertAdjacentHTML('beforeend', `<div class="m-user">${shown.length ? `<div class="atts">${shown.map((x) => `<span class="att">${x.kind === 'folder' ? ic('folder', 'sm') : ic('file', 'sm')}<span>${esc(x.name)}</span></span>`).join('')}</div>` : ''}${text ? `<div class="bubble">${esc(text)}</div>` : ''}</div>`);
    inp.value = ''; inp.dispatchEvent(new Event('input'));
    C.atts = []; renderAtts();
  }
  if (regenerate) {
    body.regenerate = true;
    const bots = $$('.m-bot', inner); bots.pop()?.remove();
  }
  if (decisions) {
    body.decisions = decisions;
    $$('.confirm-card', inner).forEach((x) => x.remove());
  }
  const live = createLiveTurn();
  scrollChat(true);
  C.stick = true;
  setBusy(true);
  C.ctrl = new AbortController();
  let localErr = null;  // erreur que le serveur n'a pas pu enregistrer (Archiviste injoignable, discussion occupée…)
  let failed = false;
  try {
    await streamApi('/api/chat', body, (ev) => {
      live.on(ev);
      if (ev.t === 'error') failed = true;
      if (ev.t === 'user_saved' && ev.titre && C.conv && !C.conv.titre) { C.conv.titre = ev.titre; renderChatHead(); }
    }, C.ctrl.signal);
  } catch (e) {
    if (e.name !== 'AbortError') { localErr = e.message; live.error(e.message); }
  } finally {
    setBusy(false);
    C.ctrl = null;
    const keepScroll = $('#cMsgs').scrollTop;
    try { C.conv = await api(`/api/conversations/${C.conv.id}`); } catch { /* */ }
    const atBottom = C.stick;
    renderMessages();
    if (localErr) {  // le rafraîchissement vient d'effacer l'affichage en direct : on remet le message
      if (text && !C.conv.messages.some((m) => m.role === 'user' && m.content === text)) { inp.value = text; inp.dispatchEvent(new Event('input')); }  // le message non envoyé n'est pas perdu
      inner.insertAdjacentHTML('beforeend', errorHtml(localErr, false));
      scrollChat(true);
    } else if (!atBottom) $('#cMsgs').scrollTop = keepScroll;
    if (failed || localErr || !S.status?.ok) refreshStatus();  // la pastille dit tout de suite si Ollama est tombé, ou revenu
    renderChatHead();
    loadConvs();
    inp.focus();
  }
}
async function exportConv() {
  const c = C.conv;
  if (!c) return;
  const a = agentById(c.agent_id);
  const lines = [`# ${c.titre || 'Discussion'}`, '', `_${a ? `Agent : ${a.nom} · ` : ''}${DF_FULL.format(new Date(c.cree || Date.now()))}_`, ''];
  for (const m of c.messages) {
    if (m.role === 'user') lines.push(`## 🧑 ${S.settings.prenom || 'Moi'}`, '', m.content || '', ...(m.attachments || []).map((x) => `- 📎 ${x.path}`), '');
    else if (m.role === 'assistant' && m.content) lines.push(`## 🤖 ${a ? a.nom : 'Archiviste'}`, '', m.content, '');
    else if (m.role === 'tool') lines.push(`> 🔧 ${m.description} — ${m.summary}`, '');
  }
  saveTextToFile(lines.join('\n'), `${(c.titre || 'discussion').replace(/[\\/:*?"<>|]/g, '').slice(0, 60)}.md`);
}
RENDER.chat = (opts = {}) => {
  if (!C.built) buildChat();
  if (!C.draft) C.draft = freshDraft();
  if (opts.conv && opts.conv !== C.conv?.id) { openConv(opts.conv); loadConvs(); return; }
  renderChatAll();
  loadConvs();
  setTimeout(() => $('#cInput')?.focus(), 30);
};

// ═════════════════════════════════════════════════════════════
//  AGENTS
// ═════════════════════════════════════════════════════════════
async function loadAgents() { S.agents = await api('/api/agents'); $('#countAgents').textContent = S.agents.length || ''; }
async function loadPrompts() { S.prompts = await api('/api/prompts'); $('#countPrompts').textContent = S.prompts.length || ''; }
const EMOJIS = ['🤖', '🗂️', '📖', '✍️', '🧹', '🔎', '🧠', '📊', '💼', '🛠️', '🧾', '📸', '🎮', '🎲', '📚', '🗺️', '⚙️', '🦉'];
function renderAgents() {
  const v = $('#view-agents');
  v.innerHTML = `<div class="vhead"><h1>Agents</h1><span class="sub">Des assistants spécialisés, avec leurs consignes et leurs outils.</span><span class="grow"></span>
      <button class="btn primary" data-act="new">${ic('plus', 'sm')} Nouvel agent</button></div>
    <div class="vbody">
      <div class="banner">${ic('info')}<div>Un agent combine <b>des consignes</b> (son rôle), <b>des outils</b> (lire, ranger, écrire des fichiers…) et <b>un dossier de travail</b> dont il ne peut pas sortir. Par défaut, toute action qui modifie un fichier attend ta validation.</div></div>
      <div class="grid-cards">${S.agents.map((a) => {
        const reads = a.outils.filter((o) => !S.tools.find((t) => t.name === o)?.modifie).length;
        const writes = a.outils.length - reads;
        return `<div class="acard">
          <div class="top"><div class="emo">${esc(a.icone)}</div><div class="grow"><h3>${esc(a.nom)}</h3><p>${esc(a.description || '')}</p></div></div>
          <div class="badges">
            ${a.outils.length ? `<span class="badge">${reads} lecture</span>${writes ? `<span class="badge accent">${writes} modification</span>` : ''}` : '<span class="badge">sans outils</span>'}
            ${a.modele ? `<span class="badge">${esc(a.modele)}</span>` : ''}
            ${a.dossier ? `<span class="badge" title="${esc(a.dossier)}">📁 ${esc(tildify(a.dossier))}</span>` : ''}
            ${writes && !a.confirmer ? '<span class="badge danger">sans validation</span>' : ''}
          </div>
          <div class="foot"><button class="btn primary sm" data-act="chat" data-id="${a.id}">${ic('chat', 'sm')} Discuter</button>
            <button class="btn sm" data-act="edit" data-id="${a.id}">${ic('pencil', 'sm')} Modifier</button>
            <span class="grow"></span>
            <button class="icon-btn sm" data-act="dup" data-id="${a.id}" title="Dupliquer">${ic('copy', 'sm')}</button>
            <button class="icon-btn sm" data-act="del" data-id="${a.id}" title="Supprimer">${ic('trash', 'sm')}</button></div>
        </div>`;
      }).join('')}</div>
      ${S.agents.length ? '' : `<div class="empty">${ic('bot')}<p>Aucun agent. Crée le premier !</p></div>`}
    </div>`;
}
function bindAgents() {
  $('#view-agents').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const a = agentById(b.dataset.id);
    const act = b.dataset.act;
    if (act === 'new') editAgent(null);
    if (act === 'edit') editAgent(a);
    if (act === 'chat') startChat({ agent_id: a.id });
    if (act === 'dup') { await post('/api/agents', { ...a, id: null, nom: a.nom + ' (copie)' }); await loadAgents(); renderAgents(); }
    if (act === 'del') {
      if (!(await ask(`Supprimer l'agent « ${a.nom} » ? Ses discussions restent disponibles en discussion libre.`, { ok: 'Supprimer', danger: true }))) return;
      await post(`/api/agents/${a.id}/delete`); await loadAgents(); renderAgents();
    }
  });
}
function editAgent(src) {
  const a = src ? { ...src } : { nom: '', icone: '🤖', description: '', consignes: 'Tu es … Tu aides {prenom} à …', modele: '', dossier: '', outils: ['lister_dossier', 'lire_fichier', 'chercher_fichiers', 'infos_fichier'], confirmer: true, think: false, temperature: 0.3 };
  const models = (S.status?.models || []).map((m) => m.name);
  const toolOpt = (t) => `<label class="toolopt"><input type="checkbox" data-tool="${t.name}" ${a.outils.includes(t.name) ? 'checked' : ''}><div><b>${esc(t.label)}</b><small>${esc(t.description)}</small></div></label>`;
  const m = openModal({
    title: src ? `Modifier ${a.nom}` : 'Nouvel agent', cls: 'wide',
    body: `<div class="row" style="align-items:flex-end;gap:12px">
        <label class="field" style="width:76px"><span>Icône</span><input type="text" data-f="icone" value="${esc(a.icone)}" maxlength="4" style="text-align:center;font-size:20px;padding:4px"></label>
        <label class="field grow"><span>Nom</span><input type="text" data-f="nom" value="${esc(a.nom)}" placeholder="Ex. : Comptable, Bibliothécaire…"></label></div>
      <div class="emoji-pick">${EMOJIS.map((x) => `<button type="button" data-emo="${x}">${x}</button>`).join('')}</div>
      <label class="field"><span>Description courte</span><input type="text" data-f="description" value="${esc(a.description)}" placeholder="Ce qu'il fait, en une phrase"></label>
      <label class="field"><span>Consignes (son rôle, sa façon de travailler)</span><textarea data-f="consignes" rows="7">${esc(a.consignes)}</textarea><small>{prenom} sera remplacé par ton prénom. Sois concret : un petit modèle comme qwen 4B suit mieux des consignes courtes et précises.</small></label>
      <div class="settings-grid">
        <label class="field"><span>Modèle</span><select data-f="modele"><option value="">Par défaut (${esc(S.settings.model)})</option>${models.map((x) => `<option ${x === a.modele ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label>
        <label class="field"><span>Créativité (température) : <b data-tv>${a.temperature}</b></span><input type="range" min="0" max="1.5" step="0.1" data-f="temperature" value="${a.temperature}"><small>Bas = précis et fiable (conseillé avec des outils), haut = plus inventif.</small></label>
        <div class="field full"><span>Dossier de travail</span><div class="pathbox"><input type="text" data-f="dossier" value="${esc(a.dossier)}" placeholder="Vide = tous tes dossiers autorisés"><button class="btn" type="button" data-pick>${ic('folder', 'sm')} Choisir…</button></div><small>L'agent ne pourra rien lire ni modifier en dehors de ce dossier. Tu peux aussi le changer pour une discussion précise.</small></div>
      </div>
      <h3 style="margin:6px 0 0;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">Outils de lecture (sans risque)</h3>
      <div class="toolgroup">${S.tools.filter((t) => !t.modifie).map(toolOpt).join('')}</div>
      <h3 style="margin:6px 0 0;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">Outils de modification</h3>
      <div class="toolgroup">${S.tools.filter((t) => t.modifie).map(toolOpt).join('')}</div>
      <label class="switch"><input type="checkbox" data-f="confirmer" ${a.confirmer ? 'checked' : ''}><i></i>Me demander validation avant chaque modification (recommandé)</label>
      <div class="banner danger hidden" data-warn>${ic('alert')}<div>Sans validation, l'agent modifie, déplace et met à la corbeille sans te demander. Les suppressions restent récupérables dans la corbeille, mais vérifie bien son dossier de travail.</div></div>
      <label class="switch"><input type="checkbox" data-f="think" ${a.think ? 'checked' : ''}><i></i>Mode réflexion par défaut (plus lent)</label>`,
    footer: `<button class="btn" data-close>Annuler</button><button class="btn primary" data-save>${ic('check', 'sm')} Enregistrer</button>`,
  });
  const f = (k) => $(`[data-f="${k}"]`, m.el);
  const warn = () => $('[data-warn]', m.el).classList.toggle('hidden', f('confirmer').checked || !$$('[data-tool]', m.el).some((x) => x.checked && S.tools.find((t) => t.name === x.dataset.tool)?.modifie));
  m.el.addEventListener('change', warn);
  warn();
  f('temperature').addEventListener('input', (e) => { $('[data-tv]', m.el).textContent = e.target.value; });
  m.el.addEventListener('click', async (e) => {
    const emo = e.target.closest('[data-emo]');
    if (emo) f('icone').value = emo.dataset.emo;
    if (e.target.closest('[data-pick]')) { const d = await pickPath({ title: 'Dossier de travail', start: f('dossier').value || S.home }); if (d) f('dossier').value = d; }
    if (e.target.closest('[data-save]')) {
      const body = {
        id: src?.id, nom: f('nom').value, icone: f('icone').value, description: f('description').value, consignes: f('consignes').value,
        modele: f('modele').value, temperature: +f('temperature').value, dossier: f('dossier').value.trim(),
        confirmer: f('confirmer').checked, think: f('think').checked,
        outils: $$('[data-tool]', m.el).filter((x) => x.checked).map((x) => x.dataset.tool),
      };
      if (!body.nom.trim()) return toast('Donne un nom à l\'agent.', 'err');
      try { await post('/api/agents', body); await loadAgents(); if (S.view === 'agents') renderAgents(); m.close(true); toast('Agent enregistré', 'ok'); }
      catch (err) { toast(err.message, 'err'); }
    }
  });
}
RENDER.agents = () => renderAgents();

// ═════════════════════════════════════════════════════════════
//  PROMPTS
// ═════════════════════════════════════════════════════════════
const P = { q: '', cat: null };
const varsOf = (t) => [...new Set([...String(t).matchAll(/\{\{\s*([^}]+?)\s*\}\}/g)].map((m) => m[1]))];
function renderPrompts() {
  const v = $('#view-prompts');
  const cats = [...new Set(S.prompts.map((p) => p.categorie))].sort((a, b) => a.localeCompare(b, 'fr'));
  const list = S.prompts.filter((p) => (!P.cat || p.categorie === P.cat) && (!P.q || (p.titre + ' ' + p.contenu).toLowerCase().includes(P.q)))
    .sort((a, b) => (b.favori - a.favori) || a.titre.localeCompare(b.titre, 'fr'));
  v.innerHTML = `<div class="vhead"><h1>Prompts</h1><span class="sub">Tes consignes réutilisables.</span><span class="grow"></span>
      <div class="fsearch">${ic('search', 'sm')}<input type="search" id="pSearch" placeholder="Rechercher…" value="${esc(P.q)}"></div>
      <button class="btn primary" data-act="new">${ic('plus', 'sm')} Nouveau prompt</button></div>
    <div class="vbody">
      <div class="row wrap" style="margin-bottom:14px"><span class="chip ${!P.cat ? 'on' : ''}" data-act="cat" data-cat="">Toutes <b>${S.prompts.length}</b></span>${cats.map((c) => `<span class="chip ${P.cat === c ? 'on' : ''}" data-act="cat" data-cat="${esc(c)}">${esc(c)} <b>${S.prompts.filter((p) => p.categorie === c).length}</b></span>`).join('')}</div>
      <div class="grid-cards">${list.map((p) => {
        const vars = varsOf(p.contenu);
        return `<div class="acard pcard">
          <div class="top"><div class="grow"><h3>${esc(p.titre)}</h3><div class="row wrap" style="margin-top:4px;gap:5px"><span class="badge">${esc(p.categorie)}</span>${vars.map((x) => `<span class="badge accent">{{${esc(x)}}}</span>`).join('')}</div></div>
            <button class="icon-btn sm star ${p.favori ? 'on' : ''}" data-act="fav" data-id="${p.id}" title="Favori">${ic('star', 'sm')}</button></div>
          <div class="body">${esc(p.contenu)}</div>
          <div class="foot"><button class="btn primary sm" data-act="use" data-id="${p.id}">${ic('play', 'sm')} Utiliser</button>
            <button class="btn sm" data-act="edit" data-id="${p.id}">${ic('pencil', 'sm')} Modifier</button><span class="grow"></span>
            <span class="faint" style="font-size:11.5px">${p.utilisations ? `${p.utilisations}×` : ''}</span>
            <button class="icon-btn sm" data-act="copy" data-id="${p.id}" title="Copier">${ic('copy', 'sm')}</button>
            <button class="icon-btn sm" data-act="del" data-id="${p.id}" title="Supprimer">${ic('trash', 'sm')}</button></div></div>`;
      }).join('')}</div>
      ${list.length ? '' : `<div class="empty">${ic('prompt')}<p>Aucun prompt${P.q || P.cat ? ' ne correspond' : ''}.</p></div>`}
      <p class="muted" style="font-size:12.5px;margin-top:18px">Astuce : écris <code>{{variable}}</code> dans un prompt pour qu'Archiviste te demande la valeur au moment de l'utiliser. Les prompts de la catégorie « Tri » apparaissent dans le Tri intelligent.</p>
    </div>`;
  $('#pSearch').addEventListener('input', debounce((e) => { P.q = e.target.value.toLowerCase(); renderPrompts(); const s = $('#pSearch'); s.focus(); s.setSelectionRange(s.value.length, s.value.length); }, 250));
}
function bindPrompts() {
  $('#view-prompts').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const p = S.prompts.find((x) => x.id === b.dataset.id);
    const act = b.dataset.act;
    if (act === 'new') editPrompt(null);
    if (act === 'edit') editPrompt(p);
    if (act === 'cat') { P.cat = b.dataset.cat || null; renderPrompts(); }
    if (act === 'copy') copyText(p.contenu);
    if (act === 'fav') { await post('/api/prompts', { ...p, favori: !p.favori }); await loadPrompts(); renderPrompts(); }
    if (act === 'use') {
      const text = await fillVars(p.contenu, p.titre);
      if (text === null) return;
      post(`/api/prompts/${p.id}/used`).catch(() => {});
      if (/tri/i.test(p.categorie)) { T.consignes = text; T.mode = 'ai'; go('sort'); return; }
      if (!C.conv && !C.draft) C.draft = freshDraft();
      go('chat');
      const inp = $('#cInput'); inp.value = text; inp.dispatchEvent(new Event('input')); inp.focus();
    }
    if (act === 'del') {
      if (!(await ask(`Supprimer le prompt « ${p.titre} » ?`, { ok: 'Supprimer', danger: true }))) return;
      await post(`/api/prompts/${p.id}/delete`); await loadPrompts(); renderPrompts();
    }
  });
}
function editPrompt(src, preset = {}) {
  const p = src ? { ...src } : { titre: '', categorie: P.cat || 'Divers', contenu: '', favori: false, ...preset };
  const cats = [...new Set(S.prompts.map((x) => x.categorie))];
  const m = openModal({
    title: src ? 'Modifier le prompt' : 'Nouveau prompt', cls: 'wide',
    body: `<div class="row" style="gap:12px"><label class="field grow"><span>Titre</span><input type="text" data-f="titre" value="${esc(p.titre)}" placeholder="Ex. : Résumer une réunion"></label>
        <label class="field" style="width:220px"><span>Catégorie</span><input type="text" data-f="categorie" value="${esc(p.categorie)}" list="pCats"><datalist id="pCats">${cats.map((c) => `<option value="${esc(c)}">`).join('')}<option value="Tri"></datalist></label></div>
      <label class="field"><span>Contenu</span><textarea data-f="contenu" rows="12" placeholder="Écris ta consigne. Utilise {{variable}} pour les parties à compléter.">${esc(p.contenu)}</textarea><small data-vars></small></label>
      <label class="check"><input type="checkbox" data-f="favori" ${p.favori ? 'checked' : ''}> Favori (en haut des listes)</label>`,
    footer: `<button class="btn" data-close>Annuler</button><button class="btn primary" data-save>${ic('check', 'sm')} Enregistrer</button>`,
  });
  const f = (k) => $(`[data-f="${k}"]`, m.el);
  const showVars = () => { const v = varsOf(f('contenu').value); $('[data-vars]', m.el).textContent = v.length ? `Variables : ${v.join(', ')}` : 'Aucune variable.'; };
  f('contenu').addEventListener('input', showVars); showVars();
  $('[data-save]', m.el).onclick = async () => {
    const body = { id: src?.id, titre: f('titre').value, categorie: f('categorie').value, contenu: f('contenu').value, favori: f('favori').checked };
    if (!body.contenu.trim()) return toast('Le prompt est vide.', 'err');
    if (!body.titre.trim()) body.titre = body.contenu.trim().split('\n')[0].slice(0, 60);
    try { await post('/api/prompts', body); await loadPrompts(); if (S.view === 'prompts') renderPrompts(); m.close(true); toast('Prompt enregistré', 'ok'); }
    catch (e) { toast(e.message, 'err'); }
  };
}
function fillVars(text, title = 'Compléter le prompt') {
  const vars = varsOf(text);
  if (!vars.length) return Promise.resolve(text);
  return new Promise((resolve) => {
    let res = null;
    const m = openModal({
      title,
      body: vars.map((v, i) => `<label class="field"><span>${esc(v)}</span>${/texte|contenu|text|code|notes?/i.test(v) ? `<textarea rows="5" data-v="${i}"></textarea>` : `<input type="text" data-v="${i}">`}</label>`).join(''),
      footer: `<button class="btn" data-close>Annuler</button><button class="btn primary" data-ok>Insérer</button>`,
      onClose: () => resolve(res),
    });
    const ok = () => {
      res = text;
      vars.forEach((v, i) => { const val = $(`[data-v="${i}"]`, m.el).value; res = res.replace(new RegExp(`\\{\\{\\s*${v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\}\\}`, 'g'), val); });
      m.close(true);
    };
    $('[data-ok]', m.el).onclick = ok;
    m.el.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') ok(); });
  });
}
RENDER.prompts = () => renderPrompts();

// ═════════════════════════════════════════════════════════════
//  CORBEILLE
// ═════════════════════════════════════════════════════════════
const TR = S.trash;
async function renderTrash() {
  const v = $('#view-trash');
  try { TR.items = await api('/api/trash'); } catch (e) { TR.items = []; toast(e.message, 'err'); }
  TR.sel = new Set([...TR.sel].filter((id) => TR.items.some((x) => x.id === id)));
  const total = TR.items.reduce((s, x) => s + (x.size || 0), 0);
  v.innerHTML = `<div class="vhead"><h1>Corbeille</h1><span class="sub">${TR.items.length} élément(s) · ${fmtSize(total) || '0 o'} — la même corbeille que Nemo.</span><span class="grow"></span>
      <button class="btn" data-act="restore" ${TR.sel.size ? '' : 'disabled'}>${ic('undo', 'sm')} Restaurer</button>
      <button class="btn danger" data-act="purge" ${TR.sel.size ? '' : 'disabled'}>${ic('trash', 'sm')} Supprimer définitivement</button>
      <button class="btn danger" data-act="empty" ${TR.items.length ? '' : 'disabled'}>Vider la corbeille</button></div>
    <div class="vbody">${TR.items.length ? `<table class="tbl"><thead><tr><th style="width:30px"><input type="checkbox" data-act="all" ${TR.sel.size && TR.sel.size === TR.items.length ? 'checked' : ''}></th><th>Nom</th><th>Emplacement d'origine</th><th>Supprimé le</th><th style="text-align:right">Taille</th></tr></thead><tbody>
      ${TR.items.map((x) => `<tr><td><input type="checkbox" data-act="one" data-id="${esc(x.id)}" ${TR.sel.has(x.id) ? 'checked' : ''}></td>
        <td><div class="row">${fileIcon({ dir: x.dir, ext: x.ext, kind: 'file' })}<span class="ellipsis">${esc(x.name)}</span></div></td>
        <td class="muted mono ellipsis" style="max-width:380px" title="${esc(x.origine)}">${esc(tildify(dirname(x.origine)))}</td>
        <td class="muted">${x.date ? DF_FULL.format(new Date(x.date)) : ''}</td><td class="muted" style="text-align:right">${x.dir ? 'dossier' : fmtSize(x.size)}</td></tr>`).join('')}
      </tbody></table>` : `<div class="empty">${ic('trash')}<p>La corbeille est vide.</p></div>`}</div>`;
}
function bindTrash() {
  $('#view-trash').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'one') { b.checked ? TR.sel.add(b.dataset.id) : TR.sel.delete(b.dataset.id); return renderTrash(); }
    if (act === 'all') { TR.sel = b.checked ? new Set(TR.items.map((x) => x.id)) : new Set(); return renderTrash(); }
    if (act === 'restore') {
      try { reportRestore(await post('/api/trash/restore', { ids: [...TR.sel] })); } catch (err) { toast(err.message, 'err'); }
      TR.sel.clear(); renderTrash();
    }
    if (act === 'purge' || act === 'empty') {
      const ids = act === 'empty' ? TR.items.map((x) => x.id) : [...TR.sel];
      if (!(await ask(`Supprimer définitivement ${ids.length} élément(s) ? C'est irréversible.`, { ok: 'Supprimer définitivement', danger: true }))) return;
      try { await post('/api/trash/purge', { ids }); toast('Supprimé définitivement', 'ok'); } catch (err) { toast(err.message, 'err'); }
      TR.sel.clear(); renderTrash();
    }
  });
}
RENDER.trash = () => renderTrash();

// ═════════════════════════════════════════════════════════════
//  RÉGLAGES
// ═════════════════════════════════════════════════════════════
let roots = [];
function renderSettings() {
  const s = S.settings;
  roots = [...s.roots];
  const models = (S.status?.models || []);
  const v = $('#view-settings');
  v.innerHTML = `<div class="vhead"><h1>Réglages</h1><span class="grow"></span><button class="btn primary" data-act="save">${ic('check', 'sm')} Enregistrer</button></div>
    <div class="vbody narrow">
      ${ollamaBanner()}
      <div class="card"><h2>${ic('cpu')} Intelligence artificielle (Ollama)</h2>
        <div class="settings-grid">
          <label class="field full"><span>Adresse d'Ollama</span><div class="pathbox"><input type="url" data-f="ollama_url" value="${esc(s.ollama_url)}"><button class="btn" data-act="test">${ic('refresh', 'sm')} Tester</button></div><small data-test>${S.status?.ok ? `✓ Connecté — Ollama ${esc(S.status.version || '')}, ${models.length} modèle(s) installé(s)` : '✗ Pas de connexion'}</small></label>
          <label class="field"><span>Modèle par défaut</span><input type="text" data-f="model" value="${esc(s.model)}" list="stModels"><datalist id="stModels">${models.map((m) => `<option value="${esc(m.name)}">${esc(m.params || '')} ${esc(m.quant || '')} · ${esc(m.taille)}</option>`).join('')}</datalist><small>Installés : ${models.map((m) => esc(m.name)).join(', ') || 'aucun'}</small></label>
          <label class="field"><span>Mémoire de conversation (contexte)</span><select data-f="num_ctx">${[4096, 8192, 16384, 32768, 65536].map((n) => `<option value="${n}" ${+s.num_ctx === n ? 'selected' : ''}>${n.toLocaleString('fr-FR')} jetons${n === 8192 ? ' (conseillé)' : n >= 32768 ? ' (gourmand en VRAM)' : ''}</option>`).join('')}</select><small>Plus c'est grand, plus l'IA « se souvient » de longs fichiers, mais plus elle consomme de mémoire vidéo (6 Go sur ta RTX 3060).</small></label>
          <label class="field"><span>Créativité par défaut : <b data-tv>${s.temperature}</b></span><input type="range" min="0" max="1.5" step="0.1" data-f="temperature" value="${s.temperature}"></label>
          <label class="field"><span>Garder le modèle chargé</span><select data-f="keep_alive">${[['5m', '5 minutes'], ['15m', '15 minutes'], ['1h', '1 heure'], ['-1', 'Toujours (réponse immédiate, VRAM occupée)']].map(([k, l]) => `<option value="${k}" ${String(s.keep_alive) === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="switch full"><input type="checkbox" data-f="think" ${s.think ? 'checked' : ''}><i></i>Mode réflexion activé par défaut dans les discussions libres</label>
        </div></div>
      <div class="card"><h2>${ic('chat')} Toi et l'assistant</h2>
        <div class="settings-grid">
          <label class="field"><span>Ton prénom</span><input type="text" data-f="prenom" value="${esc(s.prenom)}"></label>
          <label class="field"><span>Thème</span><select data-f="theme">${[['auto', 'Automatique (comme le système)'], ['dark', 'Sombre — encre'], ['light', 'Clair — parchemin']].map(([k, l]) => `<option value="${k}" ${s.theme === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="field full"><span>Consigne de base de la discussion libre</span><textarea data-f="system_prompt" rows="4">${esc(s.system_prompt)}</textarea><small>{prenom} est remplacé par ton prénom.</small></label>
        </div></div>
      <div class="card"><h2>${ic('folder')} Dossiers autorisés</h2>
        <p class="muted" style="margin-top:-4px;font-size:13px">Archiviste et ses agents ne peuvent rien voir ni toucher en dehors de ces dossiers. Ajoute par exemple ta partition Windows ou ton disque externe s'ils sont montés.</p>
        <div class="roots-list" id="stRoots"></div>
        <div class="pathbox" style="margin-top:8px"><input type="text" id="stNewRoot" placeholder="/media/${esc((S.home || '').split('/').pop() || 'moi')}/Disque"><button class="btn" data-act="pickRoot">${ic('folder', 'sm')} Parcourir…</button><button class="btn" data-act="addRoot">${ic('plus', 'sm')} Ajouter</button></div>
        <label class="switch" style="margin-top:12px"><input type="checkbox" data-f="show_hidden" ${s.show_hidden ? 'checked' : ''}><i></i>Afficher les fichiers cachés par défaut</label></div>
      <div class="card" id="stFm"></div>
      <div class="card" id="stIndex"><h2>${ic('search')} Recherche instantanée</h2><p class="muted" style="margin:0;font-size:13px"><span class="spinner"></span> Chargement…</p></div>
      <div class="card" id="stBureau"><h2>${ic('panel')} Bureau</h2><p class="muted" style="margin:0;font-size:13px"><span class="spinner"></span> Chargement…</p></div>
      <div class="card"><h2>${ic('save')} Sauvegarde</h2>
        <p class="muted" style="margin-top:-4px;font-size:13px">Exporte tes agents et tes prompts dans un fichier JSON (pour les garder ou les copier sur un autre PC).</p>
        <div class="row"><button class="btn" data-act="export">${ic('download', 'sm')} Exporter</button><button class="btn" data-act="import">${ic('upload', 'sm')} Importer…</button><input type="file" id="stImport" accept=".json,application/json" hidden></div></div>
      <div class="card"><h2>${ic('info')} À propos</h2>
        <dl class="muted" style="display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:0;font-size:13px">
          <dt>Version</dt><dd style="margin:0">Archiviste ${esc(S.status?.app_version || '')} · <a href="https://github.com/${esc(UPD.info?.depot || 'csaintecluque-ui/Archiviste')}/releases" target="_blank" rel="noopener">nouveautés</a></dd>
          <dt>Mises à jour</dt><dd style="margin:0" data-maj>${updLine()}</dd>
          <dt>Données</dt><dd style="margin:0" class="mono">${esc(tildify(s.data_dir))}</dd>
          <dt>Grimoire</dt><dd style="margin:0">${S.status?.grimoire ? `✓ détecté (${esc(S.status.grimoire)}) : les documents Word et Excel s'y ouvrent` : '— pas installé sur ce PC (appli de bureau en .deb)'}</dd>
          <dt>Lecture des PDF</dt><dd style="margin:0">${S.status?.pdftotext ? '✓ pdftotext disponible' : '✗ installe poppler-utils : <code>sudo apt install poppler-utils</code>'}</dd>
        </dl>
        <div class="row wrap" style="margin-top:12px"><button class="btn sm" data-act="checkUpdate">${ic('refresh', 'sm')} Vérifier maintenant</button>
          <button class="btn sm" data-act="rollback" title="Si une mise à jour se passe mal : réinstalle la version d'avant, sans toucher à tes données">${ic('undo', 'sm')} Revenir à la version précédente…</button>
          <label class="switch"><input type="checkbox" data-f="maj_auto" ${s.maj_auto !== false ? 'checked' : ''}><i></i>Vérifier automatiquement (au démarrage puis toutes les 6 heures)</label></div></div>
    </div>`;
  renderRoots();
  renderFmCard();
  renderIndexCard();
  renderBureauCard();
  $('[data-f="temperature"]', v).addEventListener('input', (e) => { $('[data-tv]', v).textContent = e.target.value; });
  $('#stImport').addEventListener('change', importBackup);
}
// Gestionnaire de fichiers par défaut : les dossiers ouverts depuis les autres applis (Firefox, menu de Mint,
// clé USB branchée…) s'ouvrent dans Archiviste au lieu de Nemo.
async function renderFmCard() {
  const el = $('#stFm');
  if (!el) return;
  let g;
  try { g = await api('/api/gestionnaire'); } catch { el.remove(); return; }
  const other = g.defaut && !g.archiviste ? g.defaut.replace(/\.desktop$/, '').replace(/^.*\./, '') : 'Nemo';
  el.innerHTML = `<h2>${ic('folder')} Gestionnaire de fichiers</h2>
    <p class="muted" style="margin-top:-4px;font-size:13px">${g.archiviste
      ? 'Archiviste est ton gestionnaire de fichiers : un dossier ouvert depuis une autre appli (Firefox « Afficher dans le dossier », menu de Mint, clé USB branchée…) s\'ouvre ici. « Afficher dans le gestionnaire de fichiers » ouvre alors Nemo.'
      : `Aujourd'hui, les dossiers ouverts depuis les autres applis s'ouvrent dans ${esc(other.charAt(0).toUpperCase() + other.slice(1))}. Tu peux les ouvrir dans Archiviste à la place.`}</p>
    <div class="row wrap">${g.possible
      ? `<button class="btn sm ${g.archiviste ? '' : 'primary'}" data-fm="${g.archiviste ? 'non' : 'oui'}">${g.archiviste ? `Revenir à ${esc(other === 'Nemo' ? 'Nemo' : other)}` : 'Utiliser Archiviste comme gestionnaire de fichiers'}</button>`
      : '<span class="faint" style="font-size:12.5px">Disponible avec Archiviste installé par son paquet (.deb).</span>'}
      ${g.archiviste && !g.service ? '<span class="faint" style="font-size:12px">« Afficher dans le dossier » de Firefox ouvre encore Nemo tant que Nemo est ouvert ; tout le reste passe par Archiviste.</span>' : ''}</div>`;
  el.onclick = async (e) => {
    const b = e.target.closest('[data-fm]');
    if (!b) return;
    b.disabled = true;
    try { await post('/api/gestionnaire', { archiviste: b.dataset.fm === 'oui' }); toast(b.dataset.fm === 'oui' ? 'Les dossiers s\'ouvriront maintenant dans Archiviste' : 'Les dossiers s\'ouvriront de nouveau dans le gestionnaire d\'avant', 'ok'); } catch (err) { toast(err.message, 'err'); }
    renderFmCard();
  };
}

// Index de recherche : Archiviste retient la liste de tes fichiers (et le texte des documents) pour répondre
// tout de suite. Tout reste sur le PC, dans ses données.
async function renderIndexCard() {
  const el = $('#stIndex');
  if (!el) return;
  let x;
  try { x = await api('/api/index'); } catch (e) { x = { absent: true, etat: e.message }; }
  S.index = x;
  const nb = (n) => (n || 0).toLocaleString('fr-FR');
  const state = x.absent ? 'désactivé : la recherche parcourt le disque à chaque fois'
    : !x.pret ? `première lecture de tes dossiers en cours (${nb(x.fichiers)} fichiers vus)…`
      : `${nb(x.fichiers)} fichiers et ${nb(x.dossiers)} dossiers retenus${x.passage ? ` · vérifié ${fmtDate(x.passage)}` : ''}`;
  const texts = x.absent ? '' : !x.plein_texte ? 'non disponible sur ce PC (SQLite sans recherche plein texte)'
    : !x.contenu ? 'désactivé' : `${nb(x.textes)} documents lus${x.a_lire ? ` · ${nb(x.a_lire)} fichiers encore à examiner` : ''}`;
  el.innerHTML = `<h2>${ic('search')} Recherche instantanée</h2>
    <p class="muted" style="margin-top:-4px;font-size:13px">Archiviste retient la liste de tes fichiers dans les dossiers autorisés, et la tient à jour en arrière-plan : la recherche répond tout de suite, sur tout le dossier. Rien ne quitte ton PC.</p>
    <dl class="muted" style="display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:0;font-size:13px">
      <dt>Noms</dt><dd style="margin:0">${esc(state)}</dd>
      ${texts ? `<dt>Contenu</dt><dd style="margin:0">${esc(texts)}</dd>` : ''}
    </dl>
    <div class="row wrap" style="margin-top:12px">
      <label class="switch"><input type="checkbox" data-ix="contenu" ${S.settings.index_contenu !== false ? 'checked' : ''} ${x.absent || !x.plein_texte ? 'disabled' : ''}><i></i>Lire aussi le texte des documents (PDF, Word, Excel, notes) pour chercher dedans</label>
      <span class="grow"></span><button class="btn sm" data-ix="refaire" ${x.absent ? 'disabled' : ''}>${ic('refresh', 'sm')} Reconstruire l'index</button></div>`;
  el.onchange = async (e) => {
    if (e.target.dataset.ix !== 'contenu') return;
    try { S.settings = { ...S.settings, ...(await post('/api/settings', { index_contenu: e.target.checked })) }; toast(e.target.checked ? 'Le texte des documents va être lu en arrière-plan' : 'Le texte des documents n\'est plus lu', 'ok'); } catch (err) { toast(err.message, 'err'); }
    setTimeout(renderIndexCard, 600);
  };
  el.onclick = async (e) => {
    if (e.target.closest('[data-ix]')?.dataset.ix !== 'refaire') return;
    try { await post('/api/index/reconstruire'); toast('Index en cours de reconstruction : la recherche reste utilisable pendant ce temps', 'ok'); } catch (err) { toast(err.message, 'err'); }
    setTimeout(renderIndexCard, 800);
  };
}
async function renderBureauCard(rapport) {
  const el = $('#stBureau');
  if (!el) return;
  let b;
  try { b = await api('/api/bureau'); } catch (e) { el.innerHTML = `<h2>${ic('panel')} Bureau</h2><p class="muted">${esc(e.message)}</p>`; return; }
  const okIc = (ok) => (ok === true ? '✓' : ok === false ? '✗' : '·');
  el.innerHTML = `<h2>${ic('panel')} Bureau</h2>
    <p class="muted" style="margin-top:-4px;font-size:13px">Archiviste remplace les icônes du bureau de Mint : tes fichiers du dossier <span class="mono">${esc(tildify(b.dossier))}</span>, et un volet à droite avec tes raccourcis et la discussion (qui ouvre aussi tes applis : « ouvre Grimoire »). Pour épingler une appli, un dossier ou un fichier : clic droit › <b>Épingler aux raccourcis</b>.</p>
    <div class="row wrap" style="gap:10px">
      ${b.actif
    ? `<span class="chip on">${ic('check', 'sm')} Bureau Archiviste actif</span><button class="btn" data-bu="off">Rendre le bureau à Nemo</button>`
    : `<button class="btn primary" data-bu="on">${ic('panel', 'sm')} Activer le bureau Archiviste</button>`}
      ${!b.cinnamon ? '<span class="muted" style="font-size:12.5px">Conçu pour Cinnamon (Linux Mint) : ailleurs, certaines étapes peuvent ne pas s\'appliquer.</span>' : ''}
    </div>
    ${rapport ? `<ul class="bu-rapport">${rapport.map((r) => `<li class="${r.ok === false ? 'bad' : r.ok ? 'ok' : ''}"><b>${okIc(r.ok)} ${esc(r.titre)}</b> — ${esc(r.message)}</li>`).join('')}</ul>` : ''}
    <div class="settings-grid" style="margin-top:12px">
      <label class="field"><span>Un dossier du bureau s'ouvre dans</span><select data-bf="dossiers">${[['archiviste', 'Archiviste'], ['systeme', 'Le gestionnaire de fichiers (Nemo)']].map(([k, l]) => `<option value="${k}" ${b.dossiers === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label class="field"><span>Nouvelle discussion dans le volet</span><select data-bf="conv_heures">${[[1, 'Après 1 heure sans échange'], [4, 'Après 4 heures sans échange (conseillé)'], [12, 'Après 12 heures sans échange'], [24, 'Après 24 heures sans échange'], [0, 'Jamais : toujours la même discussion']].map(([k, l]) => `<option value="${k}" ${+b.conv_heures === k ? 'selected' : ''}>${l}</option>`).join('')}</select><small>Un vieux sujet ne pollue pas la question suivante. L'ancienne discussion reste dans l'onglet Discussion.</small></label>
      <label class="field"><span>Position du volet</span><select data-bf="volet_cote">${[['droite', 'À droite de l\'écran'], ['gauche', 'À gauche de l\'écran']].map(([k, l]) => `<option value="${k}" ${(b.volet_cote || 'droite') === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      ${(b.ecrans || []).length > 1 ? `<label class="field"><span>Écran du bureau Archiviste</span><select data-bf="ecran"><option value="principal" ${b.ecran === null || b.ecran === undefined ? 'selected' : ''}>L'écran principal</option>${b.ecrans.map((e) => `<option value="${e.index}" ${b.ecran === e.index ? 'selected' : ''}>Écran ${e.index + 1} — ${esc(e.nom)} (${e.largeur} × ${e.hauteur})${e.principal ? ', principal' : ''}</option>`).join('')}</select><small>Les icônes et le volet s'affichent sur cet écran.</small></label>` : ''}
      <label class="field"><span>Raccourcis par-dessus les applis</span><select data-bf="dock_bord">${[['1', 'Pousser la souris contre le bord du volet'], ['0', 'Non']].map(([k, l]) => `<option value="${k}" ${(b.dock_bord !== false) === (k === '1') ? 'selected' : ''}>${l}</option>`).join('')}</select><small>Une appli en plein écran ? Pousse la souris contre le bord ${b.volet_cote === 'gauche' ? 'gauche' : 'droit'} de l'écran : la colonne des raccourcis apparaît, sans rien réduire. Aussi avec Super + Espace.</small></label>
            <label class="field"><span>Fond d'écran</span><select data-bf="fond">${[['auto', 'Celui de Cinnamon (conseillé)'], ['archiviste', 'Dessiné par Archiviste (si le fond reste noir)']].map(([k, l]) => `<option value="${k}" ${b.fond === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
    </div>
    <dl class="muted" style="display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:12px 0 0;font-size:13px">
      <dt>Demander partout</dt><dd style="margin:0">${b.touche ? `<span class="kbd">${esc(b.touche_label)}</span> ouvre une petite fenêtre « Demander à l'Archiviste » par-dessus tes fenêtres` : b.actif ? 'pas de raccourci clavier (voir Paramètres système › Clavier, commande <code>archiviste --demander</code>)' : 'actif avec le bureau'}</dd>
      <dt>Applis ouvertes</dt><dd style="margin:0">${b.fenetres ? '✓ un repère sur le raccourci du volet quand l\'appli est ouverte ; un clic la ramène devant ou la réduit' : b.actif ? '— suivi indisponible : dans un terminal, <code>sudo apt install gir1.2-wnck-3.0</code>, puis relance Archiviste' : 'actif avec le bureau'}</dd>
      <dt>Au démarrage</dt><dd style="margin:0">${b.demarrage ? '✓ le bureau s\'affiche à l\'ouverture de session' : '—'}</dd>
      <dt>En cas de souci</dt><dd style="margin:0">dans un terminal : <code>archiviste --sans-bureau</code> rend le bureau à Nemo</dd>
    </dl>
    <div class="row wrap" style="margin-top:12px"><button class="btn sm" data-bu="raz">${ic('undo', 'sm')} Raccourcis par défaut</button><button class="btn sm" data-bu="fondcin">${ic('image', 'sm')} Changer le fond d'écran…</button></div>`;
  el.onchange = async (e) => {
    const k = e.target.dataset.bf;
    if (!k) return;
    try { await post('/api/bureau/reglages', { [k]: e.target.value }); toast('Bureau mis à jour', 'ok'); } catch (err) { toast(err.message, 'err'); }
  };
  el.onclick = async (e) => {
    const btn = e.target.closest('[data-bu]');
    if (!btn) return;
    const a = btn.dataset.bu;
    if (a === 'raz') {
      if (!(await ask('Remettre les raccourcis du volet par défaut (Archiviste, Grimoire, tes dossiers, Terminal) ?', { ok: 'Remettre' }))) return;
      try { await post('/api/raccourcis/defaut'); toast('Raccourcis remis par défaut', 'ok'); } catch (err) { toast(err.message, 'err'); }
      return;
    }
    if (a === 'fondcin') { try { await post('/api/systeme/reglages', { module: 'backgrounds' }); } catch (err) { toast(err.message, 'err'); } return; }
    if (a === 'off' && !(await ask('Rendre le bureau à Nemo ? Les icônes de Mint reviennent, le volet et Super + Espace disparaissent. Tes raccourcis sont gardés.', { ok: 'Rendre à Nemo' }))) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Un instant…';
    try {
      const r = await post('/api/bureau/activer', { actif: a === 'on' });
      if (!r.fenetre && a === 'on') toast('Ouvre Archiviste depuis le menu pour afficher le bureau.', 'info', { timeout: 8000 });
      renderBureauCard(r.rapport);
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  };
}
function updLine() {
  const i = UPD.info;
  if (!i) return '—';
  if (i.relancer) return `version ${esc(i.installee)} installée : relance Archiviste`;
  if (i.disponible) return `<b>version ${esc(i.derniere.version)} disponible</b>`;
  if (i.ignoree) return `version ${esc(i.derniere.version)} mise de côté (tu en es revenu) — « Vérifier maintenant » permet d'y retourner`;
  if (i.erreur) return esc(i.erreur);
  return i.verifie ? `à jour (vérifié ${fmtDate(i.verifie)})` : 'pas encore vérifié';
}
function renderRoots() {
  $('#stRoots').innerHTML = roots.map((r, i) => `<div class="root-item"><span class="grow ellipsis">${esc(r)}${r === S.home ? ' <span class="faint">(dossier personnel)</span>' : ''}</span><button class="icon-btn sm" data-act="rmRoot" data-i="${i}" title="Retirer" ${roots.length < 2 ? 'disabled' : ''}>${ic('x', 'sm')}</button></div>`).join('');
}
function bindSettings() {
  const v = $('#view-settings');
  const f = (k) => $(`[data-f="${k}"]`, v);
  v.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'rmRoot') { roots.splice(+b.dataset.i, 1); renderRoots(); }
    if (act === 'addRoot') { const p = $('#stNewRoot').value.trim(); if (p && !roots.includes(p)) { roots.push(p); renderRoots(); $('#stNewRoot').value = ''; } }
    if (act === 'pickRoot') toast('Le sélecteur ne montre que les dossiers déjà autorisés : tape le chemin complet (ex. /media/…) puis « Ajouter ».');
    if (act === 'test') {
      try { S.settings = await post('/api/settings', { ollama_url: f('ollama_url').value }); } catch (err) { return toast(err.message, 'err'); }
      const st = await refreshStatus();
      $('[data-test]', v).textContent = st.ok ? `✓ Connecté — Ollama ${st.version || ''}, ${st.models.length} modèle(s) installé(s)` : `✗ ${st.error || 'Pas de connexion'}`;
    }
    if (act === 'save') {
      const body = {
        ollama_url: f('ollama_url').value, model: f('model').value, num_ctx: +f('num_ctx').value, temperature: +f('temperature').value,
        keep_alive: f('keep_alive').value, think: f('think').checked, prenom: f('prenom').value, theme: f('theme').value,
        system_prompt: f('system_prompt').value, show_hidden: f('show_hidden').checked, roots, maj_auto: f('maj_auto').checked,
      };
      try {
        S.settings = { ...S.settings, ...(await post('/api/settings', body)) };
        applyTheme(); await refreshStatus();
        F.hidden = S.settings.show_hidden; F.path = null;
        if (F.built) $('#fHiddenBtn').classList.toggle('on', F.hidden);
        toast('Réglages enregistrés', 'ok');
        renderSettings();
      } catch (err) { toast(err.message, 'err'); }
    }
    if (act === 'checkUpdate') {
      b.disabled = true;
      const i = await refreshUpdate(true);
      b.disabled = false;
      const line = $('[data-maj]', v); if (line) line.innerHTML = updLine();
      if (i?.ignoree) {  // la version dont on est revenu : proposée seulement si on le demande
        if (await ask(`La version ${i.derniere.version} est celle que tu as quittée en revenant à la précédente.\nL'installer quand même ?`, { ok: 'Oui, l\'installer' })) {
          try { S.settings = { ...S.settings, ...(await post('/api/settings', { maj_ignoree: '' })) }; } catch (err) { return toast(err.message, 'err'); }
          await refreshUpdate(true);
          showUpdateModal();
        }
        return;
      }
      if (i?.disponible || i?.relancer) showUpdateModal();
      else toast(i?.erreur || `Archiviste est à jour (${i?.actuelle || ''}).`, i?.erreur ? 'err' : 'ok');
    }
    if (act === 'rollback') showRollbackModal();
    if (act === 'export') {
      const data = await api('/api/export');
      saveTextToFile(JSON.stringify(data, null, 2), `archiviste-agents-prompts-${stamp()}.json`);
    }
    if (act === 'import') $('#stImport').click();
  });
}
async function importBackup(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    const r = await post('/api/import', data);
    await Promise.all([loadAgents(), loadPrompts()]);
    toast(`Importé : ${r.agents} agent(s), ${r.prompts} prompt(s)`, 'ok');
  } catch (err) { toast(`Import impossible : ${err.message}`, 'err'); }
}
function applyTheme() { document.documentElement.dataset.theme = S.settings.theme || 'auto'; }
RENDER.settings = async () => { await refreshStatus(); renderSettings(); };

// ═════════════════════════════════════════════════════════════
//  Mises à jour (releases GitHub)
// ═════════════════════════════════════════════════════════════
const UPD = { info: null, poll: null, modal: null };
async function refreshUpdate(force = false) {
  try { UPD.info = force ? await post('/api/update/check') : await api('/api/update'); } catch { return null; }
  renderUpdatePill();
  return UPD.info;
}
function renderUpdatePill() {
  const el = $('#updatePill');
  const i = UPD.info;
  if (!el) return;
  if (i && i.relancer) {
    el.innerHTML = `${ic('refresh')}<div class="grow ellipsis"><span>Mise à jour installée</span><small>Relancer pour passer en ${esc(i.installee)}</small></div>`;
    el.hidden = false;
  } else if (i && i.disponible) {
    el.innerHTML = `${ic('download')}<div class="grow ellipsis"><span>Version ${esc(i.derniere.version)} disponible</span><small>Clique pour l'installer</small></div>`;
    el.hidden = false;
  } else el.hidden = true;
}
async function relaunchApp() {
  try {
    const r = await post('/api/app/relaunch');
    if (r.ok) toast('Archiviste redémarre…');
    else toast(r.message, 'info', { timeout: 8000 });
  } catch (e) { toast(e.message, 'err'); }
}
function updateModalBody(i) {
  if (i.relancer) {
    return `<div class="banner">${ic('check')}<div><b>Archiviste ${esc(i.installee)} est installé.</b><br>Relance l'appli pour l'utiliser (tes agents, prompts et discussions sont conservés).</div></div>`;
  }
  const d = i.derniere || {};
  return `<p style="margin:0">Tu as la version <b>${esc(i.actuelle)}</b>. La version <b>${esc(d.version)}</b> est disponible${d.taille ? ` (${fmtSize(d.taille)})` : ''}.</p>
    ${d.notes ? `<div class="notes-maj md">${md(d.notes)}</div>` : ''}
    <p class="muted" style="font-size:12.5px;margin:0">Archiviste télécharge le paquet depuis GitHub, vérifie son empreinte, puis l'installe : ton mot de passe est demandé par une fenêtre de Mint. Il te proposera ensuite de redémarrer.</p>`;
}
function showUpdateModal() {
  const i = UPD.info;
  if (!i || (!i.disponible && !i.relancer)) return;
  UPD.modal?.close(true);
  const m = openModal({
    title: i.relancer ? 'Mise à jour installée' : `Archiviste ${i.derniere.version}`,
    body: updateModalBody(i),
    footer: i.relancer
      ? `<button class="btn" data-close>Plus tard</button><button class="btn primary" data-u="relaunch">${ic('refresh', 'sm')} Relancer maintenant</button>`
      : `<button class="btn" data-close>Plus tard</button><button class="btn primary" data-u="install">${ic('download', 'sm')} Télécharger et installer</button>`,
    onClose: () => { UPD.modal = null; },
  });
  UPD.modal = m;
  const relaunchFooter = () => { m.mf.innerHTML = `<button class="btn" data-close>Plus tard</button><button class="btn primary" data-u="relaunch">${ic('refresh', 'sm')} Relancer maintenant</button>`; };
  m.el.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-u]');
    if (!b) return;
    if (b.dataset.u === 'relaunch') return relaunchApp();
    const mode = b.dataset.u === 'installateur' ? 'installateur' : 'auto';
    const ver = i.derniere?.version || '';
    $$('[data-u]', m.el).forEach((x) => { x.disabled = true; });
    b.innerHTML = '<span class="spinner"></span> Installation…';
    if (mode === 'auto') {
      m.mb.innerHTML = `<div class="banner">${ic('info')}<div><b>Téléchargement puis installation d'Archiviste ${esc(ver)}.</b><br>Une fenêtre de Mint va te demander ton mot de passe : il faut les droits d'administrateur pour installer un logiciel. Si une autre installation est en cours, Archiviste attend qu'elle se termine.</div></div>`;
    }
    let r;
    try { r = await post('/api/update/install', { mode }); } catch (err) {
      toast(err.message, 'err');
      $$('[data-u]', m.el).forEach((x) => { x.disabled = false; });
      b.innerHTML = `${ic('download', 'sm')} Réessayer`;
      return;
    }
    if (r.installe) {
      const st = await refreshUpdate();
      m.mb.innerHTML = updateModalBody(st && st.relancer ? st : { relancer: true, installee: r.version });
      relaunchFooter();
      return;
    }
    if (r.installe === false) {
      m.mb.innerHTML = `<div class="banner danger">${ic('alert')}<div><b>${esc(r.erreur)}</b></div></div>
        ${r.sortie ? `<details style="margin-top:10px"><summary class="muted" style="cursor:pointer;font-size:12.5px">Détails techniques</summary><pre class="pv-text" style="max-height:220px;white-space:pre-wrap">${esc(r.sortie)}</pre></details>` : ''}
        <p class="muted" style="font-size:12.5px;margin:10px 0 0">Autre solution, dans un terminal : <code>sudo apt install ${esc(r.fichier)}</code></p>`;
      m.mf.innerHTML = `<button class="btn" data-close>Fermer</button><button class="btn" data-u="installateur">Avec l'installateur de Mint</button><button class="btn primary" data-u="install">${ic('refresh', 'sm')} Réessayer</button>`;
      return;
    }
    // installateur graphique de Mint (au choix, ou si la fenêtre de mot de passe n'existe pas sur ce PC)
    m.mb.innerHTML = r.ouvert
      ? `<div class="banner">${ic('info')}<div><b>L'installateur de paquets s'est ouvert.</b><br>Clique sur « Installer » et saisis ton mot de passe. Cette fenêtre te proposera ensuite de relancer Archiviste.</div></div>`
      : `<div class="banner">${ic('info')}<div>Paquet téléchargé : <code>${esc(r.fichier)}</code><br>Dans un terminal : <code>sudo apt install ${esc(r.fichier)}</code></div></div>`;
    b.innerHTML = '<span class="spinner"></span> En attente de l\'installation…';
    clearInterval(UPD.poll);
    UPD.poll = setInterval(async () => {
      const st = await refreshUpdate();
      if (st && st.relancer) {
        clearInterval(UPD.poll);
        m.mb.innerHTML = updateModalBody(st);
        relaunchFooter();
      }
    }, 4000);
    setTimeout(() => clearInterval(UPD.poll), 20 * 60 * 1000);
  });
}

// Revenir à la version précédente : réinstalle le paquet d'avant (gardé sur le PC, sinon repris sur GitHub).
async function showRollbackModal() {
  let p;
  try { p = await api('/api/update/precedente'); } catch (e) { return toast(e.message, 'err'); }
  if (!p.trouvee) return toast('Aucune version précédente n\'a été trouvée.', 'info', { timeout: 6000 });
  const m = openModal({
    title: `Revenir à Archiviste ${p.version}`,
    body: `<p style="margin:0">Tu as la version <b>${esc(p.actuelle)}</b>. Archiviste va réinstaller la version <b>${esc(p.version)}</b> (${p.source === 'pc' ? 'paquet gardé sur ce PC' : 'téléchargée depuis GitHub, empreinte vérifiée'}).</p>
      <p class="muted" style="font-size:12.5px;margin:10px 0 0">Tes fichiers, réglages, agents, prompts et discussions ne sont pas touchés. Ton mot de passe est demandé par une fenêtre de Mint. La version ${esc(p.actuelle)} ne te sera plus proposée d'office ensuite.</p>`,
    footer: `<button class="btn" data-close>Annuler</button><button class="btn primary" data-r="go">${ic('undo', 'sm')} Revenir à la ${esc(p.version)}</button>`,
  });
  m.el.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-r]');
    if (!b) return;
    if (b.dataset.r === 'relaunch') return relaunchApp();
    b.disabled = true;
    b.innerHTML = '<span class="spinner"></span> Installation…';
    let r;
    try { r = await post('/api/update/revenir'); } catch (err) { toast(err.message, 'err'); b.disabled = false; b.innerHTML = `${ic('undo', 'sm')} Réessayer`; return; }
    if (r.installe) {
      await refreshUpdate();
      m.mb.innerHTML = `<div class="banner">${ic('check')}<div><b>Archiviste ${esc(r.version)} est réinstallé.</b><br>Relance l'appli pour l'utiliser.${r.maj_auto === false ? '<br>La vérification automatique des mises à jour est coupée (cette ancienne version ne sait pas mettre une version de côté) : « Vérifier maintenant » reste disponible dans Réglages → À propos.' : ''}</div></div>`;
      m.mf.innerHTML = `<button class="btn" data-close>Plus tard</button><button class="btn primary" data-r="relaunch">${ic('refresh', 'sm')} Relancer maintenant</button>`;
    } else if (r.installe === false) {
      m.mb.innerHTML = `<div class="banner danger">${ic('alert')}<div><b>${esc(r.erreur)}</b></div></div>${r.sortie ? `<details style="margin-top:10px"><summary class="muted" style="cursor:pointer;font-size:12.5px">Détails techniques</summary><pre class="pv-text" style="max-height:220px;white-space:pre-wrap">${esc(r.sortie)}</pre></details>` : ''}
        <p class="muted" style="font-size:12.5px;margin:10px 0 0">Autre solution, dans un terminal : <code>sudo apt install --allow-downgrades ${esc(r.fichier)}</code></p>`;
      m.mf.innerHTML = '<button class="btn" data-close>Fermer</button>';
    } else {
      m.mb.innerHTML = `<div class="banner">${ic('info')}<div>Paquet prêt : <code>${esc(r.fichier)}</code><br>Dans un terminal : <code>sudo apt install --allow-downgrades ${esc(r.fichier)}</code></div></div>`;
      m.mf.innerHTML = '<button class="btn" data-close>Fermer</button>';
    }
  });
  return m;
}

// ═════════════════════════════════════════════════════════════
//  Démarrage
// ═════════════════════════════════════════════════════════════
async function init() {
  $$('[data-icon]').forEach((el) => { el.outerHTML = ic(el.dataset.icon); });
  $('#nav').addEventListener('click', (e) => { const b = e.target.closest('button[data-view]'); if (b) go(b.dataset.view); });
  $('#statusPill').addEventListener('click', () => go('settings'));
  $('#updatePill').addEventListener('click', () => (UPD.info?.relancer && !UPD.info?.disponible ? relaunchApp() : showUpdateModal()));
  try {
    [S.settings, S.tools] = await Promise.all([api('/api/settings'), api('/api/tools')]);
  } catch (e) {
    document.body.innerHTML = `<div class="empty" style="padding-top:20vh"><h2>Archiviste ne répond pas</h2><p>${esc(e.message)}</p><p class="muted">Ferme la fenêtre et relance Archiviste. Pour voir le détail : <code>ARCHIVISTE_DEBUG=1 archiviste</code> dans un terminal.</p></div>`;
    return;
  }
  S.home = S.settings.home;
  applyTheme();
  await Promise.all([loadAgents(), loadPrompts()]);
  bindAgents(); bindPrompts(); bindTrash(); bindSettings();
  refreshStatus();
  setInterval(() => { if (!document.hidden) refreshStatus(); }, 30000);
  clipListener = refreshSelection;
  clipLoad();
  // une tâche finie : le dossier affiché est relu s'il est concerné
  taskDone = (t) => {
    if (S.view !== 'files') return;
    const touched = [t.dossier, ...(t.resultat || []).map(dirname)];
    if (touched.includes(F.path) || t.genre === 'deplacement') { if (F.search) runSearch(F.search.query); else loadDir(); }
    if (t.etat === 'finie' && t.genre === 'extraction' && t.dossier === F.path && t.resultat[0]) setTimeout(() => selectPath(t.resultat[0]), 300);
  };
  tasksPoll();
  window.addEventListener('focus', clipLoad);  // ce qui a été coupé dans l'autre fenêtre (bureau ↔ fenêtre principale)
  api('/api/index').then((x) => { S.index = x; }).catch(() => {});
  setInterval(() => api('/api/index').then((x) => { S.index = x; }).catch(() => {}), 60000);
  refreshUpdate();
  setTimeout(refreshUpdate, 25000);
  setTimeout(refreshUpdate, 60000);
  setInterval(refreshUpdate, 30 * 60 * 1000);
  routeFromHash();
}
if (document.getElementById('app')) init();
