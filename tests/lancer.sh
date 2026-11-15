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
HOME="$H" XDG_DATA_HOME= ARCHIVISTE_PORT=8766 ARCHIVISTE_SANS_MAJ=1 python3 "$RACINE/archiviste.py" & SRV=$!
trap 'kill $MOCK $SRV 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do python3 -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8766/', timeout=1)" 2>/dev/null && break; sleep 0.25; done
python3 "$ICI/test_api.py"
