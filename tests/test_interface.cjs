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
  const windows = { dispo: true, sig: 's1', groupes: [
    { cle: 'app:firefox.desktop', app: 'firefox.desktop', nom: 'Firefox', icone: 'firefox', n: 2, reduit: false, devant: true, titres: ['Accueil', 'Autre onglet'] },
    { cle: 'app:vlc.desktop', app: 'vlc.desktop', nom: 'VLC', icone: 'vlc', n: 1, reduit: true, devant: false, titres: ['Film'] },
  ] };
  const acts = [];
  const starts = [];
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
  await sleep(250);
  check(acts.length === 1 && acts[0].cle === 'app:firefox.desktop' && acts[0].action === 'basculer' && starts.length === 0, 'clic sur une appli ouverte : sa fenêtre est ramenée ou réduite, rien n\'est relancé');
  await page.click(tile('r_t2'));
  await sleep(250);
  check(starts.length === 1 && starts[0].id === 'org.gnome.Terminal.desktop' && acts.length === 1, 'clic sur une appli fermée : elle est lancée');
  await page.click('#sc [data-run="app:vlc.desktop"]');
  await sleep(250);
  check(acts.length === 2 && acts[1].cle === 'app:vlc.desktop', 'clic sur une appli sans raccourci : sa fenêtre revient');
  open = false;
  await page.click(tile('r_t1'));
  await sleep(350);
  check(acts.length === 3 && starts.length === 2 && starts[1].id === 'firefox.desktop', 'appli fermée entre-temps : le clic la relance');
  await page.click(tile('r_t1'), { button: 'right' });
  const menu = await page.innerText('.menu');
  check(menu.includes('Réduire') && menu.includes('Nouvelle fenêtre') && menu.includes('Fermer les 2 fenêtres'), 'clic droit : réduire, nouvelle fenêtre, fermer');
  await page.keyboard.press('Escape');
  for (const u of ['**/api/raccourcis', '**/api/fenetres', '**/api/fenetres/action', '**/api/apps/lancer']) await page.unroute(u);
  await page.evaluate(async () => { D.win = { dispo: false, groupes: [], map: {}, sig: 'x' }; D.sc = []; await loadShortcuts(); await loadWindows(); });

  // ── fenêtre principale ──
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
