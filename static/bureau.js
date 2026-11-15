/* ═══════════════════════════════════════════════════════════
   Archiviste — bureau
   Icônes du dossier Bureau · barre « Demande à l'Archiviste » · volet (raccourcis, à ranger, discussion)
   Même page en mode « demander » : la petite fenêtre de Super + Espace.
   S'appuie sur les outils d'app.js (api, toast, menus, fenêtres, markdown…).
   ═══════════════════════════════════════════════════════════ */
'use strict';

const Q = new URLSearchParams(location.search);
const MODE = Q.get('mode') === 'demander' ? 'demander' : 'bureau';
const D = {
  b: null, items: [], sel: new Set(), anchor: null, sig: '', rv: '', apps: null, favs: [], sc: [], todo: null,
  conv: null, busy: false, ctrl: null, atts: [], editSc: false, ownFond: Q.get('fond') === '1', fondKey: '',
  cv: undefined, resizing: false, autoNew: false,
  fv: undefined, win: { dispo: false, groupes: [], map: {}, sig: '' }, scDrag: false, winDirty: false,
};
const IS_WRITING = () => { const a = document.activeElement; return a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable); };
const appIconUrl = (name, size = 64) => `/api/icone?t=${enc(TOKEN)}&n=${enc(name)}&s=${size}`;
const norm = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
ICONS.vide = 'M0 0';  // icône invisible : aligne les entrées de menu
const fileUri = (p) => 'file://' + p.split('/').map(encodeURIComponent).join('/');

// La fenêtre principale d'Archiviste remplace « go » d'app.js : depuis le bureau, on ouvre la fenêtre.
// eslint-disable-next-line no-global-assign
go = (view, opts = {}) => openMain({ vue: view, chemin: opts.path, select: opts.select, conv: opts.conv });

// ───────────────────────── Marges (panneau de Cinnamon) ─────────────────────────
function setMarges(m = {}) {
  const r = document.documentElement.style;
  for (const [k, v] of Object.entries({ h: '--mt', b: '--mb', g: '--ml', d: '--mr' })) r.setProperty(v, `${Math.max(0, +(m[k] || 0))}px`);
}
window.archivisteMarges = setMarges;
setMarges({ h: Q.get('h'), b: Q.get('b'), g: Q.get('g'), d: Q.get('d') });

// ───────────────────────── Icônes (logo-style : cuivre, parchemin) ─────────────────────────
const GLYPH = {
  home: '<path d="M24 41 36 31 48 41v10H24z" fill="none" stroke="#fbeedc" stroke-width="3" stroke-linejoin="round"/>',
  down: '<path d="M36 30v16M29 40l7 7 7-7" fill="none" stroke="#fbeedc" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>',
  photo: '<path d="M22 51l9-10 6 6 5-5 8 9z" fill="#fbeedc" opacity=".9"/><circle cx="44" cy="35" r="3" fill="#fbeedc"/>',
  doc: '<path d="M28 31h16M28 37h16M28 43h10" stroke="#fbeedc" stroke-width="3" stroke-linecap="round"/>',
  music: '<path d="M33 48V34l11-3v14" fill="none" stroke="#fbeedc" stroke-width="3" stroke-linejoin="round"/><circle cx="30" cy="48" r="3.5" fill="#fbeedc"/><circle cx="41" cy="45" r="3.5" fill="#fbeedc"/>',
  video: '<path d="M31 32v16l13-8z" fill="#fbeedc"/>',
  desk: '<path d="M25 33h22v13H25zM31 50h10" fill="none" stroke="#fbeedc" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>',
  link: '<path d="M27 47l18-18M40 29h5v5" fill="none" stroke="#fbeedc" stroke-width="3" stroke-linecap="round"/>',
};
function folderSvg(glyph = '') {
  return `<svg viewBox="0 0 72 72"><path d="M6 18a5 5 0 0 1 5-5h16l6 6h28a5 5 0 0 1 5 5v6H6z" fill="#9a5528"/>
    <rect x="6" y="23" width="60" height="38" rx="5" fill="#c9804f"/><rect x="6" y="23" width="60" height="5" fill="#d9925f" opacity=".7"/>${GLYPH[glyph] || ''}</svg>`;
}
const KIND_COLOR = { pdf: '#c0392b', doc: '#3d6fb4', sheet: '#2f8f5b', slides: '#d0702c', image: '#4f8a3a', video: '#8a55b0', audio: '#c04d82',
  archive: '#b08a1c', code: '#2a8a8a', text: '#6b5d52', book: '#8b5e3c', app: '#5d5d5d' };
function fileSvg(e) {
  const color = e.ext === 'pdf' ? KIND_COLOR.pdf : KIND_COLOR[e.kind] || '#7a6a5a';
  const label = esc((e.ext || 'fichier').toUpperCase().slice(0, 4));
  return `<svg viewBox="0 0 72 72"><path d="M16 6h28l14 14v42a4 4 0 0 1-4 4H16a4 4 0 0 1-4-4V10a4 4 0 0 1 4-4z" fill="#f4ebdc"/>
    <path d="M44 6v10a4 4 0 0 0 4 4h10z" fill="#d9ccb6"/><rect x="18" y="26" width="26" height="3" rx="1.5" fill="#cbbda6"/>
    <rect x="18" y="32" width="32" height="3" rx="1.5" fill="#cbbda6"/><rect x="18" y="38" width="22" height="3" rx="1.5" fill="#cbbda6"/>
    <rect x="9" y="46" width="44" height="15" rx="3" fill="${color}"/>
    <text x="31" y="57.5" text-anchor="middle" font-family="Inter, 'DejaVu Sans', sans-serif" font-weight="700" font-size="${label.length > 3 ? 9.5 : 10.5}" fill="#fff" letter-spacing=".5">${label}</text></svg>`;
}
const TRASH_SVG = (full) => `<svg viewBox="0 0 72 72"><rect x="17" y="20" width="38" height="44" rx="5" fill="#e9dcc6"/>
  <rect x="13" y="13" width="46" height="8" rx="3" fill="#d4c4aa"/><rect x="29" y="8" width="14" height="6" rx="2" fill="#d4c4aa"/>
  ${full ? '<path d="M24 22l6-9 9 6 10-7 3 10z" fill="#f4ebdc" stroke="#b5a387" stroke-width="1.5"/>' : ''}
  <path d="M28 30v26M36 30v26M44 30v26" stroke="#b5a387" stroke-width="3" stroke-linecap="round"/></svg>`;
const DRIVE_SVG = `<svg viewBox="0 0 72 72"><path d="M14 40l7-22a5 5 0 0 1 5-3h20a5 5 0 0 1 5 3l7 22z" fill="#d4c4aa"/>
  <rect x="10" y="38" width="52" height="20" rx="5" fill="#e9dcc6"/><circle cx="51" cy="48" r="3" fill="#8cb874"/><path d="M18 48h18" stroke="#b5a387" stroke-width="3" stroke-linecap="round"/></svg>`;
const APP_FALLBACK = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="6" y="6" width="52" height="52" rx="14" fill="#3a2e27"/><rect x="18" y="18" width="28" height="28" rx="7" fill="none" stroke="#c9804f" stroke-width="4"/></svg>')}`;
document.addEventListener('error', (e) => { const t = e.target; if (t.tagName === 'IMG' && t.classList.contains('app-ic') && t.src !== APP_FALLBACK) t.src = APP_FALLBACK; }, true);

function folderGlyph(path) {
  if (!D.b) return '';
  const n = norm(basename(path));
  if (path === D.b.home) return 'home';
  if (path === D.b.telechargements || n === 'downloads') return 'down';
  if (path === D.b.documents) return 'doc';
  if (/^(images|pictures|photos?)/.test(n)) return 'photo';
  if (/^(musique|music)$/.test(n)) return 'music';
  if (/^(videos?)$/.test(n)) return 'video';
  return '';
}
const THUMB_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg', 'avif']);
function itemPic(it) {
  if (it.type === 'home') return folderSvg('home');
  if (it.type === 'trash') return TRASH_SVG(D.trashFull);
  if (it.type === 'volume') return DRIVE_SVG;
  const e = it.e;
  if (e.lanceur) {
    return `<img class="app-ic" src="${appIconUrl(e.lanceur.icone || 'application-x-executable')}" alt="" draggable="false">${e.lanceur.fiable ? '' : '<span class="trust" title="Lanceur pas encore marqué comme fiable">!</span>'}`;
  }
  if (e.dir) return folderSvg(e.link ? 'link' : folderGlyph(e.path));
  if (e.kind === 'image' && THUMB_EXTS.has(e.ext) && (e.size || 0) < 15e6) {
    return `<img class="thumb" src="${rawUrl(e.path)}&v=${Math.round(e.mtime)}" alt="" loading="lazy" draggable="false">`;
  }
  return fileSvg(e);
}

// ───────────────────────── Contenu du bureau ─────────────────────────
async function loadElements() {
  let r;
  try { r = await api('/api/bureau/elements'); } catch (e) { return toast(e.message, 'err'); }
  D.sig = r.sig;
  D.trashFull = r.corbeille > 0;
  const tri = D.b.tri || 'nom';
  const cmp = (a, b) => {
    if (a.dir !== b.dir) return a.dir ? -1 : 1;
    if (tri === 'date') return b.mtime - a.mtime;
    if (tri === 'type' && a.ext !== b.ext) return (a.ext || '').localeCompare(b.ext || '');
    return a.name.localeCompare(b.name, 'fr', { numeric: true, sensitivity: 'base' });
  };
  const label = (e) => (e.lanceur ? e.lanceur.nom : e.name);
  D.items = [
    { key: 'home', type: 'home', label: 'Dossier personnel', path: r.home },
    { key: 'trash', type: 'trash', label: 'Corbeille' },
    ...r.volumes.map((v) => ({ key: 'vol:' + v.path, type: 'volume', label: v.nom, path: v.path })),
    ...r.elements.sort(cmp).map((e) => ({ key: e.path, type: 'entry', label: label(e), path: e.path, e })),
  ];
  const keys = new Set(D.items.map((x) => x.key));
  D.sel = new Set([...D.sel].filter((k) => keys.has(k)));
  renderIcons();
}
function renderIcons() {
  $('#icons').innerHTML = D.items.map((it, i) => {
    const drag = it.type === 'entry' || it.type === 'home';
    return `<div class="dicon ${D.sel.has(it.key) ? 'sel' : ''}" data-i="${i}" role="option" ${drag ? 'draggable="true"' : ''} title="${esc(it.path ? tildify(it.path) : it.label)}">
      <div class="pic">${itemPic(it)}</div><div class="lbl">${esc(it.label)}</div></div>`;
  }).join('');
  iconFades();
}
// Les icônes ne passent plus sous le volet : la grille s'arrête à son bord et défile (molette) s'il y en a trop.
// Un fondu à gauche / à droite signale qu'il en reste.
function iconFades() {
  const el = $('#icons');
  if (!el) return;
  const left = el.scrollLeft > 2;
  const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
  el.classList.toggle('fade-l', left);
  el.classList.toggle('fade-r', right);
  $('#icPrev').hidden = !left;
  $('#icNext').hidden = !right;
}
function refreshSel() { $$('#icons .dicon').forEach((el) => el.classList.toggle('sel', D.sel.has(D.items[+el.dataset.i].key))); }
const selItems = () => D.items.filter((x) => D.sel.has(x.key));
const selEntries = () => selItems().filter((x) => x.type === 'entry');
function selectOnly(it) { D.sel = new Set(it ? [it.key] : []); D.anchor = it ? D.items.indexOf(it) : null; refreshSel(); }

async function poll() {
  if (document.hidden) return;
  let r;
  try { r = await api('/api/bureau/sig'); } catch { return; }
  if (r.sig !== D.sig) { await loadElements(); loadTodo(); }
  if (r.rv !== D.rv) {
    const first = !D.rv;
    D.rv = r.rv;
    if (!first && !D.resizing) {
      try { D.b = await api('/api/bureau'); } catch { /* */ }
      applyVolet(); loadShortcuts();
    }
  }
  // la discussion du volet a avancé ailleurs (fenêtre « Demander », fenêtre principale) : on la remet à jour
  if (r.cv !== D.cv) { D.cv = r.cv; if (!D.busy) syncConv(false); }
  if (r.fv !== D.fv) { D.fv = r.fv; loadWindows(); }  // une fenêtre s'est ouverte, fermée, réduite…
}

// ───────────────────────── Ouvrir, lancer ─────────────────────────
async function openMain(data = {}) {
  const body = Object.fromEntries(Object.entries(data).filter(([, v]) => v));
  try {
    const r = await post('/api/app/ouvrir', body);
    if (!r.ok) toast(r.message || 'Ouvre Archiviste depuis le menu.');
    else if (MODE === 'demander') closePopup();
  } catch (e) { toast(e.message, 'err'); }
}
function openFolder(p) {
  if (D.b?.dossiers === 'systeme') return openWithSystem(p);
  return openMain({ vue: 'files', chemin: p });
}
async function launchApp(id, nom, fichiers, fresh = false) {
  try {
    // déjà ouverte : sa fenêtre revient devant au lieu d'en lancer une autre (sauf « Nouvelle fenêtre »)
    const r = await post('/api/apps/lancer', { id, fichiers, ramener: !fresh && !fichiers?.length });
    toast(r.ramenee ? `${nom || r.nom} est déjà ouvert : je le ramène devant` : `Lancement de ${nom || r.nom || 'l\'application'}…`);
    if (MODE === 'demander') closePopup();
    else setTimeout(loadWindows, 1200);
  } catch (e) { toast(e.message, 'err'); }
}
async function launchLauncher(path) {
  try {
    let r = await post('/api/apps/lancer', { fichier: path });
    if (r.confiance) {
      const ok = await ask(`« ${r.nom} » n'est pas encore marqué comme fiable.\nUn lanceur peut exécuter n'importe quelle commande : ne le lance que si tu sais d'où il vient.`, { title: 'Lanceur inconnu', ok: 'Faire confiance et lancer' });
      if (!ok) return;
      r = await post('/api/apps/lancer', { fichier: path, confiance: true });
      loadElements();
    }
    if (r.ok) toast('Lancement…');
  } catch (e) { toast(e.message, 'err'); }
}
function openFile(e) {
  if (e.dir) return openFolder(e.path);
  if (e.ext === 'desktop') return launchLauncher(e.path);
  if (hasGrimoire() && GRIM_FIRST.has(e.ext)) return openInGrimoire(e.path);
  return openWithSystem(e.path);
}
function openItem(it) {
  if (!it) return;
  if (it.type === 'home') return openFolder(it.path);
  if (it.type === 'trash') return openMain({ vue: 'trash' });
  if (it.type === 'volume') return post('/api/bureau/volume', { path: it.path, action: 'ouvrir' }).catch((e) => toast(e.message, 'err'));
  return openFile(it.e);
}
async function openWithMenu(e, x, y) {
  let r;
  try { r = await api(`/api/apps/pour?path=${enc(e.path)}`); } catch (err) { return toast(err.message, 'err'); }
  if (!r.apps.length) return toast('Aucune application installée ne déclare savoir ouvrir ce type de fichier.');
  showMenu(x, y, [{ header: 'Ouvrir avec' }, ...r.apps.map((a) => ({
    label: a.nom + (a.id === r.defaut ? ' — par défaut' : ''), sub: a.generique || '', icon: 'app',
    act: () => launchApp(a.id, a.nom, [e.path]),
  }))], { search: r.apps.length > 8 });
}

// ───────────────────────── Actions sur les fichiers ─────────────────────────
async function renameEntry(e) {
  const name = await promptText({ title: 'Renommer', label: tildify(dirname(e.path)), value: e.name, selectStem: !e.dir, ok: 'Renommer' });
  if (!name || name === e.name) return;
  try { const r = await post('/api/fs/rename', { path: e.path, new_name: name }); D.sel = new Set([r.vers]); await loadElements(); } catch (err) { toast(err.message, 'err'); }
}
async function trashPaths(paths) {
  if (!paths.length) return;
  // Comme dans la fenêtre principale : un dossier ou plusieurs éléments ne partent pas à la corbeille sur une
  // simple touche. (Un lien vers un dossier ne compte pas : seul le lien part, sa cible reste.)
  const folder = (p) => { const it = D.items.find((x) => x.path === p); return !it || (it.e?.dir && !it.e.link); };
  if (paths.length > 1 || paths.some(folder)) {
    const what = paths.length > 1 ? `ces ${paths.length} éléments` : `« ${basename(paths[0])} »`;
    if (!(await ask(`Mettre ${what} à la corbeille ?\nTu pourras les restaurer depuis la Corbeille (ici ou dans Nemo).`, { ok: 'Mettre à la corbeille', danger: true }))) return;
  }
  try {
    const r = await post('/api/fs/trash', { paths });
    if (r.erreurs.length) toast(r.erreurs.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
    if (r.ok.length) {
      const ids = r.ok.map((x) => x.corbeille);
      toast(`${r.ok.length} élément(s) mis à la corbeille`, 'ok', { label: 'Annuler', action: async () => { await post('/api/trash/restore', { ids }); loadElements(); } });
    }
  } catch (e) { toast(e.message, 'err'); }
  loadElements();
}
async function movePaths(paths, dest, copy) {
  try {
    const r = await post('/api/fs/move', { paths, dest_dir: dest, copy });
    if (r.erreurs.length) toast(r.erreurs.map((x) => `${basename(x.path)} : ${x.erreur}`).join('\n'), 'err');
    if (r.ok.length) toast(`${r.ok.length} élément(s) ${copy ? 'copié(s)' : 'déplacé(s)'} vers ${dest === D.b.dossier ? 'le bureau' : basename(dest)}`, 'ok');
    return r;
  } catch (e) { toast(e.message, 'err'); return null; } finally { loadElements(); }
}
async function newFolder() {
  const name = await promptText({ title: 'Nouveau dossier', label: 'Sur le bureau', value: 'Nouveau dossier', ok: 'Créer' });
  if (!name) return;
  try { const r = await post('/api/fs/mkdir', { dir: D.b.dossier, name }); D.sel = new Set([r.path || joinPath(D.b.dossier, name)]); loadElements(); } catch (e) { toast(e.message, 'err'); }
}
async function newTextFile() {
  const name = await promptText({ title: 'Nouveau fichier texte', label: 'Sur le bureau', value: 'Note.md', selectStem: true, ok: 'Créer' });
  if (!name) return;
  const path = joinPath(D.b.dossier, name);
  try { await post('/api/fs/write', { path, content: '', create_only: true }); D.sel = new Set([path]); await loadElements(); openWithSystem(path); } catch (e) { toast(e.message, 'err'); }
}
const pinEntry = (e) => pinShortcut(e.ext === 'desktop' && !e.dir ? 'app' : e.dir ? 'dossier' : 'fichier', e.path).then(loadShortcuts);

function setTri(t) { D.b.tri = t; post('/api/bureau/reglages', { tri: t }).catch(() => {}); loadElements(); }

// ───────────────────────── Menus contextuels ─────────────────────────
function itemMenu(x, y) {
  const its = selItems();
  if (!its.length) return;
  const one = its.length === 1 ? its[0] : null;
  const ents = selEntries();
  const paths = ents.map((it) => it.path);
  const m = [];
  if (one?.type === 'trash') {
    m.push({ label: 'Ouvrir la corbeille', icon: 'trash', kbd: 'Entrée', act: () => openItem(one) });
    return showMenu(x, y, m);
  }
  if (one?.type === 'volume') {
    m.push({ label: 'Ouvrir', icon: 'external', kbd: 'Entrée', act: () => openItem(one) });
    m.push({ label: 'Éjecter', icon: 'upload', act: async () => {
      const t = toast(`Éjection de « ${one.label} »…`, 'info', { sticky: true });
      try { await post('/api/bureau/volume', { path: one.path, action: 'ejecter' }); t.close(); toast(`« ${one.label} » peut être retiré`, 'ok'); loadElements(); } catch (e) { t.close(); toast(e.message, 'err'); }
    } });
    return showMenu(x, y, m);
  }
  if (one?.type === 'home') {
    m.push({ label: 'Ouvrir', icon: 'folder', kbd: 'Entrée', act: () => openItem(one) });
    m.push({ label: 'Ouvrir dans le gestionnaire de fichiers', icon: 'external', act: () => openWithSystem(one.path) });
    m.push({ label: 'Épingler aux raccourcis', icon: 'star', act: () => pinShortcut('dossier', one.path).then(loadShortcuts) });
    return showMenu(x, y, m);
  }
  const e = one?.e;
  if (e) {
    if (e.lanceur) {
      m.push({ label: 'Lancer', icon: 'play', kbd: 'Entrée', act: () => launchLauncher(e.path) });
      m.push({ label: 'Épingler aux raccourcis', icon: 'star', act: () => pinEntry(e) });
      m.push('sep');
    } else {
      m.push({ label: e.dir ? 'Ouvrir' : hasGrimoire() && GRIM_FIRST.has(e.ext) ? 'Ouvrir dans Grimoire' : 'Ouvrir', icon: e.dir ? 'folder' : hasGrimoire() && GRIM_FIRST.has(e.ext) ? 'quill' : 'external', kbd: 'Entrée', act: () => openFile(e) });
      if (!e.dir) m.push({ label: 'Ouvrir avec…', icon: 'external', act: () => openWithMenu(e, x, y) });
      if (grimOk(e) && !GRIM_FIRST.has(e.ext)) m.push({ label: 'Ouvrir dans Grimoire', icon: 'quill', act: () => openInGrimoire(e.path) });
      if (e.dir && D.b.dossiers !== 'systeme') m.push({ label: 'Ouvrir dans le gestionnaire de fichiers', icon: 'external', act: () => openWithSystem(e.path) });
      if (e.dir && D.b.dossiers === 'systeme') m.push({ label: 'Ouvrir dans Archiviste', icon: 'folder', act: () => openMain({ vue: 'files', chemin: e.path }) });
      m.push('sep');
      if (!e.dir) m.push({ label: 'Résumer avec l\'IA', icon: 'sparkles', act: () => askAbout([e.path], 'Résume ce document en quelques points clés.') });
      m.push({ label: 'En discuter', icon: 'chat', act: () => attachToChat([e.path]) });
      if (e.dir) m.push({ label: 'Ranger ce dossier avec l\'IA', icon: 'sparkles', act: () => openMain({ vue: 'sort', chemin: e.path }) });
      m.push('sep');
      m.push({ label: 'Épingler aux raccourcis', icon: 'star', act: () => pinEntry(e) });
    }
    m.push({ label: 'Renommer', icon: 'pencil', kbd: 'F2', act: () => renameEntry(e) });
    m.push({ label: 'Afficher dans Archiviste', icon: 'folder', act: () => openMain({ vue: 'files', chemin: dirname(e.path), select: e.path }) });
    m.push({ label: 'Copier le chemin', icon: 'copy', act: () => copyText(e.path) });
  } else if (paths.length) {
    m.push({ label: `Ouvrir les ${paths.length} éléments`, icon: 'external', act: () => ents.forEach((it) => openFile(it.e)) });
    m.push({ label: 'En discuter (joindre)', icon: 'chat', act: () => attachToChat(paths) });
    m.push({ label: 'Copier les chemins', icon: 'copy', act: () => copyText(paths.join('\n')) });
  }
  if (paths.length) {
    m.push('sep');
    m.push({ label: 'Mettre à la corbeille', icon: 'trash', kbd: 'Suppr', danger: true, act: () => trashPaths(paths) });
  }
  showMenu(x, y, m);
}
function deskMenu(x, y) {
  const tri = D.b.tri || 'nom';
  const ck = (t) => (tri === t ? 'check' : 'vide');
  showMenu(x, y, [
    { label: 'Nouveau dossier', icon: 'folderPlus', act: newFolder },
    { label: hasGrimoire() ? 'Nouveau document Word (Grimoire)' : 'Nouveau document Word', icon: 'doc', act: () => newOffice('docx', D.b.dossier).then(loadElements) },
    { label: hasGrimoire() ? 'Nouveau classeur Excel (Grimoire)' : 'Nouveau classeur Excel', icon: 'sheet', act: () => newOffice('xlsx', D.b.dossier).then(loadElements) },
    { label: 'Nouveau fichier texte', icon: 'filePlus', act: newTextFile },
    'sep',
    { label: 'Ranger le bureau avec l\'IA', icon: 'sparkles', act: () => openMain({ vue: 'sort', chemin: D.b.dossier }) },
    { header: 'Trier les icônes' },
    { label: 'Par nom', icon: ck('nom'), act: () => setTri('nom') },
    { label: 'Par date (récents d\'abord)', icon: ck('date'), act: () => setTri('date') },
    { label: 'Par type', icon: ck('type'), act: () => setTri('type') },
    'sep',
    { label: 'Ouvrir Archiviste', icon: 'external', act: () => openMain({}) },
    { label: D.b.volet ? 'Masquer le volet' : 'Afficher le volet', icon: 'panel', act: () => setVolet(!D.b.volet) },
    { label: 'Ouvrir le Bureau dans le gestionnaire de fichiers', icon: 'folder', act: () => openWithSystem(D.b.dossier) },
    'sep',
    { label: 'Changer le fond d\'écran…', icon: 'image', act: () => post('/api/systeme/reglages', { module: 'backgrounds' }).catch((e) => toast(e.message, 'err')) },
    { label: 'Écrans et résolution…', icon: 'sliders', act: () => post('/api/systeme/reglages', { module: 'display' }).catch((e) => toast(e.message, 'err')) },
    { label: 'Réglages du bureau Archiviste', icon: 'sliders', act: () => openMain({ vue: 'settings' }) },
  ]);
}

// ───────────────────────── Souris, clavier, glisser-déposer ─────────────────────────
function bindDesk() {
  const desk = $('#desk');
  const icons = $('#icons');
  let lasso = null;
  desk.addEventListener('mousedown', (ev) => {
    closeMenu();
    if (IS_WRITING()) document.activeElement.blur();
    const el = ev.target.closest('.dicon');
    if (el) {
      const i = +el.dataset.i;
      const it = D.items[i];
      if (ev.shiftKey && D.anchor !== null) {
        const [a, b] = [Math.min(D.anchor, i), Math.max(D.anchor, i)];
        D.sel = new Set(D.items.slice(a, b + 1).map((x) => x.key));
      } else if (ev.ctrlKey) {
        D.sel.has(it.key) ? D.sel.delete(it.key) : D.sel.add(it.key);
        D.anchor = i;
      } else if (!D.sel.has(it.key) || ev.button === 0 && D.sel.size === 1) {
        selectOnly(it);
      }
      refreshSel();
      desk.focus({ preventScroll: true });
      return;
    }
    if (ev.button !== 0) return;
    desk.focus({ preventScroll: true });
    const base = ev.ctrlKey ? new Set(D.sel) : new Set();
    lasso = { x: ev.clientX, y: ev.clientY, base, moved: false };
    if (!ev.ctrlKey) { D.sel.clear(); refreshSel(); }
  });
  window.addEventListener('mousemove', (ev) => {
    if (!lasso) return;
    const r = { l: Math.min(lasso.x, ev.clientX), t: Math.min(lasso.y, ev.clientY), r: Math.max(lasso.x, ev.clientX), b: Math.max(lasso.y, ev.clientY) };
    if (!lasso.moved && r.r - r.l < 4 && r.b - r.t < 4) return;
    lasso.moved = true;
    const box = $('#lasso');
    Object.assign(box.style, { left: r.l + 'px', top: r.t + 'px', width: (r.r - r.l) + 'px', height: (r.b - r.t) + 'px' });
    box.hidden = false;
    const sel = new Set(lasso.base);
    $$('#icons .dicon').forEach((el) => {
      const b = el.getBoundingClientRect();
      if (b.right > r.l && b.left < r.r && b.bottom > r.t && b.top < r.b) sel.add(D.items[+el.dataset.i].key);
    });
    D.sel = sel; refreshSel();
  });
  window.addEventListener('mouseup', () => { if (lasso) { $('#lasso').hidden = true; lasso = null; } });
  icons.addEventListener('click', (ev) => {  // clic simple dans une sélection multiple : ne garder que cet élément
    const el = ev.target.closest('.dicon');
    if (el && !ev.ctrlKey && !ev.shiftKey && D.sel.size > 1) selectOnly(D.items[+el.dataset.i]);
  });
  icons.addEventListener('dblclick', (ev) => {
    const el = ev.target.closest('.dicon');
    if (el) openItem(D.items[+el.dataset.i]);
  });
  desk.addEventListener('contextmenu', (ev) => {
    ev.preventDefault();
    const el = ev.target.closest('.dicon');
    if (el) {
      const it = D.items[+el.dataset.i];
      if (!D.sel.has(it.key)) selectOnly(it);
      return itemMenu(ev.clientX, ev.clientY);
    }
    D.sel.clear(); refreshSel();
    deskMenu(ev.clientX, ev.clientY);
  });
  document.addEventListener('contextmenu', (ev) => {
    if (ev.target.closest('input, textarea, .md, .msgs')) return;
    if (!ev.defaultPrevented) ev.preventDefault();
  });

  // clavier
  document.addEventListener('keydown', (ev) => {
    if (IS_WRITING() || $('.overlay') || $('.menu')) return;
    const its = selItems();
    const one = its.length === 1 ? its[0] : null;
    const k = ev.key;
    if (k === 'Enter' && its.length) { ev.preventDefault(); its.slice(0, 8).forEach(openItem); return; }
    if (k === 'F2' && one?.type === 'entry') { ev.preventDefault(); renameEntry(one.e); return; }
    if (k === 'Delete' && selEntries().length) { ev.preventDefault(); trashPaths(selEntries().map((x) => x.path)); return; }
    if (k === 'Escape') { D.sel.clear(); refreshSel(); return; }
    if (ev.ctrlKey && (k === 'a' || k === 'A')) { ev.preventDefault(); D.sel = new Set(D.items.map((x) => x.key)); refreshSel(); return; }
    if (k.startsWith('Arrow')) {
      ev.preventDefault();
      const rows = Math.max(1, Math.floor(($('#icons').clientHeight + 4) / 118));
      const cur = D.anchor ?? -1;
      const step = { ArrowDown: 1, ArrowUp: -1, ArrowRight: rows, ArrowLeft: -rows }[k];
      const i = Math.max(0, Math.min(D.items.length - 1, cur < 0 ? 0 : cur + step));
      selectOnly(D.items[i]);
      $(`#icons .dicon[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      return;
    }
    if (k.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {  // taper n'importe où : on écrit à l'Archiviste
      ev.preventDefault();
      if (!D.b.volet) setVolet(true);
      const inp = $('#vIn');
      inp.focus(); inp.value += k; inp.dispatchEvent(new Event('input'));
    }
  });

  // trop d'icônes pour la place à gauche du volet : la molette fait défiler la grille
  icons.addEventListener('wheel', (ev) => {
    if (ev.ctrlKey || icons.scrollWidth <= icons.clientWidth) return;
    ev.preventDefault();
    icons.scrollLeft += Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY;
  }, { passive: false });
  icons.addEventListener('scroll', iconFades, { passive: true });
  window.addEventListener('resize', iconFades);
  const page = (dir) => icons.scrollBy({ left: dir * Math.max(122, Math.floor((icons.clientWidth - 40) / 122) * 122), behavior: 'smooth' });
  $('#icPrev').addEventListener('click', () => page(-1));
  $('#icNext').addEventListener('click', () => page(1));

  // glisser-déposer
  icons.addEventListener('dragstart', (ev) => {
    const el = ev.target.closest('.dicon');
    if (!el) return;
    const it = D.items[+el.dataset.i];
    if (!D.sel.has(it.key)) selectOnly(it);
    const paths = selItems().filter((x) => x.type === 'entry' || x.type === 'home').map((x) => x.path);
    if (!paths.length) return ev.preventDefault();
    DRAG_PATHS = paths;
    try { ev.dataTransfer.setData('application/x-archiviste-paths', JSON.stringify(paths)); } catch { /* */ }
    ev.dataTransfer.setData('text/uri-list', paths.map(fileUri).join('\r\n'));
    ev.dataTransfer.setData('text/plain', paths.join('\n'));
    ev.dataTransfer.effectAllowed = 'copyMove';
  });
  icons.addEventListener('dragend', () => { setTimeout(() => { DRAG_PATHS = null; }, 300); });
  const target = (ev) => {
    const el = ev.target.closest('.dicon');
    if (!el) return { el: null, dir: D.b.dossier };
    const it = D.items[+el.dataset.i];
    if (it.type === 'trash') return { el, trash: true };
    if (it.type === 'home') return { el, dir: it.path };
    if (it.type === 'entry' && it.e.dir && !D.sel.has(it.key)) return { el, dir: it.path };
    return { el: null, dir: D.b.dossier };
  };
  let lastOver = null;
  desk.addEventListener('dragenter', (ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = ev.ctrlKey ? 'copy' : 'move'; });
  desk.addEventListener('dragover', (ev) => {
    ev.preventDefault();
    const t = target(ev);
    if (lastOver !== t.el) { lastOver?.classList.remove('drop'); t.el?.classList.add('drop'); lastOver = t.el; }
    desk.classList.toggle('drop-on', !t.el && !DRAG_PATHS);
    ev.dataTransfer.dropEffect = ev.ctrlKey ? 'copy' : 'move';
  });
  desk.addEventListener('dragleave', (ev) => { if (ev.target === desk) { desk.classList.remove('drop-on'); lastOver?.classList.remove('drop'); lastOver = null; } });
  desk.addEventListener('drop', async (ev) => {
    ev.preventDefault();
    desk.classList.remove('drop-on'); lastOver?.classList.remove('drop'); lastOver = null;
    const t = target(ev);
    const dt = ev.dataTransfer;
    const paths = dropPaths(dt);
    DRAG_PATHS = null;
    if (t.trash) return paths.length && trashPaths(paths);
    if (t.dir === D.b.dossier && paths.length && paths.every((p) => dirname(p) === D.b.dossier)) return;  // déjà sur le bureau
    if (paths.length) {
      const r = await movePaths(paths, t.dir, ev.ctrlKey);
      const refused = new Set((r?.erreurs || []).map((x) => basename(x.path)));
      const files = [...dt.files].filter((f) => refused.has(f.name));
      if (files.length) { await uploadFiles(files, t.dir); loadElements(); }
      return;
    }
    if (dt.files.length) { await uploadFiles(dt.files, t.dir); loadElements(); }
  });
}
// un fichier lâché ailleurs que sur une zone prévue ne doit pas ouvrir la page du fichier
// (WebKitGTK n'accepte un dépôt que si dropEffect est précisé à chaque survol)
document.addEventListener('dragover', (ev) => { if (!ev.defaultPrevented) { ev.preventDefault(); ev.dataTransfer.dropEffect = 'none'; } });
document.addEventListener('drop', (ev) => ev.preventDefault());
function pathsFromUris(list) {
  return String(list || '').split(/\r?\n/).map((l) => l.trim()).filter((l) => l.startsWith('file://'))
    .map((u) => { try { return decodeURIComponent(new URL(u).pathname); } catch { return null; } }).filter(Boolean);
}
// Chemins glissés : format interne, liste d'URI (Nemo) ou texte brut (WebKitGTK ne garde pas toujours le format interne)
let DRAG_PATHS = null;  // glisser-déposer à l'intérieur de la page : on garde les chemins ici, sans dépendre du presse-papiers
function dropPaths(dt) {
  if (DRAG_PATHS && DRAG_PATHS.length) return DRAG_PATHS.slice();
  try { const j = dt.getData('application/x-archiviste-paths'); if (j) return JSON.parse(j); } catch { /* */ }
  let p = pathsFromUris(dt.getData('text/uri-list'));
  if (!p.length) {
    p = String(dt.getData('text/plain') || '').split(/\r?\n/).map((l) => l.trim()).filter((l) => l.startsWith('/') || l.startsWith('file://'))
      .map((l) => (l.startsWith('file://') ? pathsFromUris(l)[0] : l)).filter(Boolean);
  }
  return p;
}

// ───────────────────────── Lanceur : une seule saisie pour l'IA, les applis et les fichiers ─────────────────────────
// « ouvre Grimoire », « lance firefox », « ouvre mes téléchargements » : ouvert tout de suite, sans passer par l'IA.
// Le reste part à l'Archiviste. Utilisé par la discussion du volet et par la fenêtre « Demander » (Super + Espace).
const VERBES = ['ouvre', 'ouvrir', 'ouvres', 'lance', 'lancer', 'lances', 'demarre', 'demarrer', 'affiche', 'afficher', 'montre', 'montrer'];
const ART_RE = /^(?:l['’]\s*appli(?:cation)?|l['’]\s*app|le\s+logiciel|le\s+programme|le\s+dossier|le\s+fichier|la\s+|le\s+|les\s+|l['’]\s*|mes\s+|mon\s+|ma\s+)\s*/i;
// « ouvre Grimoire », « lance firefox », « ouvrr le terminal » (faute de frappe), « ou le Terminal » (incertain)
function parseIntent(text) {
  let t = String(text || '').trim().replace(/[?!.…]+$/, '')
    .replace(/^(?:(?:peux|pourrais)[- ]tu\s+|tu\s+peux\s+|merci\s+d['’]\s*|stp\s+|svp\s+)/i, '');
  let weak = false;
  const dans = t.match(/^(?:va|aller)\s+dans\s+(.+)$/i);
  if (dans) t = dans[1];
  else {
    const m = t.match(/^(\S+?)(?:-moi)?\s+(?:moi\s+)?(.+)$/i);
    if (!m) return null;
    const v = norm(m[1]).replace(/[^a-z]/g, '');
    if (!VERBES.includes(v)) {
      if (v === 'ou' || v === 'ouv') weak = true;
      else if (!(v.length >= 4 && VERBES.some((x) => osa(v, x) <= 1))) return null;
    }
    t = m[2];
  }
  for (let i = 0; i < 3; i++) t = t.replace(ART_RE, '').trim();
  return t ? { target: t, weak } : null;
}
// ── orthographe approchée : « terminale », « grimio », « firefoks », « libre office » ──
function osa(a, b) {
  if (a === b) return 0;
  let prev2 = null;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) cur[j] = Math.min(cur[j], prev2[j - 2] + 1);
    }
    prev2 = prev; prev = cur;
  }
  return prev[b.length];
}
const tolerance = (n) => (n <= 2 ? 0 : n <= 5 ? 1 : n <= 9 ? 2 : 3);
const compact = (t) => norm(t).replace(/[^a-z0-9]/g, '');
function fuzzyWord(w, tokens, strict = false) {
  const tol = tolerance(w.length) - (strict ? 1 : 0);
  let best = null;
  for (const t of tokens) {
    if (t.length < 2) continue;
    let d = osa(w, t);
    if (t.length > w.length && w.length >= 3) d = Math.min(d, osa(w, t.slice(0, w.length)) + (t.startsWith(w.slice(0, 2)) ? 0 : 1));
    if (d <= tol && (best === null || d < best)) best = d;
  }
  return best;
}
const SYNONYMES = { navigateur: 'WebBrowser', internet: 'WebBrowser', web: 'WebBrowser', terminal: 'TerminalEmulator',
  console: 'TerminalEmulator', fichiers: 'FileManager', explorateur: 'FileManager', mail: 'Email', courriel: 'Email', messagerie: 'Email' };
function appTokens(a) {
  if (!a._tok) {
    const split = (t) => norm(t).split(/[\s\-_.]+/).map((w) => w.replace(/[^a-z0-9]/g, '')).filter(Boolean);
    a._tok = {
      main: new Set([...split(a.nom), compact(a.id.replace(/\.desktop$/, '').split('.').pop()), compact(a.cmd || '')].filter(Boolean)),
      extra: new Set([...split(a.generique), ...a.mots.map(compact)].filter(Boolean)),
    };
  }
  return a._tok;
}
function scoreApp(a, n) {
  const name = norm(a.nom);
  const stem = norm(a.id.replace(/\.desktop$/, '').split('.').pop());
  const nc = n.replace(/[^a-z0-9]/g, '');
  if (name === n || stem === n || norm(a.cmd) === n || [compact(a.nom), compact(stem), compact(a.cmd || '')].includes(nc)) return 0;
  if (name.startsWith(n) || stem.startsWith(n) || compact(a.nom).startsWith(nc)) return 1;
  if (name.split(/\s+/).some((w) => w.startsWith(n))) return 2;
  if (name.includes(n)) return 3;
  if (norm(a.generique).includes(n) || a.mots.some((m) => norm(m).startsWith(n)) || norm(a.id).includes(n)) return 4;
  const words = n.split(/\s+/).map((w) => w.replace(/[^a-z0-9]/g, '')).filter(Boolean);
  if (!words.length) return -1;
  const { main, extra } = appTokens(a);
  let ds = words.map((w) => fuzzyWord(w, main));
  if (ds.every((d) => d !== null)) return 6 + ds.reduce((x, y) => x + y, 0);
  ds = words.map((w) => fuzzyWord(w, main) ?? fuzzyWord(w, extra, true));
  if (ds.every((d) => d !== null)) return 7.5 + ds.reduce((x, y) => x + y, 0);
  if (nc.length >= 4 && osa(nc, compact(a.nom)) <= tolerance(nc.length)) return 6 + osa(nc, compact(a.nom));
  return -1;
}
function matchApps(q) {
  const n = norm(q).replace(/^(l['’]\s*appli(cation)?|l['’]\s*app|le\s+logiciel|le\s+programme|(la|le|les|mon|ma|mes)\s+|l['’]\s*)/, '').trim();
  if (!D.apps || n.length < 2) return [];
  let res = D.apps.map((a) => [scoreApp(a, n), a]).filter((x) => x[0] >= 0);
  if (!res.length && SYNONYMES[n]) res = D.apps.filter((a) => a.categories.includes(SYNONYMES[n])).map((a) => [9, a]);
  return res.sort((x, y) => x[0] - y[0] || x[1].nom.localeCompare(y[1].nom)).slice(0, 5).map(([s, a]) => ({ s, a }));
}
// Dossiers spéciaux : « ouvre téléchargements » ouvre le dossier, pas l'appli Transmission (« client de téléchargement »)
function specialDirs(q) {
  const n = norm(q).replace(/^(?:dossiers?|repertoires?)\s+(?:des?\s+|du\s+)?/, '').replace(/^(?:mes|mon|ma|les|le|la)\s+/, '').trim();
  const nc = n.replace(/[^a-z0-9]/g, '');
  if (!D.b || nc.length < 3) return [];
  const list = [
    [['bureau', 'desktop'], D.b.dossier, 'Bureau'],
    [['telechargements', 'telechargement', 'downloads'], D.b.telechargements, 'Téléchargements'],
    [['documents', 'document', 'docs'], D.b.documents, 'Documents'],
    [['images', 'image', 'photos', 'pictures'], D.b.images, 'Images'],
    [['musique', 'musiques', 'music'], D.b.musique, 'Musique'],
    [['videos', 'video', 'films'], D.b.videos, 'Vidéos'],
    [['dossierpersonnel', 'maison', 'home', 'perso'], D.b.home, 'Dossier personnel'],
    [['corbeille', 'poubelle'], '#corbeille', 'Corbeille'],
  ];
  return list.filter(([keys, path]) => path && keys.some((k) => k === nc || k.startsWith(nc) || (nc.length >= 4 && osa(nc, k) <= tolerance(k.length))))
    .map(([, path, name]) => ({ name, path, dir: true, kind: 'folder', ext: '', special: true }));
}
function makeLauncher({ input, box, onAsk, always = false }) {
  const L = { q: '', target: '', intent: null, weak: false, items: [], idx: 0, seq: 0, files: null, loading: false, cut: false };
  const visible = () => !box.hidden;
  const hide = () => { box.hidden = true; box.innerHTML = ''; L.items = []; reportSize(); };
  const search = debounce(async (q, seq) => {
    try {
      const r = await api(`/api/fs/search?rapide=1&path=${enc(S.home)}&q=${enc(q)}`);
      if (seq !== L.seq) return;
      L.files = r.results.slice(0, 7);
      L.cut = r.incomplet === 'temps';
    } catch { if (seq === L.seq) L.files = []; }
    L.loading = false;
    build();
  }, 220);
  function update() {
    const text = input.value.trim();
    L.q = text; L.seq++; L.idx = 0; L.files = null; L.loading = false; L.cut = false;
    if (text.length < 2 || text.length > 90 || text.includes('\n')) return hide();
    const pi = parseIntent(text);
    L.intent = pi ? pi.target : null;
    L.weak = pi ? pi.weak : false;
    L.target = L.intent || text;
    const words = L.target.split(/\s+/).length;
    if (D.apps === null) loadApps().then(build);
    if ((L.intent || (always ? words <= 4 : words <= 2)) && L.target.length >= 2) { L.loading = true; search(L.target, L.seq); }
    return build();
  }
  function build() {
    if (!L.q) return hide();
    const apps = matchApps(L.target);
    const dirs = specialDirs(L.target);
    const folderHint = /\b(dossiers?|r[ée]pertoires?)\b/i.test(L.q);
    let found = (L.files || []).filter((f) => !dirs.some((d) => d.path === f.path)).slice(0, 7);
    if (folderHint) found = [...found.filter((f) => f.dir), ...found.filter((f) => !f.dir)];
    const appActs = folderHint ? [] : apps.map(({ a }) => ({ kind: 'app', a }));
    const dirActs = dirs.map((e) => ({ kind: 'file', e }));
    const fileActs = found.map((e) => ({ kind: 'file', e }));
    // un dossier connu passe avant une appli qui lui ressemble seulement (Transmission, « Numériseur de documents »…)
    const dirFirst = dirActs.length && (folderHint || !apps.length || apps[0].s >= 2);
    const acts = dirFirst ? [...dirActs, ...appActs, ...fileActs] : [...appActs, ...dirActs, ...fileActs];
    const ask = { kind: 'ask' };
    const oneApp = apps.length && apps[0].s <= 1 && L.target.split(/\s+/).length <= 2;
    const strong = L.intent ? (L.weak ? (dirFirst || (apps.length > 0 && apps[0].s <= 7)) : acts.length > 0) : oneApp;
    L.items = strong ? [acts[0], ask, ...acts.slice(1)] : [ask, ...acts];
    L.idx = Math.min(L.idx, L.items.length - 1);
    if (!always && !acts.length && !(L.intent && L.loading) && !(L.intent && L.cut)) return hide();
    let html = '';
    let section = '';
    L.items.forEach((it, i) => {
      const sec = it.kind === 'app' ? 'Applications' : it.kind === 'file' ? 'Fichiers et dossiers' : '';
      if (sec && sec !== section && !(i === 0 && strong)) { html += `<div class="rh">${sec}</div>`; section = sec; }
      let ico; let t; let sub; let k = '';
      if (it.kind === 'ask') {
        ico = '<img src="/favicon.svg" alt="" width="26" height="26">';
        t = 'Demander à l\'Archiviste'; sub = `« ${L.q} »`;
      } else if (it.kind === 'app') {
        ico = `<img class="app-ic" src="${appIconUrl(it.a.icone, 32)}" alt="">`;
        t = it.a.nom; sub = (i === 0 && strong ? 'Ouvrir l\'application · ' : '') + (it.a.generique || it.a.description || 'Application');
      } else {
        ico = it.e.dir ? `<span style="color:#e09a68">${ic(it.e.path === '#corbeille' ? 'trash' : it.e.path === D.b?.home ? 'home' : 'folder')}</span>` : `<span style="color:${KIND_COLOR[it.e.kind] || '#c9b8a3'}">${ic(KIND_ICON[it.e.kind] || 'file')}</span>`;
        t = it.e.name; sub = (i === 0 && strong ? 'Ouvrir · ' : '') + (it.e.special ? 'Dossier' : tildify(dirname(it.e.path)));
      }
      if (i === 0) k = 'Entrée';
      html += `<div class="ri ${i === L.idx ? 'on' : ''}" data-r="${i}"><span class="ico">${ico}</span><span class="t"><b>${esc(t)}</b><small>${esc(sub)}</small></span>${k ? `<span class="k">${k}</span>` : ''}</div>`;
    });
    if (L.loading && L.files === null) html += '<div class="wait"><span class="spinner"></span> Recherche dans tes fichiers…</div>';
    else if (L.cut) html += `<div class="wait cut">${ic('alert', 'sm')} Recherche de fichiers incomplète : ton dossier personnel est trop volumineux pour être parcouru en entier d'ici. Cherche depuis l'onglet Fichiers d'Archiviste.</div>`;
    box.innerHTML = html;
    box.hidden = false;
    reportSize();
    return null;
  }
  function move(d) {
    if (!L.items.length) return;
    L.idx = (L.idx + d + L.items.length) % L.items.length;
    $$('.ri', box).forEach((el) => el.classList.toggle('on', +el.dataset.r === L.idx));
    $(`.ri[data-r="${L.idx}"]`, box)?.scrollIntoView({ block: 'nearest' });
  }
  function run(it) {
    const text = input.value.trim();
    L.q = ''; L.seq++;  // ignore les recherches encore en route
    hide();
    if (!it || it.kind === 'ask') return onAsk(text);
    input.value = ''; input.dispatchEvent(new Event('input'));
    if (it.kind === 'app') return launchApp(it.a.id, it.a.nom);
    if (it.e.path === '#corbeille') return openMain({ vue: 'trash' });
    return openFile(it.e);
  }
  function menu(it, x, y) {
    if (it.kind === 'app') {
      return showMenu(x, y, [
        { header: it.a.nom },
        { label: 'Lancer', icon: 'play', act: () => run(it) },
        { label: 'Épingler aux raccourcis', icon: 'star', act: () => pinShortcut('app', it.a.id).then(loadShortcuts) },
      ]);
    }
    if (it.kind === 'file' && !it.e.path.startsWith('#')) {
      return showMenu(x, y, [
        { header: it.e.name },
        { label: 'Ouvrir', icon: 'external', act: () => run(it) },
        { label: 'Afficher dans Archiviste', icon: 'folder', act: () => openMain(it.e.dir ? { vue: 'files', chemin: it.e.path } : { vue: 'files', chemin: dirname(it.e.path), select: it.e.path }) },
        { label: 'Épingler aux raccourcis', icon: 'star', act: () => pinEntry(it.e) },
        { label: 'En discuter', icon: 'chat', act: () => attachToChat([it.e.path]) },
      ]);
    }
    return null;
  }
  input.addEventListener('input', update);
  input.addEventListener('keydown', (ev) => {
    if (visible() && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) { ev.preventDefault(); move(ev.key === 'ArrowDown' ? 1 : -1); return; }
    if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) {
      ev.preventDefault();
      if (visible() && L.items.length) run(L.items[L.idx]);
      else onAsk(input.value.trim());
      return;
    }
    if (ev.key === 'Escape') {
      if (visible()) { ev.preventDefault(); ev.stopPropagation(); hide(); } else if (MODE === 'demander') { ev.preventDefault(); if (input.value) input.value = ''; else closePopup(); }
    }
  });
  input.addEventListener('blur', () => setTimeout(() => { if (!box.contains(document.activeElement) && !$('.menu')) hide(); }, 150));
  box.addEventListener('mousedown', (ev) => ev.preventDefault());  // garde le focus dans la saisie
  box.addEventListener('mousemove', (ev) => {
    const r = ev.target.closest('.ri');
    if (r && +r.dataset.r !== L.idx) { L.idx = +r.dataset.r; $$('.ri', box).forEach((el) => el.classList.toggle('on', el === r)); }
  });
  box.addEventListener('click', (ev) => { const r = ev.target.closest('.ri'); if (r) run(L.items[+r.dataset.r]); });
  box.addEventListener('contextmenu', (ev) => {
    ev.preventDefault();
    const r = ev.target.closest('.ri');
    if (r) menu(L.items[+r.dataset.r], ev.clientX, ev.clientY);
  });
  return { hide, update };
}
async function loadApps() {
  try { const r = await api('/api/apps'); D.apps = r.apps; D.favs = r.favoris; } catch { D.apps = []; }
}

// ───────────────────────── Volet ─────────────────────────
function buildVolet() {
  const v = $('#volet');
  // Deux colonnes : la discussion prend toute la hauteur, les raccourcis sont en colonne à droite.
  v.innerHTML = `<div class="vgrip" id="vGrip" title="Glisse pour élargir ou rétrécir le volet — double-clic : largeur d'origine"></div><div class="vmain">
    <div class="hd"><img src="/static/logo-seal.svg" alt="Anamnesis · CSC" width="42" height="42">
      <div style="min-width:0"><b class="serif">Archiviste</b><small id="vStatus"><span class="dot"></span><span>…</span></small></div>
      <div class="acts"><button class="vbtn maj" data-v="maj" id="vMaj" hidden title="Mise à jour">${ic('download')}</button><button class="vbtn" data-v="main" title="Ouvrir Archiviste">${ic('external')}</button><button class="vbtn" data-v="fold" title="Replier le volet">${ic('panel')}</button></div></div>
    <div id="todo" hidden></div>
    <section class="conv" id="conv"><h3>${ic('chat')}Discussion<span class="r"><select id="vAgent" title="Agent"></select>
      <button class="lnk" data-v="newConv" title="Nouvelle discussion">${ic('plus')}</button><button class="lnk" data-v="convMain" title="Continuer dans Archiviste">${ic('external')}</button></span></h3>
      <div class="msgs" id="vMsgs"></div>
      <div class="vcomp"><div class="results glass lsugg" id="vSugg" hidden></div><div class="atts" id="vAtts"></div><div class="row1">
        <button class="clip" data-v="attach" title="Joindre des fichiers">${ic('clip')}</button>
        <textarea id="vIn" rows="1" placeholder="Écris à l'Archiviste, ou « ouvre Grimoire »…"></textarea>
        <button class="send" id="vSend" data-v="send" title="Envoyer">${ic('send')}</button></div></div>
    </section></div>
    <nav class="rail" id="rail" aria-label="Raccourcis">
      <div class="sc" id="sc"></div>
      <div class="rfoot"><button class="vbtn" data-v="addSc" title="Épingler une appli, un dossier ou un fichier">${ic('plus')}</button><button class="vbtn" data-v="editSc" id="vEditSc" title="Modifier les raccourcis (retirer, réordonner)">${ic('pencil')}</button></div>
    </nav>`;
  v.addEventListener('click', onVoletClick);
  v.addEventListener('contextmenu', onVoletContext);
  const inp = $('#vIn');
  inp.addEventListener('input', () => { inp.style.height = 'auto'; inp.style.height = Math.min(inp.scrollHeight, 160) + 'px'; });
  // On s'apprête à écrire après une longue pause : la nouvelle discussion s'ouvre maintenant, avant l'envoi,
  // avec « Reprendre la discussion précédente » sous la main. Relire ou copier une réponse ne change rien.
  inp.addEventListener('focus', () => { if (!D.busy && convStale()) syncConv(true, true); });
  makeLauncher({ input: inp, box: $('#vSugg'), onAsk: () => sendFromComposer() });
  $('#vAgent').addEventListener('change', (ev) => changeAgent(ev.target.value || null));
  $('#voletTab').addEventListener('click', () => setVolet(true));
  bindShortcutDnD();
  bindVoletResize();
  const conv = $('#conv');
  const convOver = (ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = 'copy'; conv.classList.add('drop-on'); };
  conv.addEventListener('dragenter', convOver);
  conv.addEventListener('dragover', convOver);
  conv.addEventListener('dragleave', (ev) => { if (!conv.contains(ev.relatedTarget)) conv.classList.remove('drop-on'); });
  conv.addEventListener('drop', (ev) => {
    ev.preventDefault(); conv.classList.remove('drop-on');
    const paths = dropPaths(ev.dataTransfer);
    DRAG_PATHS = null;
    if (paths.length) attachToChat(paths);
  });
}
function applyVolet() {
  if (MODE !== 'bureau' || !D.b) return;
  const open = D.b.volet !== false;
  $('#volet').hidden = !open;
  $('#voletTab').hidden = open;
  document.body.classList.toggle('volet-ferme', !open);
  applyVoletWidth();
  if (open) scFades(); // replié, la colonne n'avait pas de hauteur : le fondu est recalculé à l'ouverture
  iconFades();
}
// Largeur du volet : réglable à la souris (poignée sur son bord gauche), gardée d'une session à l'autre.
const VOLET_MIN = 440;
const VOLET_MAX = 900;
const voletWidth = (w) => Math.round(Math.max(VOLET_MIN, Math.min(w, VOLET_MAX, innerWidth * 0.6)));
function applyVoletWidth(w = D.b?.volet_largeur) {
  const r = document.documentElement.style;
  if (w) { const px = voletWidth(w); r.setProperty('--sidew', `${px}px`); r.setProperty('--vw', `${px + 24}px`); }
  else { r.removeProperty('--sidew'); r.removeProperty('--vw'); }
}
function bindVoletResize() {
  const grip = $('#vGrip');
  let drag = null;
  grip.addEventListener('mousedown', (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault(); ev.stopPropagation();
    drag = { x: ev.clientX, w: $('#volet').getBoundingClientRect().width, now: 0 };
    D.resizing = true;
    document.body.classList.add('volet-resize');
  });
  window.addEventListener('mousemove', (ev) => {
    if (!drag) return;
    drag.now = voletWidth(drag.w + (drag.x - ev.clientX));
    applyVoletWidth(drag.now);
    scFades(); iconFades();
  });
  window.addEventListener('mouseup', () => {
    if (!drag) return;
    const w = drag.now;
    drag = null; D.resizing = false;
    document.body.classList.remove('volet-resize');
    if (w) { D.b.volet_largeur = w; post('/api/bureau/reglages', { volet_largeur: w }).catch(() => {}); }
    scrollMsgs();
  });
  grip.addEventListener('dblclick', () => {
    D.b.volet_largeur = null;
    applyVoletWidth(null); scFades(); iconFades();
    post('/api/bureau/reglages', { volet_largeur: 0 }).catch(() => {});
  });
  window.addEventListener('resize', () => { if (!D.resizing) applyVoletWidth(); });
}
function setVolet(open) {
  D.b.volet = open;
  applyVolet();
  post('/api/bureau/reglages', { volet: open }).catch(() => {});
}
async function onVoletClick(ev) {
  const b = ev.target.closest('[data-v], [data-act], [data-sc], [data-run], [data-todo], [data-chip]');
  if (!b) return;
  if (b.dataset.sc !== undefined) {
    if (ev.target.closest('.x')) return removeShortcut(b.dataset.sc);
    if (D.editSc) return;
    return runShortcut(D.sc.find((s) => s.id === b.dataset.sc));
  }
  if (b.dataset.run !== undefined) return toggleWindows(b.dataset.run);
  if (b.dataset.todo !== undefined) return openMain({ vue: 'sort', chemin: b.dataset.todo });
  if (b.dataset.chip !== undefined) return CHIPS[+b.dataset.chip].run();
  if (b.dataset.act) return chatAct(b, ev);
  switch (b.dataset.v) {
    case 'main': return openMain({});
    case 'maj': return UPD.info?.relancer && !UPD.info?.disponible ? relaunchApp() : showUpdateModal();
    case 'fold': return setVolet(false);
    case 'editSc':
      D.editSc = !D.editSc;
      b.innerHTML = ic(D.editSc ? 'check' : 'pencil');
      b.title = D.editSc ? 'Terminé' : 'Modifier les raccourcis (retirer, réordonner)';
      b.classList.toggle('on', D.editSc);
      return renderShortcuts();
    case 'addSc': return addShortcutMenu(b);
    case 'newConv': return newConv();
    case 'resume': return resumeConv();
    case 'convMain': return D.conv && openMain({ vue: 'chat', conv: D.conv.id });
    case 'attach': {
      const paths = await pickPath({ title: 'Joindre à la discussion', mode: 'files', start: D.b.dossier });
      if (paths) attachToChat(paths);
      return null;
    }
    case 'send': return D.busy ? D.ctrl?.abort() : sendFromComposer();
    case 'rmAtt': D.atts.splice(+b.dataset.i, 1); return renderVAtts();
    default: return null;
  }
}
function onVoletContext(ev) {
  const t = ev.target.closest('[data-sc]');
  if (t) { ev.preventDefault(); return shortcutMenu(D.sc.find((s) => s.id === t.dataset.sc), ev.clientX, ev.clientY); }
  const o = ev.target.closest('[data-run]');
  if (o) { ev.preventDefault(); return openAppMenu(D.win.map[o.dataset.run], ev.clientX, ev.clientY); }
  if (!ev.target.closest('textarea, input, .msgs')) ev.preventDefault();
  return null;
}

// ── statut ──
const DF_BUREAU = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'short' });
async function refreshVStatus() {
  try { S.status = await api('/api/status'); } catch (e) { S.status = { ok: false, error: e.message, models: [] }; }
  const st = S.status;
  const el = $('#vStatus');
  if (!el) return;
  const [cls, txt] = st.ok && st.model_present ? ['ok', `${st.model} prêt`] : st.ok ? ['warn', `${st.model} absent`] : ['bad', 'Ollama hors ligne'];
  el.innerHTML = `<span class="dot ${cls}"></span><span class="ellipsis">${esc(txt)} · ${esc(DF_BUREAU.format(new Date()))}</span>`;
  el.title = st.ok ? `Ollama ${st.version || ''}` : (st.error || 'Lance Ollama : systemctl start ollama');
}

// ── mise à jour disponible (même logique que la fenêtre principale) ──
async function refreshVMaj() {
  const i = await refreshUpdate();
  const b = $('#vMaj');
  if (!b || !i) return;
  b.hidden = !(i.disponible || i.relancer);
  b.title = i.relancer ? `Archiviste ${i.installee} est installé : clique pour relancer` : i.disponible ? `Archiviste ${i.derniere.version} est disponible : clique pour l'installer` : '';
}

// ── raccourcis ──
async function loadShortcuts() {
  let sc;
  try { sc = await api('/api/raccourcis'); } catch { if (D.sc.length) return; sc = []; }
  // rien n'a changé : on ne redessine pas (un glisser ou le mode « modifier » en cours ne sont pas interrompus)
  if ($('#sc')?.children.length && JSON.stringify(sc) === JSON.stringify(D.sc)) return;
  D.sc = sc;
  renderShortcuts();
}
function scIcon(s) {
  if (s.type === 'archiviste') return '<span class="ico app"><img src="/favicon.svg" alt=""></span>';
  if (s.type === 'app') return `<span class="ico app"><img class="app-ic" src="${appIconUrl(s.icone || 'application-x-executable', 48)}" alt="" draggable="false"></span>`;
  if (s.type === 'dossier') return `<span class="ico">${ic(s.cible === D.b?.home ? 'home' : 'folder')}</span>`;
  return `<span class="ico" style="color:${KIND_COLOR[s.kind] || '#f0b98f'}">${ic(KIND_ICON[s.kind] || 'file')}</span>`;
}
// ── fenêtres ouvertes : le volet sert de dock ──
// Un repère sur le raccourci dit que l'appli est ouverte (trait plein), devant (trait long) ou réduite (trait creux).
// Un clic la ramène devant, ou la réduit si elle y est déjà. Les applis ouvertes sans raccourci apparaissent
// à la suite, le temps qu'elles restent ouvertes : une fenêtre réduite ne « disparaît » plus.
const winKey = (s) => (s.type === 'archiviste' ? 'archiviste' : s.type === 'app' ? `app:${s.cible}` : null);
const winOf = (s) => { const k = winKey(s); return k ? D.win.map[k] : null; };
function winClass(g) { return g && g.n ? `run${g.devant ? ' front' : ''}${g.reduit ? ' mini' : ''}` : ''; }
function winHint(g) {
  if (!g || !g.n) return '';
  const what = g.n > 1 ? `${g.n} fenêtres ouvertes` : g.reduit ? 'Ouverte, réduite' : 'Ouverte';
  return `\n${what} — clic : ${g.devant && !g.reduit ? 'réduire' : 'ramener devant'}`;
}
function winMarks(g) { return g && g.n ? `<i class="run-dot"></i>${g.n > 1 ? `<span class="nb">${g.n}</span>` : ''}` : ''; }
async function loadWindows() {
  if (MODE !== 'bureau') return;
  let r;
  try { r = await api('/api/fenetres'); } catch { return; }
  if (r.sig === D.win.sig && r.dispo === D.win.dispo) return;
  D.win = { ...r, map: Object.fromEntries(r.groupes.map((g) => [g.cle, g])) };
  if (D.scDrag) { D.winDirty = true; return; }  // pas de nouveau dessin au milieu d'un glisser
  renderShortcuts();
}
window.archivisteFenetres = debounce(loadWindows, 60);  // appelé par la fenêtre GTK dès qu'une fenêtre change
async function toggleWindows(cle, fallback, action = 'basculer') {
  let r;
  try { r = await post('/api/fenetres/action', { cle, action }); } catch (e) { return toast(e.message, 'err'); }
  if (!r.ouverte && fallback) return fallback();  // fermée entre-temps : on la lance
  setTimeout(loadWindows, 350);
  return null;
}
function winMenuItems(g) {
  if (!g || !g.n) return [];
  const front = g.devant && !g.reduit;
  return [
    { label: front ? 'Réduire' : 'Ramener devant', icon: front ? 'down' : 'up', act: () => toggleWindows(g.cle, null, front ? 'reduire' : 'afficher') },
    { label: g.n > 1 ? `Fermer les ${g.n} fenêtres` : 'Fermer la fenêtre', icon: 'x', act: () => toggleWindows(g.cle, null, 'fermer') },
  ];
}
function openAppMenu(g, x, y) {
  if (!g) return;
  const m = [{ header: g.nom }, ...winMenuItems(g)];
  if (g.app && !g.app.startsWith('/')) m.push('sep', { label: 'Épingler aux raccourcis', icon: 'star', act: () => pinShortcut('app', g.app).then(loadShortcuts) });
  showMenu(x, y, m);
}
function renderShortcuts() {
  const el = $('#sc');
  if (!el) return;
  el.classList.toggle('edit', D.editSc);
  const pinned = new Set(D.sc.map(winKey).filter(Boolean));
  const others = D.win.groupes.filter((g) => !pinned.has(g.cle));
  el.innerHTML = (D.sc.map((s) => {
    const g = winOf(s);
    return `<button class="t ${s.ok ? '' : 'ko'} ${winClass(g)}" data-sc="${esc(s.id)}" draggable="true" title="${esc(s.titre)}${s.description ? '\n' + esc(s.description) : ''}${esc(winHint(g))}">
    ${scIcon(s)}<span class="lbl">${esc(s.titre)}</span>${winMarks(g)}${D.editSc ? '<span class="x" title="Retirer">×</span>' : ''}</button>`;
  }).join('')
    || `<button class="t add" data-v="addSc" title="Épingler une appli, un dossier ou un fichier"><span class="ico">${ic('plus')}</span><span class="lbl">Ajouter</span></button>`)
    + (others.length ? `<div class="sep" title="Applis ouvertes sans raccourci"></div>${others.map((g) => `<button class="t open ${winClass(g)}" data-run="${esc(g.cle)}" title="${esc(g.titres[0] || g.nom)}${esc(winHint(g))}\nClic droit : épingler, fermer">
    <span class="ico app"><img class="app-ic" src="${appIconUrl(g.icone || 'application-x-executable', 48)}" alt="" draggable="false"></span><span class="lbl">${esc(g.nom)}</span>${winMarks(g)}</button>`).join('')}` : '');
  scFades();
}
// Colonne des raccourcis : un fondu en haut / en bas signale qu'il y en a d'autres en faisant défiler.
function scFades() {
  const el = $('#sc');
  if (!el) return;
  el.classList.toggle('fade-t', el.scrollTop > 2);
  el.classList.toggle('fade-b', el.scrollTop + el.clientHeight < el.scrollHeight - 2);
}
function runShortcut(s, fresh = false) {
  if (!s) return null;
  if (!s.ok) return toast(`Introuvable : ${s.cible || s.titre}. Clic droit › Retirer des raccourcis.`, 'err');
  // déjà ouverte : le clic ramène sa fenêtre devant, ou la réduit si elle y est déjà (« Nouvelle fenêtre » au clic droit)
  if (!fresh && winOf(s)?.n) return toggleWindows(winKey(s), () => runShortcut(s, true));
  if (s.type === 'archiviste') return openMain({});
  if (s.type === 'app') return s.cible.startsWith('/') ? launchLauncher(s.cible) : launchApp(s.cible, s.titre, undefined, true);
  if (s.type === 'dossier') return openFolder(s.cible);
  return openFile({ path: s.cible, name: basename(s.cible), dir: false, ext: s.ext || '', kind: s.kind });
}
async function removeShortcut(id) {
  try { D.sc = await post('/api/raccourcis/retirer', { id }); renderShortcuts(); } catch (e) { toast(e.message, 'err'); }
}
async function reorderShortcuts(ids) {
  try { D.sc = await post('/api/raccourcis/ordre', { ids }); renderShortcuts(); } catch (e) { toast(e.message, 'err'); }
}
function shortcutMenu(s, x, y) {
  if (!s) return;
  const i = D.sc.indexOf(s);
  const ids = D.sc.map((z) => z.id);
  const swap = (j) => { const c = ids.slice(); [c[i], c[j]] = [c[j], c[i]]; reorderShortcuts(c); };
  const g = winOf(s);
  const m = [{ header: s.titre }, ...winMenuItems(g),
    { label: g?.n ? 'Nouvelle fenêtre' : s.type === 'app' ? 'Lancer' : 'Ouvrir', icon: s.type === 'app' ? 'play' : 'external', act: () => runShortcut(s, true) }];
  if (s.type === 'dossier' || s.type === 'fichier') {
    m.push({ label: 'Afficher dans Archiviste', icon: 'folder', act: () => openMain(s.type === 'dossier' ? { vue: 'files', chemin: s.cible } : { vue: 'files', chemin: dirname(s.cible), select: s.cible }) });
    if (s.type === 'fichier') m.push({ label: 'En discuter', icon: 'chat', act: () => attachToChat([s.cible]) });
  }
  m.push('sep');
  m.push({ label: 'Renommer le raccourci…', icon: 'pencil', act: async () => {
    const nom = await promptText({ title: 'Renommer le raccourci', label: 'Laisse vide pour reprendre le nom d\'origine', value: s.nom || s.titre, ok: 'Renommer' });
    if (nom === null) return;
    try { D.sc = await post('/api/raccourcis/renommer', { id: s.id, nom }); renderShortcuts(); } catch (e) { toast(e.message, 'err'); }
  } });
  if (i > 0) m.push({ label: 'Monter', icon: 'up', act: () => swap(i - 1) });
  if (i < D.sc.length - 1) m.push({ label: 'Descendre', icon: 'down', act: () => swap(i + 1) });
  m.push('sep');
  m.push({ label: 'Retirer des raccourcis', icon: 'x', danger: true, act: () => removeShortcut(s.id) });
  showMenu(x, y, m);
}
function addShortcutMenu(btn) {
  const m = [
    { label: 'Une application…', icon: 'app', act: pickAppDialog },
    { label: 'Un dossier…', icon: 'folder', act: async () => { const d = await pickPath({ title: 'Épingler un dossier', mode: 'dir', start: S.home }); if (d) { await pinShortcut('dossier', d); loadShortcuts(); } } },
    { label: 'Un fichier…', icon: 'file', act: async () => { const f = await pickPath({ title: 'Épingler des fichiers', mode: 'files', start: D.b.dossier }); if (f) { for (const p of f.slice(0, 8)) await pinShortcut('fichier', p); loadShortcuts(); } } },
  ];
  if (!D.sc.some((s) => s.type === 'archiviste')) m.push({ label: 'Archiviste', icon: 'star', act: () => pinShortcut('archiviste', '').then(loadShortcuts) });
  m.push('sep', { label: 'Astuce : clic droit sur une appli, un dossier ou un fichier › Épingler aux raccourcis', icon: 'info', disabled: true });
  menuAt(btn, m);
}
async function pickAppDialog() {
  if (D.apps === null) await loadApps();
  const m = openModal({
    title: 'Épingler une application', cls: 'wide',
    body: '<input type="search" data-q placeholder="Chercher une application…" autofocus><div class="app-list" data-l></div><p class="muted" style="font-size:12px;margin:8px 0 0">Clic : épingler · clic droit : plus d\'options</p>',
    footer: '<button class="btn" data-close>Fermer</button>',
  });
  const list = $('[data-l]', m.el);
  const qi = $('[data-q]', m.el);
  const pinned = () => new Set(D.sc.filter((s) => s.type === 'app').map((s) => s.cible));
  const row = (a, p) => `<div class="ar" data-id="${esc(a.id)}"><img class="app-ic" src="${appIconUrl(a.icone, 32)}" alt="" loading="lazy"><span class="t"><b>${esc(a.nom)}</b><small>${esc(a.generique || a.description || '')}</small></span>${p.has(a.id) ? '<span class="pin chip on">✓ épinglée</span>' : ''}</div>`;
  const draw = () => {
    const n = norm(qi.value.trim());
    const p = pinned();
    const all = D.apps.filter((a) => !n || norm(`${a.nom} ${a.generique} ${a.mots.join(' ')} ${a.id}`).includes(n));
    const favs = n ? [] : D.favs.map((id) => D.apps.find((a) => a.id === id)).filter(Boolean);
    list.innerHTML = (favs.length ? `<div class="rh">Favoris du menu</div>${favs.map((a) => row(a, p)).join('')}<div class="rh">Toutes les applications</div>` : '')
      + (all.map((a) => row(a, p)).join('') || '<p class="muted" style="padding:10px">Aucune application ne correspond.</p>');
  };
  draw();
  qi.addEventListener('input', draw);
  const byId = (id) => D.apps.find((a) => a.id === id);
  list.addEventListener('click', async (ev) => {
    const r = ev.target.closest('.ar');
    if (!r) return;
    await pinShortcut('app', r.dataset.id);
    await loadShortcuts(); draw();
  });
  list.addEventListener('contextmenu', (ev) => {
    const r = ev.target.closest('.ar');
    if (!r) return;
    ev.preventDefault();
    const a = byId(r.dataset.id);
    showMenu(ev.clientX, ev.clientY, [
      { header: a.nom },
      { label: 'Épingler aux raccourcis', icon: 'star', act: async () => { await pinShortcut('app', a.id); await loadShortcuts(); draw(); } },
      { label: 'Lancer', icon: 'play', act: () => launchApp(a.id, a.nom) },
    ]);
  });
}
function bindShortcutDnD() {
  const sc = $('#rail'); // toute la colonne accepte le dépôt, y compris sous le dernier raccourci
  let dragId = null;
  $('#sc').addEventListener('scroll', scFades, { passive: true });
  window.addEventListener('resize', scFades);
  sc.addEventListener('dragstart', (ev) => {
    const t = ev.target.closest('[data-sc]');
    if (!t) return;
    dragId = t.dataset.sc;
    D.scDrag = true;
    ev.dataTransfer.setData('text/plain', t.querySelector('.lbl')?.textContent || 'raccourci');
    ev.dataTransfer.effectAllowed = 'move';
  });
  sc.addEventListener('dragend', () => {
    dragId = null; D.scDrag = false;
    $$('.drag-over', sc).forEach((x) => x.classList.remove('drag-over')); sc.classList.remove('drop-on');
    if (D.winDirty) { D.winDirty = false; renderShortcuts(); }
  });
  sc.addEventListener('dragenter', (ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = dragId ? 'move' : 'copy'; });
  sc.addEventListener('dragover', (ev) => {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = dragId ? 'move' : 'copy';
    const t = ev.target.closest('[data-sc]');
    $$('.drag-over', sc).forEach((x) => x.classList.toggle('drag-over', x === t));
    if (t && dragId) t.classList.add('drag-over');
    sc.classList.toggle('drop-on', !dragId);
  });
  sc.addEventListener('dragleave', (ev) => { if (!sc.contains(ev.relatedTarget)) { sc.classList.remove('drop-on'); $$('.drag-over', sc).forEach((x) => x.classList.remove('drag-over')); } });
  sc.addEventListener('drop', async (ev) => {
    ev.preventDefault();
    sc.classList.remove('drop-on');
    const t = ev.target.closest('[data-sc]');
    $$('.drag-over', sc).forEach((x) => x.classList.remove('drag-over'));
    if (dragId) {
      const ids = D.sc.map((s) => s.id).filter((id) => id !== dragId);
      const at = t ? ids.indexOf(t.dataset.sc) : ids.length;
      ids.splice(at < 0 ? ids.length : at, 0, dragId);
      dragId = null;
      return reorderShortcuts(ids);
    }
    const paths = dropPaths(ev.dataTransfer);
    DRAG_PATHS = null;
    if (!paths.length) return toast('Rien à épingler : fais plutôt un clic droit sur l\'élément › Épingler aux raccourcis.');
    for (const p of paths.slice(0, 8)) {
      const it = D.items.find((x) => x.path === p);
      const e = it?.e;
      await pinShortcut(e && e.ext === 'desktop' && !e.dir ? 'app' : e && !e.dir ? 'fichier' : 'dossier', p);
    }
    return loadShortcuts();
  });
}

// ── à ranger ──
function depuis(ts) {
  const days = (Date.now() - ts * 1000) / 864e5;
  if (days < 1) return 'depuis aujourd\'hui';
  if (days < 2) return 'depuis hier';
  if (days < 7) return `depuis ${Math.floor(days)} jours`;
  if (days < 30) { const w = Math.floor(days / 7); return `depuis ${w} semaine${w > 1 ? 's' : ''}`; }
  if (days < 365) return `depuis ${Math.floor(days / 30)} mois`;
  return 'depuis plus d\'un an';
}
async function loadTodo() {
  if (MODE !== 'bureau') return;
  try { D.todo = await api('/api/bureau/a-ranger'); } catch { D.todo = null; }
  const el = $('#todo');
  const t = D.todo;
  const cands = t ? [['telechargements', 5], ['bureau', 8]].map(([k, min]) => ({ k, min, ...t[k] })).filter((c) => c.fichiers >= c.min).sort((a, b) => b.fichiers - a.fichiers) : [];
  if (!cands.length) { el.hidden = true; return; }
  const c = cands[0];
  el.hidden = false;
  el.innerHTML = `<div class="todo"><span class="n serif">${c.fichiers}</span><p>fichiers en vrac ${c.k === 'bureau' ? 'sur <b>le bureau</b>' : 'dans <b>Téléchargements</b>'}<br>${esc(depuis(c.depuis))} · ${fmtSize(c.taille)}</p>
    <button class="btn primary sm" data-todo="${esc(c.chemin)}" title="Le tri intelligent propose un rangement : rien ne bouge sans ton accord">Trier</button></div>`;
}

// ───────────────────────── Discussion (volet et « Demander ») ─────────────────────────
const CHIPS = [
  { t: 'Ranger mes téléchargements', icon: 'sparkles', run: () => openMain({ vue: 'sort', chemin: D.b?.telechargements }) },
  { t: 'Résumer un document', icon: 'doc', run: async () => { const p = await pickPath({ title: 'Document à résumer', mode: 'files', start: D.b?.dossier }); if (p) askAbout(p, 'Résume ce document en quelques points clés.'); } },
  { t: 'Qu\'y a-t-il sur mon bureau ?', icon: 'folder', run: () => sendChat({ text: 'Fais-moi un point rapide sur ce qu\'il y a sur mon bureau et propose un rangement.', agentName: 'Rangeur', workspace: D.b?.dossier }) },
];
const msgsEl = () => (MODE === 'demander' ? $('#aMsgs') : $('#vMsgs'));
function scrollMsgs(force) { const m = msgsEl(); if (m && (force || m.scrollHeight - m.scrollTop - m.clientHeight < 140)) m.scrollTop = m.scrollHeight; }
async function loadConv() {
  try { D.conv = await api('/api/bureau/conv'); } catch (e) { D.conv = null; toast(e.message, 'err'); }
  renderAgentSelect();
  if (MODE === 'bureau') renderConv();
}
// Remet la discussion du volet à jour d'après le serveur. Avec rotation : après une longue pause, une nouvelle
// discussion commence (un vieux sujet ne pollue pas la question suivante) ; la précédente peut être reprise.
async function syncConv(rotation, quiet = false) {
  let c;
  try { c = await api(`/api/bureau/conv${rotation ? '' : '?rotation=0'}`); } catch { return; }
  if (D.busy && !rotation) return;
  const other = c.id !== D.conv?.id;
  if (c.auto && c.precedente) D.autoNew = true;
  if (other || c.modifie !== D.conv.modifie) {
    D.conv = c;
    renderAgentSelect();
    if (MODE === 'bureau') renderConv();
    else if (other) { const box = $('#answer'); box.hidden = true; box.innerHTML = ''; reportSize(); }
  }
  if (c.auto && c.precedente && !quiet) {
    toast(`Nouvelle discussion : la précédente avait plus de ${D.b?.conv_heures || 4} h.`, 'info', { label: 'Reprendre la précédente', action: resumeConv, timeout: 12000 });
  }
}
// La discussion du volet est-elle assez ancienne pour qu'on reparte sur une neuve ? (le serveur a le dernier mot)
function convStale() {
  const h = D.b?.conv_heures;
  return !!(h && D.conv?.messages?.length && !D.conv.pending && Date.now() - new Date(D.conv.modifie).getTime() >= h * 36e5);
}
async function resumeConv() {
  if (D.busy) {  // on reprend l'ancienne pendant que la nouvelle répond : on arrête d'abord cette réponse
    D.ctrl?.abort();
    for (let i = 0; i < 50 && D.busy; i++) await new Promise((r) => setTimeout(r, 100));
    if (D.busy) return toast('Attends la fin de la réponse (ou arrête-la).');
  }
  try { D.conv = await post('/api/bureau/conv/reprendre'); } catch (e) { return toast(e.message, 'err'); }
  D.autoNew = false;
  renderAgentSelect();
  if (MODE === 'bureau') renderConv();
  else if (D.conv.messages.length) { showAnswer(); finishAnswer(D.conv.messages.length); }
  return null;
}
function renderAgentSelect() {
  const sel = $('#vAgent');
  if (!sel) return;
  sel.innerHTML = `<option value="">💬 Discussion libre</option>${S.agents.map((a) => `<option value="${esc(a.id)}" ${a.id === D.conv?.agent_id ? 'selected' : ''}>${esc(a.icone)} ${esc(a.nom)}</option>`).join('')}`;
  $('#vIn').placeholder = D.conv?.agent_id ? `Demande quelque chose à ${agentById(D.conv.agent_id)?.nom || 'l\'agent'}…` : 'Écris à l\'Archiviste, ou « ouvre Grimoire »…';
}
async function changeAgent(agent_id) {
  if (!D.conv) return;
  // pendant une réponse, changer d'agent effaçait l'affichage en cours et le choix était perdu à la fin
  if (D.busy) { toast('Attends la fin de la réponse (ou arrête-la) pour changer d\'agent.'); renderAgentSelect(); return; }
  try { D.conv = { ...(await post(`/api/conversations/${D.conv.id}`, { agent_id, workspace: '' })), precedente: D.conv.precedente }; } catch (e) { toast(e.message, 'err'); }
  renderAgentSelect(); renderConv();
}
async function newConv(agent_id) {
  if (D.busy) return toast('Attends la fin de la réponse (ou arrête-la).');
  try { D.conv = await post('/api/bureau/conv/nouvelle', { agent_id: agent_id === undefined ? D.conv?.agent_id : agent_id }); } catch (e) { return toast(e.message, 'err'); }
  renderAgentSelect(); renderConv();
  $('#vIn')?.focus();
}
const avatar = (a) => (a ? `<span class="av">${esc(a.icone)}</span>` : '<img src="/favicon.svg" alt="" width="26" height="26">');
function attChips(list) {
  return list?.length ? `<div class="q-atts">${list.map((x) => `<span title="${esc(x.path)}">${ic(x.kind === 'folder' ? 'folder' : 'file')}${esc(x.name)}</span>`).join('')}</div>` : '';
}
function msgActs(i) {
  return `<div class="acts"><button class="icon-btn sm" data-act="copy" data-m="${i}" title="Copier">${ic('copy', 'sm')}</button>${MODE === 'bureau' ? `<button class="icon-btn sm" data-act="docx" data-m="${i}" title="${hasGrimoire() ? 'Envoyer vers Grimoire (document Word)' : 'Enregistrer en document Word'}">${ic('quill', 'sm')}</button>` : ''}</div>`;
}
function convHtml(msgs, from = 0) {
  const a = agentById(D.conv?.agent_id);
  const out = [];
  let turn = null;
  const flush = () => { if (turn) { out.push(`<div class="a">${avatar(a)}<div class="body">${turn.join('')}</div></div>`); turn = null; } };
  msgs.forEach((m, i) => {
    if (i < from) return;
    if (m.role === 'user') { flush(); out.push(attChips(m.attachments)); if (m.content) out.push(`<div class="q">${esc(m.content)}</div>`); return; }
    if (!turn) turn = [];
    if (m.role === 'tool') { turn.push(stepHtml({ ...m, name: m.tool_name, id: m.call_id })); return; }
    if (m.role === 'error') { turn.push(errorHtml(m.content, i === msgs.length - 1 && m.reessayer !== false && !D.conv?.pending)); return; }
    if (m.content) turn.push(`<div class="md">${md(m.content)}</div>${msgActs(i)}`);
  });
  if (D.conv?.pending?.length) {
    if (!turn) turn = [];
    for (const c of D.conv.pending) turn.push(stepHtml({ ...c, waiting: !!c.needs }));
    turn.push(confirmHtml(D.conv.pending.filter((x) => x.needs)));
  }
  flush();
  return out.join('');
}
function renderConv() {
  const el = $('#vMsgs');
  if (!el) return;
  const msgs = D.conv?.messages || [];
  if (!msgs.length) {
    const a = agentById(D.conv?.agent_id);
    const fresh = D.autoNew && D.conv?.precedente ? `<small class="fresh">Nouvelle discussion : la précédente avait plus de ${D.b?.conv_heures || 4} h.</small>` : '';
    el.innerHTML = `<div class="hello"><img src="/static/logo-seal.svg" alt="" width="54" height="54"><b>${a ? `${esc(a.icone)} ${esc(a.nom)}` : `Bonjour ${esc(S.settings.prenom || '')}`}</b>${fresh}
      ${a ? esc(a.description || '') : 'Je tourne sur ton PC, rien ne sort de ta machine. Glisse un fichier ici pour en parler.'}
      ${a ? '' : `<div class="chips">${CHIPS.map((c, i) => `<button class="pill" data-chip="${i}">${ic(c.icon)}${esc(c.t)}</button>`).join('')}</div>`}
      ${D.conv?.precedente ? `<div class="chips"><button class="pill" data-v="resume" title="Rouvre ici la discussion d'avant">${ic('undo')}Reprendre la discussion précédente</button></div>` : ''}</div>`;
    return;
  }
  D.autoNew = false;
  el.innerHTML = convHtml(msgs);
  scrollMsgs(true);
}
function renderVAtts() {
  const el = $('#vAtts');
  if (!el) return;
  el.innerHTML = D.atts.map((p, i) => `<span title="${esc(p)}">${ic('file', 'sm')}<em>${esc(basename(p))}</em><button data-v="rmAtt" data-i="${i}" title="Retirer">×</button></span>`).join('');
}
function attachToChat(paths) {
  if (MODE !== 'bureau') return;
  if (!D.b.volet) setVolet(true);
  for (const p of paths) if (!D.atts.includes(p)) D.atts.push(p);
  renderVAtts();
  $('#vIn').focus();
}
function askAbout(paths, text) {
  if (MODE === 'bureau' && !D.b.volet) setVolet(true);
  sendChat({ text, atts: paths });
}
function sendFromComposer() {
  const inp = $('#vIn');
  const text = inp.value.trim();
  if (!text && !D.atts.length) return;
  inp.value = ''; inp.style.height = 'auto';
  const atts = D.atts.slice();
  D.atts = []; renderVAtts();
  sendChat({ text, atts });
}
function liveTurn(container) {
  const a = agentById(D.conv?.agent_id);
  const el = document.createElement('div');
  el.className = 'a';
  el.innerHTML = `${avatar(a)}<div class="body"><div class="row muted typing" style="font-size:12.5px"><span class="spinner"></span> ${esc(a?.modele || S.settings.model)} réfléchit…</div></div>`;
  container.append(el);
  const body = $('.body', el);
  let seg = null;
  let raf = 0;
  const untype = () => $('.typing', body)?.remove();
  const paint = () => { raf = 0; if (seg) { seg.el.innerHTML = md(seg.text); scrollMsgs(); } };
  return {
    on(ev) {
      switch (ev.t) {
        case 'content':
          untype();
          if (!seg) { const d = document.createElement('div'); d.className = 'md'; body.append(d); seg = { el: d, text: '' }; }
          seg.text += ev.d;
          if (!raf) raf = requestAnimationFrame(paint);
          break;
        case 'message_end': if (seg) paint(); seg = null; break;
        case 'tool_call':
          untype();
          body.insertAdjacentHTML('beforeend', stepHtml({ id: ev.id, name: ev.name, description: ev.description, pending: !ev.needs_confirm, waiting: ev.needs_confirm }));
          scrollMsgs(); break;
        case 'tool_result': {
          const old = $(`.step[data-step="${CSS.escape(ev.id)}"]`, container);
          const html = stepHtml({ id: ev.id, name: ev.name, description: old ? $('.desc', old).textContent : '', ok: ev.ok, refuse: ev.refuse, summary: ev.summary });
          if (old) old.outerHTML = html; else body.insertAdjacentHTML('beforeend', html);
          scrollMsgs(); break;
        }
        case 'confirm': untype(); body.insertAdjacentHTML('beforeend', confirmHtml(ev.pending)); scrollMsgs(true); break;
        case 'notice': body.insertAdjacentHTML('beforeend', `<div class="notice">${esc(ev.d)}</div>`); break;
        case 'error': untype(); body.insertAdjacentHTML('beforeend', errorHtml(ev.d, false)); scrollMsgs(true); break;
        default: break;
      }
      reportSize();
    },
    error(msg) { untype(); body.insertAdjacentHTML('beforeend', errorHtml(msg, false)); },
  };
}
function setVBusy(on) {
  D.busy = on;
  const b = MODE === 'demander' ? $('#askGo') : $('#vSend');
  if (!b) return;
  if (MODE === 'bureau') { b.classList.toggle('stop', on); b.innerHTML = ic(on ? 'stop' : 'send'); b.title = on ? 'Arrêter' : 'Envoyer'; }
  const sel = $('#vAgent');
  if (sel) sel.disabled = on;  // on ne change pas d'agent au milieu d'une réponse
}
async function sendChat({ text = '', atts = [], decisions = null, regenerate = false, agentName = null, workspace = null } = {}) {
  if (D.busy) return toast('Une réponse est en cours : attends-la ou arrête-la.');
  if (MODE === 'bureau' && !D.b.volet) setVolet(true);
  setVBusy(true);  // tout de suite : une deuxième touche Entrée ne lance pas deux envois
  let container = null;
  let live = null;
  let localErr = null;  // erreur que le serveur n'a pas pu enregistrer (Archiviste injoignable, discussion occupée…)
  let failed = false;
  let from = 0;
  try {
    if (agentName) {
      const a = S.agents.find((x) => x.nom === agentName);
      if (a && (!D.conv || D.conv.agent_id !== a.id || D.conv.messages.length)) {
        try { D.conv = await post('/api/bureau/conv/nouvelle', { agent_id: a.id }); } catch (e) { return toast(e.message, 'err'); }
        if (workspace) { try { D.conv = await post(`/api/conversations/${D.conv.id}`, { workspace }); } catch { /* */ } }
        renderAgentSelect();
        if (MODE === 'bureau') renderConv();
      }
    } else if (!decisions && !regenerate) await syncConv(true);  // longue pause : on repart sur une discussion neuve
    if (!D.conv) await loadConv();
    if (!D.conv) return null;
    const body = { conv_id: D.conv.id };
    if (MODE === 'demander') {
      container = showAnswer();
    } else {
      container = $('#vMsgs');
      if (!D.conv.messages.length) container.innerHTML = '';
    }
    if (text || atts.length) {
      body.message = text; body.attachments = atts;
      container.insertAdjacentHTML('beforeend', attChips(atts.map((p) => ({ path: p, name: basename(p), kind: 'file' }))) + (text ? `<div class="q">${esc(text)}</div>` : ''));
    }
    if (decisions) { body.decisions = decisions; $$('.confirm-card', container).forEach((x) => x.remove()); }
    if (regenerate) { body.regenerate = true; $$('.err-box', container).pop()?.remove(); }
    live = liveTurn(container);
    scrollMsgs(true);
    D.ctrl = new AbortController();
    from = D.conv.messages.length;
    await streamApi('/api/chat', body, (ev) => { if (ev.t === 'error') failed = true; live.on(ev); }, D.ctrl.signal);
  } catch (e) {
    if (e.name !== 'AbortError') { localErr = e.message; live?.error(e.message); }
  } finally {
    setVBusy(false);
    D.ctrl = null;
    if (container && D.conv) {
      try { D.conv = await api(`/api/conversations/${D.conv.id}`); } catch { /* */ }
      if (MODE === 'bureau') renderConv();
      else finishAnswer(from);
      if (localErr) {  // le rafraîchissement vient d'effacer l'affichage en direct : on remet le message
        const saved = D.conv.messages.some((m) => m.role === 'user' && m.content === text);
        if (text && !saved) container.insertAdjacentHTML('beforeend', `<div class="q">${esc(text)}</div>`);
        container.insertAdjacentHTML('beforeend', errorHtml(localErr, false));
        scrollMsgs(true); reportSize();
      }
    } else if (localErr) toast(localErr, 'err');
    if (failed || localErr || !S.status?.ok) refreshVStatus();  // la pastille dit tout de suite si Ollama est tombé, ou revenu
  }
  return null;
}
function chatAct(b) {
  const act = b.dataset.act;
  const seg = b.closest('.seg');
  const card = b.closest('.confirm-card');
  const text = () => D.conv?.messages?.[+b.dataset.m]?.content || '';
  if (act === 'copy') return copyText(text());
  if (act === 'retry') return sendChat({ regenerate: true });
  if (act === 'docx') return sendToOffice(text(), 'docx', D.conv?.titre);
  if (act === 'cfYes' || act === 'cfNo') { $$('button', seg).forEach((x) => x.classList.toggle('on', x === b)); return null; }
  if (act === 'cfAll' || act === 'cfNone') {
    $$('.confirm-item', card).forEach((it) => { $('.yes', it).classList.toggle('on', act === 'cfAll'); $('.no', it).classList.toggle('on', act === 'cfNone'); });
  }
  if (['cfSend', 'cfAll', 'cfNone'].includes(act)) {
    const decisions = {};
    $$('.confirm-item', card).forEach((it) => { decisions[it.dataset.id] = $('.yes', it).classList.contains('on'); });
    $$('button', card).forEach((x) => { x.disabled = true; });
    return sendChat({ decisions });
  }
  return null;
}

// ───────────────────────── Fenêtre « Demander » (Super + Espace) ─────────────────────────
function postToGtk(msg) { try { window.webkit.messageHandlers.archiviste.postMessage(JSON.stringify(msg)); } catch { /* hors de la fenêtre GTK */ } }
let sizeRaf = 0;
function reportSize() {
  if (MODE !== 'demander' || sizeRaf) return;
  sizeRaf = requestAnimationFrame(() => { sizeRaf = 0; postToGtk({ t: 'taille', h: Math.ceil($('#ask').getBoundingClientRect().bottom) + 4 }); });
}
function closePopup() { if (D.ctrl) return; postToGtk({ t: 'fermer' }); }
function showAnswer() {
  const box = $('#answer');
  box.hidden = false;
  box.innerHTML = `<div class="msgs" id="aMsgs"></div><div class="foot" id="aFoot"></div>`;
  box.onclick = (ev) => {
    const b = ev.target.closest('[data-act], [data-f]');
    if (!b) return;
    if (b.dataset.act) { chatAct(b); return; }
    if (b.dataset.f === 'main') openMain({ vue: 'chat', conv: D.conv.id });
    if (b.dataset.f === 'new') newConv().then(() => { box.hidden = true; box.innerHTML = ''; $('#askIn').focus(); reportSize(); });
    if (b.dataset.f === 'stop') D.ctrl?.abort();
  };
  $('#aFoot').innerHTML = '<span class="grow"></span><button class="btn sm" data-f="stop">Arrêter</button>';
  reportSize();
  return $('#aMsgs');
}
function finishAnswer(from) {
  const msgs = D.conv?.messages || [];
  let start = from;
  for (let i = Math.min(from, msgs.length) - 1; i >= 0; i--) { if (msgs[i].role === 'user') { start = i; break; } }
  for (let i = start; i < msgs.length; i++) { if (msgs[i].role === 'user') { start = i; } }
  const last = msgs.map((m) => m.role).lastIndexOf('user');
  $('#aMsgs').innerHTML = convHtml(msgs, last >= 0 && !D.conv.pending ? last : start);
  $('#aFoot').innerHTML = `<span>${esc(D.conv.titre || 'Discussion du bureau')}</span><span class="grow"></span>
    <button class="btn sm" data-f="new">${ic('plus', 'sm')} Nouvelle discussion</button><button class="btn sm" data-f="main">${ic('external', 'sm')} Continuer dans Archiviste</button>`;
  scrollMsgs(true);
  reportSize();
  $('#askIn').focus();
}
window.archivisteMontrer = () => { const i = $('#askIn'); i.focus(); i.select(); reportSize(); if (!D.busy) syncConv(false); };

// ───────────────────────── Fond d'écran (si Archiviste le dessine) ─────────────────────────
async function applyFond() {
  if (!D.ownFond || MODE !== 'bureau') return;
  let f;
  try { f = await api('/api/bureau/fond'); } catch { return; }
  const key = `${f.chemin}|${f.mtime}|${f.options}|${f.couleur}`;
  if (key === D.fondKey) return;
  D.fondKey = key;
  const st = document.body.style;
  st.backgroundColor = f.couleur;
  st.backgroundImage = f.chemin && f.options !== 'none' ? `url("/api/bureau/fond/image?t=${enc(TOKEN)}&v=${enc(f.chemin + f.mtime)}")` : 'none';
  const map = { zoom: ['cover', 'no-repeat'], spanned: ['cover', 'no-repeat'], scaled: ['contain', 'no-repeat'], centered: ['auto', 'no-repeat'],
    stretched: ['100% 100%', 'no-repeat'], wallpaper: ['auto', 'repeat'] };
  const [size, rep] = map[f.options] || map.zoom;
  st.backgroundSize = size; st.backgroundRepeat = rep; st.backgroundPosition = 'center';
}

// ───────────────────────── Démarrage ─────────────────────────
async function initBureau() {
  document.body.classList.add('mode-' + MODE, D.ownFond ? 'fond-archiviste' : 'fond-cinnamon');
  $$('[data-icon]').forEach((el) => { el.outerHTML = ic(el.dataset.icon); });
  try {
    [S.settings, S.tools, D.b, S.agents] = await Promise.all([api('/api/settings'), api('/api/tools'), api('/api/bureau'), api('/api/agents')]);
  } catch (e) {
    toast(`Archiviste ne répond pas : ${e.message}`, 'err', { sticky: true });
    return;
  }
  S.home = S.settings.home;
  refreshVStatus();
  if (MODE === 'demander') {
    const inp = $('#askIn');
    const askNow = (t) => { if (!t) return; inp.value = ''; sendChat({ text: t }); };
    makeLauncher({ input: inp, box: $('#askRes'), onAsk: askNow, always: true });
    $('#askGo').addEventListener('click', () => askNow(inp.value.trim()));
    new ResizeObserver(reportSize).observe($('#ask'));
    setTimeout(() => $('#askIn').focus(), 60);
    loadApps();
    loadConv();
    return;
  }
  buildVolet();
  applyVolet();
  bindDesk();
  applyFond();
  await Promise.all([loadElements(), loadShortcuts(), loadConv(), loadTodo()]);
  loadWindows();
  try { D.rv = (await api('/api/bureau/sig')).rv; } catch { /* */ }
  loadApps();
  setInterval(poll, 2500);
  setInterval(() => { if (!document.hidden) refreshVStatus(); }, 60000);
  setInterval(loadTodo, 5 * 60000);
  setInterval(applyFond, 60000);
  setTimeout(refreshVMaj, 30000);
  setInterval(refreshVMaj, 30 * 60000);
  window.addEventListener('focus', () => { if (!D.busy) syncConv(false); });
}
initBureau();
