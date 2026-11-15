/* Tests d'interface d'Archiviste : le volet du bureau et la fenêtre principale, dans un vrai navigateur
   (Chrome sans affichage, piloté par playwright-core). Lancés par tests/lancer.sh après les tests de l'API.

   À la main :  npm install --prefix tests   puis   ./tests/lancer.sh
   Variables : CHROME (chemin du navigateur), ARCHI_HOME (dossier personnel jetable), ARCHI_OLLAMA (faux Ollama). */
'use strict';
const fs = require('fs');

let chromium;
try { ({ chromium } = require('playwright-core')); } catch { ({ chromium } = require('playwright')); }

const BASE = process.argv[2] || 'http://127.0.0.1:8766';
const HOME = process.env.ARCHI_HOME || '/tmp/archi-home';
const OLLAMA = process.env.ARCHI_OLLAMA || 'http://127.0.0.1:11500';
const CHROME = process.env.CHROME
  || ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find((p) => fs.existsSync(p));
const DESK = `${HOME}/Bureau`;
const DATA = `${HOME}/.local/share/archiviste`;

let fails = 0;
function check(cond, label) {
  console.log((cond ? '  ok  ' : '  ÉCHEC ') + label);
  if (!cond) fails++;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  if (!CHROME) throw new Error('Aucun navigateur trouvé : indique son chemin dans la variable CHROME.');
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-proxy-server'] });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const jsErrors = [];
  const watch = (p) => { p.on('pageerror', (e) => jsErrors.push(e.message)); return p; };

  // ── préparation : un bureau avec un vrai dossier, un lien vers un dossier et quelques fichiers ──
  fs.mkdirSync(`${DESK}/Vrai dossier`, { recursive: true });
  fs.mkdirSync(`${HOME}/Documents/Cible du lien`, { recursive: true });
  fs.writeFileSync(`${HOME}/Documents/Cible du lien/contrat.txt`, 'important');
  if (!fs.existsSync(`${DESK}/Lien dossier`)) fs.symlinkSync(`${HOME}/Documents/Cible du lien`, `${DESK}/Lien dossier`);

  const page = watch(await ctx.newPage());
  await page.goto(`${BASE}/bureau?fond=1&b=40`);
  await page.waitForSelector('#vIn');
  const post = (path, body = {}) => page.evaluate(([p, b]) => post(p, b), [path, body]);
  const idle = () => page.waitForFunction(() => !D.busy, null, { timeout: 20000 });
  const ask = async (text) => { await page.fill('#vIn', text); await page.press('#vIn', 'Enter'); await sleep(150); await idle(); await sleep(150); };
  await post('/api/settings', { ollama_url: OLLAMA });
  await post('/api/bureau/reglages', { volet: true, volet_largeur: 0, conv_heures: 4 });
  await post('/api/bureau/conv/nouvelle', {});
  await page.reload();
  await page.waitForSelector('#vIn');
  await page.waitForFunction(() => D.conv && D.sc.length && D.items.length);
  await page.evaluate(() => refreshVStatus());

  console.log('— volet : affichage et discussion');
  check(await page.isVisible('#volet') && (await page.locator('#sc .t').count()) >= 2, 'le volet s\'affiche avec ses raccourcis');
  check(await page.locator('#vStatus .dot.ok').count() === 1, 'pastille « prêt »');
  await ask('Bonjour, que peux-tu faire ?');
  check((await page.innerText('#vMsgs')).includes('Voici une liste') && await page.locator('#vMsgs .md table').count() === 1, 'la réponse s\'affiche, mise en forme');

  console.log('— volet : les erreurs restent affichées');
  await post('/api/settings', { ollama_url: 'http://127.0.0.1:9' });
  await ask('Résume-moi ma journée');
  let err = await page.locator('#vMsgs .err-box').count() ? await page.innerText('#vMsgs .err-box') : '';
  check(err.includes('injoignable'), 'Ollama injoignable : le message reste après la fin de la réponse');
  check(await page.locator('#vMsgs .err-box [data-act="retry"]').count() === 1, 'bouton « Réessayer »');
  check(await page.locator('#vStatus .dot.bad').count() === 1, 'la pastille passe tout de suite au rouge');
  await post('/api/settings', { ollama_url: OLLAMA });
  await page.click('#vMsgs .err-box [data-act="retry"]');
  await sleep(150); await idle(); await sleep(200);
  check(await page.locator('#vMsgs .err-box').count() === 0 && await page.locator('#vMsgs .a .md').count() === 2, 'Réessayer : la réponse remplace l\'erreur');
  check(await page.locator('#vStatus .dot.ok').count() === 1, 'la pastille repasse au vert dès que ça remarche');
  await page.route('**/api/chat', (r) => r.abort(), { times: 1 });
  await ask('question sans serveur');
  const txt = await page.innerText('#vMsgs');
  check(await page.locator('#vMsgs .err-box').count() === 1 && txt.includes('question sans serveur'), 'Archiviste injoignable : la question et l\'erreur restent à l\'écran');
  await ask('on continue');
  check(await page.locator('#vMsgs .err-box').count() === 0 && await page.locator('#vMsgs .a .md').count() === 3, 'la discussion reprend normalement');

  console.log('— volet : pas de changement d\'agent pendant une réponse');
  await page.fill('#vIn', '[lent] prends ton temps');
  await page.press('#vIn', 'Enter');
  await sleep(500);
  const mid = await page.evaluate(async () => {
    const before = D.conv.agent_id;
    await changeAgent(S.agents[0].id);
    return { disabled: document.querySelector('#vAgent').disabled, live: !!document.querySelector('#vMsgs .typing'), same: D.conv.agent_id === before };
  });
  check(mid.disabled && mid.live && mid.same, 'sélecteur d\'agent verrouillé, la réponse en cours reste affichée');
  await idle(); await sleep(200);
  check(!(await page.evaluate(() => document.querySelector('#vAgent').disabled)) && await page.locator('#vMsgs .a .md').count() === 4, 'réponse complète, sélecteur de nouveau libre');

  console.log('— bureau : corbeille');
  await page.evaluate(() => loadElements());
  await page.waitForSelector('#icons .dicon:has(.lbl:text-is("Vrai dossier"))');
  await page.click('#icons .dicon:has(.lbl:text-is("Vrai dossier"))');
  await page.keyboard.press('Delete');
  await page.waitForSelector('.overlay', { timeout: 3000 }).catch(() => {});
  check(await page.locator('.overlay').count() === 1 && fs.existsSync(`${DESK}/Vrai dossier`), 'Suppr sur un dossier : confirmation demandée');
  await page.click('.overlay [data-close]');
  await sleep(200);
  check(fs.existsSync(`${DESK}/Vrai dossier`), 'Annuler : le dossier reste');
  await page.click('#icons .dicon:has(.lbl:text-is("Lien dossier"))');
  await page.keyboard.press('Delete');
  await sleep(700);
  check(!fs.existsSync(`${DESK}/Lien dossier`) && fs.readFileSync(`${HOME}/Documents/Cible du lien/contrat.txt`, 'utf8') === 'important'
    && await page.locator('.overlay').count() === 0, 'Suppr sur un lien : seul le lien part, sa cible reste');

  console.log('— bureau : les icônes s\'arrêtent au bord du volet');
  for (let i = 0; i < 110; i++) fs.writeFileSync(`${DESK}/doc-${String(i).padStart(3, '0')}.txt`, 'x');
  await page.evaluate(() => loadElements());
  await sleep(300);
  const geo = () => page.evaluate(() => {
    const v = document.querySelector('#volet').getBoundingClientRect();
    const g = document.querySelector('#icons');
    const box = g.getBoundingClientRect();
    return { voletLeft: v.left, voletWidth: v.width, gridRight: box.right, scrolls: g.scrollWidth > g.clientWidth, fade: g.classList.contains('fade-r'), left: g.scrollLeft, n: D.items.length };
  });
  let g = await geo();
  check(g.n > 110 && g.gridRight <= g.voletLeft && g.scrolls && g.fade, `${g.n} icônes : aucune sous le volet, la grille défile`);
  await page.mouse.move(600, 500);
  await page.mouse.wheel(0, 600);
  await sleep(200);
  check((await geo()).left > 0, 'la molette fait défiler les icônes');
  await page.evaluate(() => { document.querySelector('#icons').scrollLeft = 0; });
  await sleep(150);
  check(await page.isVisible('#icNext') && !(await page.isVisible('#icPrev')), 'une flèche signale les icônes qui restent');
  await page.click('#icNext');
  await sleep(700);
  check((await geo()).left > 100 && await page.isVisible('#icPrev'), 'la flèche fait défiler d\'une page');
  await page.evaluate(() => { document.querySelector('#icons').scrollLeft = 0; });

  console.log('— volet : largeur réglable');
  const grip = await page.locator('#vGrip').boundingBox();
  const gx = grip.x + grip.width / 2;
  const gy = grip.y + grip.height / 2;
  await page.mouse.move(gx, gy);
  await page.mouse.down();
  await page.mouse.move(gx - 80, gy, { steps: 4 });
  await page.mouse.move(gx - 150, gy, { steps: 4 });
  await page.mouse.up();
  await sleep(400);
  const g2 = await geo();
  const saved = (await page.evaluate(() => api('/api/bureau'))).volet_largeur;
  check(Math.abs(g2.voletWidth - g.voletWidth - 150) <= 3 && Math.abs(saved - g2.voletWidth) <= 1, `poignée : volet élargi de 150 px et mémorisé (${Math.round(g.voletWidth)} → ${Math.round(g2.voletWidth)})`);
  check(g2.gridRight <= g2.voletLeft, 'les icônes suivent le bord du volet');
  await page.reload();
  await page.waitForSelector('#vIn');
  await page.waitForFunction(() => D.conv && D.items.length);
  check(Math.abs((await geo()).voletWidth - g2.voletWidth) <= 1, 'largeur gardée après rechargement');
  await page.dblclick('#vGrip');
  await sleep(300);
  check(Math.abs((await geo()).voletWidth - g.voletWidth) <= 1 && (await page.evaluate(() => api('/api/bureau'))).volet_largeur === null, 'double-clic : largeur d\'origine');
  await page.mouse.move(gx, gy);
  await page.mouse.down();
  await page.mouse.move(gx + 900, gy, { steps: 5 });
  await page.mouse.up();
  await sleep(300);
  const narrow = await page.evaluate(() => {
    const v = document.querySelector('#volet');
    const h3 = document.querySelector('#conv h3');
    return { w: v.getBoundingClientRect().width, overflow: h3.scrollWidth > h3.clientWidth + 1 || document.querySelector('.vmain').scrollWidth > document.querySelector('.vmain').clientWidth + 1 };
  });
  check(narrow.w === 440 && !narrow.overflow, 'largeur minimale : rien ne déborde');
  await page.dblclick('#vGrip');
  await sleep(200);

  console.log('— volet : nouvelle discussion après une longue pause');
  const oldId = await page.evaluate(() => D.conv.id);
  const file = `${DATA}/conversations/${oldId}.json`;
  const conv = JSON.parse(fs.readFileSync(file, 'utf8'));
  conv.modifie = '2020-01-01T08:00:00';
  fs.writeFileSync(file, JSON.stringify(conv));
  await page.evaluate(() => { D.conv.modifie = '2020-01-01T08:00:00'; document.activeElement.blur(); });
  await page.click('#vMsgs');   // relire l'ancienne réponse ne change rien
  await sleep(300);
  check(await page.evaluate((id) => D.conv.id === id, oldId), 'cliquer dans la discussion pour la relire : elle reste');
  await page.focus('#vIn');
  await page.waitForFunction((id) => D.conv.id !== id, oldId, { timeout: 5000 }).catch(() => {});
  check(await page.evaluate((id) => D.conv.id !== id && !D.conv.messages.length, oldId)
    && await page.locator('#vMsgs [data-v="resume"]').count() === 1 && (await page.innerText('#vMsgs')).includes('Nouvelle discussion'),
  'on se remet à écrire après une longue pause : discussion neuve, avec « Reprendre la précédente »');
  await page.click('#vMsgs [data-v="resume"]');
  await page.waitForFunction((id) => D.conv.id === id, oldId, { timeout: 5000 }).catch(() => {});
  check(await page.evaluate((id) => D.conv.id === id, oldId) && await page.locator('#vMsgs .a .md').count() === 4, 'Reprendre : l\'ancienne discussion revient');

  console.log('— volet : lanceur');
  const apps = [['firefox', 'Firefox', 'Navigateur Web'], ['org.gnome.Terminal', 'Terminal', ''], ['sticky', 'Notes', 'Notes autocollantes'], ['libreoffice-calc', 'LibreOffice Calc', 'Tableur']]
    .map(([id, nom, generique]) => ({ id: `${id}.desktop`, nom, generique, description: '', icone: id, categories: [], mots: [], cmd: id }));
  await page.evaluate((a) => { D.apps = a; }, apps);
  const launched = [];
  const asked = [];
  await page.route('**/api/apps/lancer', (r) => { launched.push(JSON.parse(r.request().postData()).id); r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"nom":"x"}' }); });
  await page.route('**/api/chat', (r) => { asked.push(JSON.parse(r.request().postData()).message); r.fulfill({ status: 200, contentType: 'application/x-ndjson', body: '{"t":"done"}\n' }); });
  const type = async (t) => { await page.fill('#vIn', t); await sleep(900); await page.press('#vIn', 'Enter'); await sleep(300); await idle(); };
  await type('ouvre firefox');
  await type('ouvrr le terminale');
  await type('ouvre le rapport de juin');
  await type('Bonjour');
  check(launched.join() === 'firefox.desktop,org.gnome.Terminal.desktop', `« ouvre firefox », « ouvrr le terminale » : applis lancées (${launched.join()})`);
  check(asked.join('|') === 'ouvre le rapport de juin|Bonjour', 'une phrase ou un mot quelconque part à l\'IA');
  await page.unroute('**/api/apps/lancer');
  await page.unroute('**/api/chat');
  await page.route('**/api/fs/search?rapide=1**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ base: HOME, query: 'x', results: [], tronque: true, incomplet: 'temps', delai: 2.5 }) }));
  await page.fill('#vIn', 'ouvre budget prévisionnel');
  await page.waitForSelector('#vSugg .wait.cut', { timeout: 4000 }).catch(() => {});
  check(await page.locator('#vSugg .wait.cut').count() === 1, 'recherche de fichiers coupée par le temps : le volet le dit');
  await page.unroute('**/api/fs/search?rapide=1**');
  await page.fill('#vIn', '');

  console.log('— volet : applis ouvertes (repères sur les raccourcis)');
  const json = (o) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(o) });
  const shortcuts = [
    { id: 'r_t1', type: 'app', cible: 'firefox.desktop', nom: '', titre: 'Firefox', icone: 'firefox', ok: true, description: '' },
    { id: 'r_t2', type: 'app', cible: 'org.gnome.Terminal.desktop', nom: '', titre: 'Terminal', icone: 'terminal', ok: true, description: '' },
  ];
  shortcuts.push({ id: 'r_t3', type: 'dossier', cible: `${HOME}/Documents`, nom: '', titre: 'Documents', icone: '', ok: true, description: '' });
  const windows = { dispo: true, sig: 's1', groupes: [
    { cle: 'app:firefox.desktop', app: 'firefox.desktop', nom: 'Firefox', icone: 'firefox', n: 2, reduit: false, devant: true, titres: ['Accueil', 'Autre onglet'],
      fenetres: [{ id: 11, titre: 'Accueil', reduit: false }, { id: 12, titre: 'Autre onglet', reduit: true }] },
    { cle: 'app:vlc.desktop', app: 'vlc.desktop', nom: 'VLC', icone: 'vlc', n: 1, reduit: true, devant: false, titres: ['Film'], fenetres: [{ id: 21, titre: 'Film', reduit: true }] },
  ] };
  const acts = [];
  const starts = [];
  const moves = [];
  let open = true;
  await page.route('**/api/raccourcis', (r) => r.fulfill(json(shortcuts)));
  await page.route('**/api/fenetres', (r) => r.fulfill(json(windows)));
  await page.route('**/api/fenetres/action', (r) => { acts.push(JSON.parse(r.request().postData())); r.fulfill(json({ ok: open, ouverte: open, dispo: true })); });
  await page.route('**/api/apps/lancer', (r) => { starts.push(JSON.parse(r.request().postData())); r.fulfill(json({ ok: true, nom: 'x' })); });
  await page.evaluate(async () => { await loadShortcuts(); await loadWindows(); });
  const tile = (id) => `#sc [data-sc="${id}"]`;
  const cls = (sel) => page.evaluate((s) => document.querySelector(s)?.className || '', sel);
  check(/\brun\b/.test(await cls(tile('r_t1'))) && /\bfront\b/.test(await cls(tile('r_t1'))) && (await page.innerText(`${tile('r_t1')} .nb`)) === '2',
    'appli ouverte : repère « devant » et nombre de fenêtres sur son raccourci');
  check(!/\brun\b/.test(await cls(tile('r_t2'))) && await page.locator(`${tile('r_t2')} .run-dot`).count() === 0, 'appli fermée : pas de repère');
  check(/\bmini\b/.test(await cls('#sc [data-run="app:vlc.desktop"]')) && await page.locator('#sc .sep').count() === 1, 'appli ouverte sans raccourci : ajoutée à la colonne, marquée « réduite »');
  await page.click(tile('r_t1'));
  await page.waitForSelector('.menu', { timeout: 3000 }).catch(() => {});
  const chooser = await page.locator('.menu').count() ? await page.innerText('.menu') : '';
  const box = await page.locator('.menu').boundingBox().catch(() => null);
  const tbox = await page.locator(tile('r_t1')).boundingBox();
  check(chooser.includes('Accueil') && chooser.includes('Autre onglet') && chooser.includes('Tout réduire') && chooser.includes('Nouvelle fenêtre') && acts.length === 0,
    'appli avec plusieurs fenêtres : le clic propose de choisir laquelle');
  check(box && box.x + box.width <= tbox.x, 'le choix s\'ouvre à côté du raccourci, vers le bureau');
  await page.click('.menu button:has-text("Autre onglet")');
  await sleep(250);
  check(acts.length === 1 && acts[0].cle === 'app:firefox.desktop' && acts[0].action === 'afficher' && acts[0].fenetre === 12 && starts.length === 0, 'la fenêtre choisie est ramenée devant, rien n\'est relancé');
  await page.click(tile('r_t2'));
  await sleep(250);
  check(starts.length === 1 && starts[0].id === 'org.gnome.Terminal.desktop' && acts.length === 1, 'clic sur une appli fermée : elle est lancée');
  await page.click('#sc [data-run="app:vlc.desktop"]');
  await sleep(250);
  check(acts.length === 2 && acts[1].cle === 'app:vlc.desktop' && acts[1].action === 'basculer', 'une seule fenêtre : le clic la ramène ou la réduit directement');
  await page.click(tile('r_t1'), { button: 'right' });
  const menu = await page.innerText('.menu');
  check(menu.includes('Réduire') && menu.includes('Nouvelle fenêtre') && menu.includes('Fermer les 2 fenêtres'), 'clic droit : réduire, nouvelle fenêtre, fermer');
  await page.keyboard.press('Escape');

  // lâcher un fichier sur un raccourci : ouvert avec l'appli, rangé dans le dossier, épinglé ailleurs
  const dropOn = (sel, paths, type = 'drop') => page.evaluate(([q, list, t]) => {
    const dt = new DataTransfer();
    dt.setData('application/x-archiviste-paths', JSON.stringify(list));
    const el = document.querySelector(q);
    const r = el.getBoundingClientRect();
    el.dispatchEvent(new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 }));
  }, [sel, paths, type]);
  await page.route('**/api/fs/move', (r) => { moves.push(JSON.parse(r.request().postData())); r.fulfill(json({ ok: [], erreurs: [] })); });
  const dropped = `${DESK}/Vrai dossier`;
  await dropOn(tile('r_t1'), [dropped], 'dragover');
  check(/drag-over/.test(await cls(tile('r_t1'))) && !/drop-on/.test(await cls('#rail')), 'fichier au-dessus d\'une appli : son raccourci s\'allume');
  await dropOn(tile('r_t1'), [dropped]);
  await sleep(250);
  check(starts.length === 2 && starts[1].id === 'firefox.desktop' && starts[1].fichiers[0] === dropped && !starts[1].ramener, 'fichier lâché sur une appli : ouvert avec elle');
  await dropOn('#sc [data-run="app:vlc.desktop"]', [dropped]);
  await sleep(250);
  check(starts.length === 3 && starts[2].id === 'vlc.desktop' && starts[2].fichiers.length === 1, '… y compris sur une appli ouverte qui n\'a pas de raccourci');
  await dropOn(tile('r_t3'), [dropped]);
  await sleep(250);
  check(moves.length === 1 && moves[0].dest_dir === `${HOME}/Documents` && moves[0].paths[0] === dropped && !moves[0].copy, 'fichier lâché sur un dossier : rangé dedans');
  await page.unroute('**/api/fs/move');

  open = false;
  windows.groupes[0].n = 1; windows.groupes[0].fenetres.pop(); windows.sig = 's2';
  await page.evaluate(() => loadWindows());
  await page.click(tile('r_t1'));
  await sleep(350);
  check(acts.length === 3 && starts.length === 4 && starts[3].id === 'firefox.desktop', 'appli fermée entre-temps : le clic la relance');
  for (const u of ['**/api/raccourcis', '**/api/fenetres', '**/api/fenetres/action', '**/api/apps/lancer']) await page.unroute(u);
  await page.evaluate(async () => { D.win = { dispo: false, groupes: [], map: {}, sig: 'x' }; D.sc = []; await loadShortcuts(); await loadWindows(); });

  // ── fenêtre principale ──
  console.log('— volet : à gauche de l\'écran');
  const boxes = () => page.evaluate(() => {
    const r = (q) => { const b = document.querySelector(q).getBoundingClientRect(); return { l: Math.round(b.left), r: Math.round(b.right) }; };
    return { side: r('.side'), rail: r('#rail'), icons: r('#icons'), w: innerWidth };
  });
  const right = await boxes();
  await page.evaluate(() => { D.b.volet_cote = 'gauche'; applyVolet(); });
  await sleep(350);
  const left = await boxes();
  check(left.side.l < 80 && Math.abs(left.rail.l - left.side.l) <= 2 && left.icons.l >= left.side.r && left.icons.r > right.icons.r,
    `volet à gauche : raccourcis contre le bord, icônes décalées à sa droite (volet ${left.side.l}–${left.side.r}, icônes ${left.icons.l}–${left.icons.r})`);
  check(right.side.r > right.w - 80 && right.icons.r <= right.side.l, 'à droite : comme avant');
  await page.evaluate(() => { D.b.volet_cote = 'droite'; applyVolet(); });

  console.log('— volet : même discussion que la fenêtre principale');
  await post('/api/settings', { think: true });
  await post('/api/bureau/conv/nouvelle', {});
  await page.evaluate(() => loadConv().then(renderConv));
  await ask('Bonjour, fais-moi un tableau');
  const nMsgs = () => page.evaluate(() => D.conv.messages.length);
  check(await page.locator('#vMsgs details.seg-think').count() === 1 && (await page.innerText('#vMsgs .acts .stats')).includes('qwen'), 'réflexion du modèle repliée, modèle et vitesse affichés');
  check(await page.locator('#vMsgs [data-act="regen"]').count() === 1 && await page.locator('#vMsgs [data-act="toXlsx"]').count() === 1
    && await page.locator('#vMsgs [data-act="toDocx"]').count() === 1, 'boutons Régénérer, Word et Excel (la réponse contient un tableau)');
  const before = await nMsgs();
  await page.click('#vMsgs [data-act="regen"]');
  await sleep(200); await idle(); await sleep(200);
  check(await nMsgs() === before && await page.locator('#vMsgs .a').count() === 1 && await page.locator('#vMsgs .md table').count() === 1, 'Régénérer : la réponse est refaite, pas ajoutée');
  await page.reload();
  await page.waitForSelector('#vIn');
  await page.waitForFunction(() => D.conv && D.items.length);
  check(await page.locator('#vMsgs details.seg-think').count() === 1 && await page.locator('#vMsgs [data-act="regen"]').count() === 1, 'identique après rechargement (même code d\'affichage)');
  await post('/api/settings', { think: false });

  console.log('— bureau : couper, coller');
  fs.writeFileSync(`${DESK}/à déplacer.txt`, 'x');
  await page.evaluate(() => loadElements());
  await page.waitForSelector('#icons .dicon[title$="à déplacer.txt"]');
  await page.click('#icons .dicon[title$="à déplacer.txt"]');
  await page.keyboard.press('Control+x');
  await sleep(300);
  check(await page.locator('#icons .dicon.cut').count() === 1, 'Ctrl+X sur le bureau : l\'icône est marquée « coupée »');
  await page.click('#icons .dicon[title$="Vrai dossier"]');
  await page.keyboard.press('Control+v');
  await sleep(600);
  check(fs.existsSync(`${DESK}/Vrai dossier/à déplacer.txt`) && !fs.existsSync(`${DESK}/à déplacer.txt`), 'Ctrl+V sur un dossier choisi : le fichier y est déplacé');
  check(await page.locator('#icons .dicon.cut').count() === 0 && await page.locator('#icons .dicon[title$="à déplacer.txt"]').count() === 0, 'l\'icône quitte le bureau');

  console.log('— bureau : archives');
  require('child_process').execFileSync('python3', ['-c', `
import zipfile
with zipfile.ZipFile("${DESK}/Photos.zip", "w") as z:
    z.writestr("Photos/a.jpg", "a"); z.writestr("Photos/b.jpg", "b")
`]);
  await page.evaluate(() => loadElements());
  await page.waitForSelector('#icons .dicon[title$="Photos.zip"]');
  await page.click('#icons .dicon[title$="Photos.zip"]', { button: 'right' });
  const dz = await page.innerText('.menu');
  check(dz.includes('Extraire ici') && dz.includes('Compresser') && dz.includes('Propriétés'), 'clic droit sur une archive du bureau : Extraire ici, Compresser, Propriétés');
  await page.keyboard.press('Escape');
  await page.dblclick('#icons .dicon[title$="Photos.zip"]');
  await page.waitForSelector('.modal .arc-row', { timeout: 5000 }).catch(() => {});
  check(await page.locator('.modal .arc-row').count() === 3 && (await page.innerText('.modal .arc-list')).includes('Photos'), 'double-clic : le contenu (dossier compris)');
  await page.click('.modal [data-ar="ici"]');
  await page.waitForSelector('#icons .dicon[title$="/Photos"]', { timeout: 8000 }).catch(() => {});
  check(fs.existsSync(`${DESK}/Photos/b.jpg`) && await page.locator('#icons .dicon[title$="/Photos"]').count() === 1, '« Extraire ici » : le dossier apparaît sur le bureau');

  console.log('— bureau : versions précédentes d\'un fichier');
  const vfile = `${DESK}/journal.txt`;
  fs.writeFileSync(vfile, 'premier jet');
  await post('/api/fs/write', { path: vfile, content: 'deuxième jet' });
  await post('/api/fs/write', { path: vfile, content: 'troisième jet' });
  await page.evaluate((p) => showVersions(p, () => { window.__revenu = true; }), vfile);
  await page.waitForSelector('.ver[data-id]');
  check(await page.locator('.ver[data-id]').count() === 2 && await page.locator('.ver.cur').count() === 1, 'deux anciennes versions listées, plus la version actuelle');
  await page.click('.ver[data-id] >> nth=1 >> [data-ver="voir"]');
  await page.waitForSelector('.modal pre.pv-text', { timeout: 4000 }).catch(() => {});
  check((await page.innerText('.modal pre.pv-text').catch(() => '')) === 'premier jet', 'aperçu d\'une ancienne version');
  await page.click('.ver[data-id] >> nth=1 >> [data-ver="remettre"]');
  await page.click('.modal:last-of-type .btn.primary:has-text("Remettre cette version")');
  await page.waitForFunction(() => window.__revenu, null, { timeout: 5000 }).catch(() => {});
  check(fs.readFileSync(vfile, 'utf8') === 'premier jet', 'Remettre : le fichier retrouve son ancien contenu');
  const again = await page.evaluate((p) => api(`/api/fs/versions?path=${encodeURIComponent(p)}`), vfile);
  check(again.versions.length === 3, 'l\'état remplacé est devenu une version lui aussi');

  console.log('— fenêtre principale');
  const main = watch(await ctx.newPage());
  await main.goto(`${BASE}/#/chat`);
  await main.waitForSelector('#cInput');
  const icon = await main.evaluate(() => document.querySelector('#nav [data-view="prompts"] svg path').getAttribute('d') === ICONS.prompt);
  check(icon, 'icône de l\'onglet Prompts');
  await main.evaluate(() => post('/api/settings', { ollama_url: 'http://127.0.0.1:9' }));
  await main.fill('#cInput', 'question pendant une panne');
  await main.press('#cInput', 'Enter');
  await main.waitForFunction(() => !S.chat.busy && S.chat.conv, null, { timeout: 20000 });
  await sleep(400);
  check(await main.locator('#cInner .err-box [data-act="retry"]').count() === 1 && (await main.innerText('#cInner')).includes('injoignable'), 'l\'erreur reste affichée, avec « Réessayer »');
  check(await main.locator('#statusPill.bad').count() === 1, 'la pastille passe au rouge');
  await main.evaluate((u) => post('/api/settings', { ollama_url: u }), OLLAMA);
  await main.click('#cInner .err-box [data-act="retry"]');
  await sleep(200);
  await main.waitForFunction(() => !S.chat.busy, null, { timeout: 20000 });
  await sleep(300);
  check(await main.locator('#cInner .err-box').count() === 0 && await main.locator('#cInner .md').count() === 1, 'Réessayer : la réponse arrive');
  await main.route('**/api/fs/search?**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ base: HOME, query: 'contrat', results: [], tronque: true, incomplet: 'temps', delai: 12 }) }));
  await main.evaluate(() => go('files'));
  await main.waitForSelector('#fSearch');
  await main.fill('#fSearch', 'contrat');
  await main.press('#fSearch', 'Enter');
  await main.waitForSelector('#fList .search-cut', { timeout: 4000 }).catch(() => {});
  check(await main.locator('#fList .search-cut').count() === 1 && (await main.innerText('#fList')).includes('pas pu tout parcourir'), 'recherche arrêtée par le temps : annoncée');
  await main.unroute('**/api/fs/search?**');
  await main.evaluate(async () => { S.index = await api('/api/index'); });
  await main.fill('#fSearch', '');
  await main.type('#fSearch', 'journ', { delay: 30 });
  await main.waitForFunction(() => F.search && F.search.query === 'journ', null, { timeout: 4000 }).catch(() => {});
  check(await main.evaluate(() => !!(F.search && F.search.index && F.search.results.some((e) => e.name === 'journal.txt'))), 'recherche au fil de la frappe, sans appuyer sur Entrée (index)');
  // couper / coller au clavier, et glisser = déplacer
  const dnd = `${HOME}/Documents/dnd`;
  fs.mkdirSync(`${dnd}/Dest`, { recursive: true });
  fs.mkdirSync(`${dnd}/Ailleurs`, { recursive: true });
  fs.writeFileSync(`${dnd}/a.txt`, 'a'); fs.writeFileSync(`${dnd}/b.txt`, 'b'); fs.writeFileSync(`${dnd}/Ailleurs/venu.txt`, 'v');
  const rowOf = (name) => `#fList .frow:has(.name span:text-is("${name}"))`;
  const openIn = async (dir) => { await main.evaluate((d) => { $('#fSearch').value = ''; F.search = null; return openDir(d); }, dir); await sleep(350); };
  await openIn(dnd);
  await main.click(rowOf('a.txt'));
  await main.keyboard.press('Control+x');
  await sleep(300);
  check(await main.locator(`${rowOf('a.txt')}.cut`).count() === 1 && fs.existsSync(`${dnd}/a.txt`), 'Ctrl+X : le fichier est marqué « coupé », rien ne bouge encore');
  await openIn(`${dnd}/Dest`);
  await main.focus('#fList');
  await main.keyboard.press('Control+v');
  await sleep(500);
  check(fs.existsSync(`${dnd}/Dest/a.txt`) && !fs.existsSync(`${dnd}/a.txt`) && await main.locator(rowOf('a.txt')).count() === 1, 'Ctrl+V dans un autre dossier : le fichier y est déplacé et s\'affiche');
  await openIn(dnd);
  await main.click(rowOf('b.txt'));
  await main.keyboard.press('Control+c');
  await sleep(250);
  await main.click(rowOf('Dest'), { button: 'right' });
  await main.click('.menu button:has-text("Coller dans ce dossier")');
  await sleep(500);
  check(fs.existsSync(`${dnd}/Dest/b.txt`) && fs.existsSync(`${dnd}/b.txt`), 'Ctrl+C puis « Coller dans ce dossier » : copié, l\'original reste');
  const dropPaths = (sel, paths, opts = {}) => main.evaluate(([q, list, o]) => {
    const dt = new DataTransfer();
    dt.setData('text/uri-list', list.map((p) => `file://${p.split('/').map(encodeURIComponent).join('/')}`).join('\r\n'));
    const el = document.querySelector(q) || document.querySelector('#fWrap');
    const r = el.getBoundingClientRect();
    for (const t of ['dragenter', 'dragover', 'drop']) el.dispatchEvent(new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt, clientX: r.x + 40, clientY: r.y + r.height / 2, ...o }));
  }, [sel, paths, opts]);
  const destRow = await main.evaluate(() => { const i = curList().findIndex((e) => e.name === 'Dest'); return `#fList .frow[data-i="${i}"]`; });
  await dropPaths(destRow, [`${dnd}/Ailleurs/venu.txt`]);
  await sleep(500);
  check(fs.existsSync(`${dnd}/Dest/venu.txt`) && !fs.existsSync(`${dnd}/Ailleurs/venu.txt`), 'fichier glissé depuis une autre appli sur un dossier : déplacé, pas copié');
  await dropPaths('#fList', [`${dnd}/Dest/venu.txt`]);
  await sleep(500);
  check(fs.existsSync(`${dnd}/venu.txt`) && !fs.existsSync(`${dnd}/Dest/venu.txt`), 'glissé dans le dossier affiché (hors d\'un sous-dossier) : déplacé ici');
  await dropPaths(destRow, [`${dnd}/venu.txt`], { ctrlKey: true });
  await sleep(500);
  check(fs.existsSync(`${dnd}/Dest/venu.txt`) && fs.existsSync(`${dnd}/venu.txt`), 'avec Ctrl : copié');
  check(await main.locator('.drop-overlay').count() === 0, 'le bandeau de dépôt disparaît une fois le fichier lâché');

  // archives : double-clic, contenu, extraction suivie en bas à droite
  console.log('— fenêtre principale : archives, tâches de fond, propriétés, navigation');
  const arc = `${HOME}/Documents/arc-ui`;
  fs.rmSync(arc, { recursive: true, force: true });
  fs.mkdirSync(arc, { recursive: true });
  require('child_process').execFileSync('python3', ['-c', `
import zipfile
with zipfile.ZipFile("${arc}/Manga.zip", "w") as z:
    for i in range(3): z.writestr(f"Tome {i + 1}.cbz", "x" * 1000)
`]);
  await openIn(arc);
  await main.dblclick(rowOf('Manga.zip'));
  await main.waitForSelector('.modal .arc-row', { timeout: 5000 }).catch(() => {});
  check(await main.locator('.modal .arc-row').count() === 3 && (await main.innerText('.modal')).includes('3 fichiers') && (await main.innerText('.modal')).includes('« Manga »'),
    'double-clic sur un zip : son contenu, et le dossier qui sera créé');
  await main.click('.modal [data-ar="ici"]');
  await main.waitForFunction(() => TK.list.some((t) => t.genre === 'extraction' && t.etat === 'finie'), null, { timeout: 8000 }).catch(() => {});
  await sleep(500);
  check(fs.existsSync(`${arc}/Manga/Tome 3.cbz`) && await main.locator('#taches .tache.finie').count() === 1 && await main.locator(rowOf('Manga')).count() === 1,
    '« Extraire ici » : tâche suivie en bas à droite, le dossier apparaît dans la liste');
  await main.click('#taches [data-tka="fermer"]');
  await main.click(rowOf('Manga'), { button: 'right' });
  const amenu = await main.innerText('.menu');
  check(amenu.includes('Compresser') && amenu.includes('Propriétés') && amenu.includes('Ouvrir un terminal ici'), 'menu d\'un dossier : Compresser, Propriétés, terminal');
  await main.keyboard.press('Escape');
  await main.click(rowOf('Manga.zip'), { button: 'right' });
  const zmenu = await main.innerText('.menu');
  check(zmenu.includes('Extraire ici') && zmenu.includes('Extraire vers') && zmenu.includes('Ouvrir avec'), 'menu d\'une archive : Extraire ici, Extraire vers…, Ouvrir avec…');
  await main.keyboard.press('Escape');
  // grosse copie : barre de progression, Annuler
  const fd = fs.openSync(`${arc}/gros.iso`, 'w'); fs.ftruncateSync(fd, 1024 ** 3); fs.closeSync(fd);
  fs.mkdirSync(`${arc}/Copies`);
  await main.evaluate(([a]) => moveItems([`${a}/gros.iso`], `${a}/Copies`, true), [arc]);
  await main.waitForSelector('#taches .tache.run', { timeout: 4000 }).catch(() => {});
  check(await main.locator('#taches .tache.run .tk-bar').count() === 1 && (await main.innerText('#taches')).includes('Copie de « gros.iso »'), 'grosse copie : barre de progression en bas à droite');
  await main.click('#taches [data-tka="annuler"]');
  await main.waitForFunction(() => TK.list.some((t) => t.etat === 'annulee'), null, { timeout: 8000 }).catch(() => {});
  await sleep(300);
  check(!fs.existsSync(`${arc}/Copies/gros.iso`) && (await main.innerText('#taches')).includes('Annulé'), 'Annuler : la copie s\'arrête et ne laisse rien');
  await main.click('#taches [data-tka="fermer"]');
  fs.unlinkSync(`${arc}/gros.iso`);
  // propriétés
  await main.evaluate(() => loadDir());
  await sleep(300);
  await main.click(rowOf('Manga'));
  await main.keyboard.press('Alt+Enter');
  await main.waitForSelector('.modal dl.props', { timeout: 5000 }).catch(() => {});
  const props = (await main.innerText('.modal').catch(() => '')).replace(/[\u202f\u00a0]/g, ' ');
  check(props.includes('3 fichiers') && props.includes('3 000 octets') && await main.locator('.modal .perm-grid input').count() === 9, `Alt+Entrée : propriétés (taille du dossier, droits)${props.includes('3 fichiers') ? '' : ` — ${props.slice(0, 300)}`}`);
  await main.keyboard.press('Escape');
  fs.writeFileSync(`${arc}/lancer.sh`, '#!/bin/sh\n'); fs.chmodSync(`${arc}/lancer.sh`, 0o644);
  await main.evaluate((p) => showProperties([p]), `${arc}/lancer.sh`);
  await main.waitForSelector('.modal [data-exe]', { state: 'attached' });
  await main.click('.modal label.switch:has([data-exe])');
  await sleep(400);
  check((fs.statSync(`${arc}/lancer.sh`).mode & 0o111) === 0o111, '« Autoriser l\'exécution » rend le fichier exécutable');
  await main.keyboard.press('Escape');
  // navigation : précédent / suivant, Alt+↑, barre d'adresse
  await openIn(arc);
  await main.dblclick(rowOf('Manga'));
  await sleep(400);
  await main.keyboard.press('Alt+ArrowLeft');
  await sleep(400);
  const backAt = await main.evaluate(() => F.path);
  await main.click('#fFwd');
  await sleep(400);
  const fwdAt = await main.evaluate(() => F.path);
  await main.keyboard.press('Alt+ArrowUp');
  await sleep(400);
  check(backAt === arc && fwdAt === `${arc}/Manga` && await main.evaluate(() => F.path) === arc && await main.evaluate(() => [...F.sel][0]) === `${arc}/Manga`,
    'précédent (Alt+←), suivant, dossier parent (Alt+↑) qui garde choisi le dossier d\'où l\'on vient');
  await main.keyboard.press('Control+l');
  await main.keyboard.type('~/Documents/arc-ui/Manga');
  await main.keyboard.press('Enter');
  await sleep(500);
  check(await main.evaluate(() => F.path) === `${arc}/Manga`, 'Ctrl+L : taper un chemin (avec ~) et y aller');
  await main.keyboard.press('Control+l');
  await main.keyboard.type('~/Documents/arc-ui/lancer.sh');
  await main.keyboard.press('Enter');
  await sleep(500);
  check(await main.evaluate(() => [F.path, [...F.sel][0]]).then(([p, s]) => p === arc && s === `${arc}/lancer.sh`), 'taper le chemin d\'un fichier : son dossier, le fichier choisi');
  // compresser depuis le menu
  await main.click(rowOf('Manga'), { button: 'right' });
  await main.click('.menu button:has-text("Compresser")');
  await main.waitForSelector('.modal [data-cn]');
  await main.fill('.modal [data-cn]', 'Envoi');
  await main.click('.modal [data-cok]');
  await main.waitForFunction(() => TK.list.some((t) => t.genre === 'compression' && t.etat === 'finie'), null, { timeout: 8000 }).catch(() => {});
  await main.waitForSelector(rowOf('Envoi.zip'), { timeout: 4000 }).catch(() => {});
  const dbgC = await main.evaluate(() => JSON.stringify({ p: F.path, s: !!F.search, l: curList().map((e) => e.name), t: TK.list.map((t) => [t.genre, t.etat, t.dossier]) }));
  check(fs.existsSync(`${arc}/Envoi.zip`) && await main.locator(rowOf('Envoi.zip')).count() === 1, `« Compresser… » : Envoi.zip créé et affiché${fs.existsSync(`${arc}/Envoi.zip`) && !(await main.locator(rowOf('Envoi.zip')).count()) ? ` ${dbgC}` : ''}`);

  await main.evaluate(() => go('settings'));
  await main.waitForSelector('#stIndex [data-ix="refaire"]', { timeout: 5000 }).catch(() => {});
  check(/fichiers et \d+ dossiers retenus/.test(await main.innerText('#stIndex')) && await main.locator('[data-act="rollback"]').count() === 1, 'Réglages : état de l\'index, bouton « Revenir à la version précédente »');
  await main.click('[data-act="rollback"]');
  await main.waitForSelector('.modal [data-r="go"]', { timeout: 5000 }).catch(() => {});
  check(/Revenir à Archiviste \d/.test(await main.innerText('.modal').catch(() => '')), 'la version précédente est proposée, avec ce qui est gardé');
  await main.keyboard.press('Escape');
  await main.evaluate(() => go('chat'));
  await main.waitForSelector('#cInner .md');
  check(await main.locator('#cInner [data-act="regen"]').count() === 1 && await main.locator('#cInner [data-act="saveMsg"]').count() === 1 && await main.locator('#cInner .m-bot .who').count() >= 1,
    'discussion de la fenêtre principale : mêmes boutons, son habillage');
  await main.close();

  check(jsErrors.length === 0, `aucune erreur JavaScript${jsErrors.length ? ` (${jsErrors.slice(0, 3).join(' | ')})` : ''}`);
  await post('/api/settings', { ollama_url: OLLAMA });
  await browser.close();
}

main().then(() => {
  console.log(`\n${fails ? `${fails} ÉCHEC(S)` : 'TOUT EST BON'}`);
  process.exit(fails ? 1 : 0);
}).catch((e) => {
  console.error(`\nTest d'interface interrompu : ${e.stack || e}`);
  process.exit(1);
});
