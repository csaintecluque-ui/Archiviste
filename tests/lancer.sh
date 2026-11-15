#!/usr/bin/env bash
# Lance les tests de bout en bout : faux Ollama + serveur Archiviste dans un dossier personnel jetable.
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RACINE="$(dirname "$ICI")"
H=/tmp/archi-home
rm -rf "$H" && mkdir -p "$H/Téléchargements" "$H/Documents"
(cd "$H/Téléchargements" && echo facture > facture_edf_mars.pdf && echo img > vacances.jpg && echo "note perso" > note.txt \
  && echo x > setup.deb && printf 'ligne1\nligne2\n' > liste.md && cp vacances.jpg copie_vacances.jpg)
python3 "$ICI/mock_ollama.py" 11500 & MOCK=$!
rm -f /tmp/archi-install.log
# mises à jour : faux dépôt de versions (servi par le faux Ollama), faux pkexec et faux installateur
HOME="$H" XDG_DATA_HOME= XDG_CACHE_HOME= ARCHIVISTE_PORT=8766 ARCHIVISTE_SANS_MAJ=1 no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost \
  ARCHIVISTE_MAJ_API=http://127.0.0.1:11500/maj/releases ARCHIVISTE_MAJ_DEPOT=http://127.0.0.1:11500/maj/ \
  ARCHIVISTE_PKEXEC="$ICI/faux_pkexec.sh" ARCHIVISTE_MAJ_HELPER="$ICI/faux_installeur.sh" \
  python3 "$RACINE/archiviste.py" & SRV=$!
trap 'kill $MOCK $SRV 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do python3 -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8766/', timeout=1)" 2>/dev/null && break; sleep 0.25; done
python3 "$ICI/test_api.py"
HOME="$H" XDG_DATA_HOME= ARCHIVISTE_DATA="$H/.unites" python3 "$ICI/test_unites.py"

# Tests d'interface (volet du bureau, fenêtre principale) dans Chrome sans affichage.
# Il faut Node.js et, une fois :  npm install --prefix tests
if (cd "$ICI" && node -e "try { require('playwright-core') } catch (e) { require('playwright') }" 2>/dev/null); then
  (cd "$ICI" && ARCHI_HOME="$H" node test_interface.cjs)
elif [ -n "${CI:-}" ]; then
  echo "Tests d'interface impossibles : playwright-core est absent (npm install --prefix tests)." >&2
  exit 1
else
  echo "(tests d'interface non lancés : installe Node.js puis « npm install --prefix tests »)"
fi
