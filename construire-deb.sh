#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Construit le paquet d'installation :  dist/archiviste_<version>_all.deb
#  Nécessite : dpkg-deb, rsvg-convert (librsvg2-bin)
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' archiviste.py)"
WORK="$(mktemp -d)"
PKG="$WORK/archiviste_${VERSION}_all"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$PKG/DEBIAN" "$PKG/opt/archiviste" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/doc/archiviste" "$PKG/usr/share/icons/hicolor/scalable/apps"

# Application
cp archiviste.py fenetre.py indexeur.py archives.py "$PKG/opt/archiviste/"
cp -r static "$PKG/opt/archiviste/static"
find "$PKG/opt/archiviste" -type d -exec chmod 755 {} +
find "$PKG/opt/archiviste" -type f -exec chmod 644 {} +
chmod 755 "$PKG/opt/archiviste/archiviste.py" "$PKG/opt/archiviste/fenetre.py"

# Commandes
cat > "$PKG/usr/bin/archiviste" <<'EOF'
#!/bin/sh
# Archiviste dans sa propre fenêtre
exec /usr/bin/python3 /opt/archiviste/fenetre.py "$@"
EOF
cat > "$PKG/usr/bin/archiviste-serveur" <<'EOF'
#!/bin/sh
# Archiviste sans fenêtre, à ouvrir dans un navigateur : http://127.0.0.1:8765
exec /usr/bin/python3 /opt/archiviste/archiviste.py "$@"
EOF
chmod 755 "$PKG/usr/bin/archiviste" "$PKG/usr/bin/archiviste-serveur"

# Installation des mises à jour depuis l'appli (mot de passe demandé par la fenêtre de Mint)
mkdir -p "$PKG/usr/lib/archiviste" "$PKG/usr/share/polkit-1/actions"
install -m 755 paquet/installer-maj "$PKG/usr/lib/archiviste/installer-maj"
install -m 644 paquet/fr.csc.archiviste.policy "$PKG/usr/share/polkit-1/actions/fr.csc.archiviste.policy"

# Raccourci du menu
cat > "$PKG/usr/share/applications/fr.csc.Archiviste.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Archiviste
GenericName=Fichiers et IA locale
Comment=Gérer, trier et modifier tes fichiers avec ton IA locale (Ollama)
Exec=archiviste %U
Icon=archiviste
Terminal=false
Categories=Utility;FileManager;
MimeType=inode/directory;
Keywords=fichiers;tri;ia;ollama;qwen;agents;prompts;
StartupWMClass=archiviste
StartupNotify=true
SingleMainWindow=true
Actions=demander;bureau;

[Desktop Action demander]
Name=Demander à l'Archiviste
Exec=archiviste --demander

[Desktop Action bureau]
Name=Afficher le bureau Archiviste
Exec=archiviste --bureau
EOF

# Icônes (logo Anamnesis · CSC) : petite version jusqu'à 48 px, sceau complet au-delà
cp static/icon.svg "$PKG/usr/share/icons/hicolor/scalable/apps/archiviste.svg"
for s in 16 24 32 48 64 128 256 512; do
  d="$PKG/usr/share/icons/hicolor/${s}x${s}/apps"; mkdir -p "$d"
  if   [ "$s" -le 16 ]; then src=static/logo-16.svg
  elif [ "$s" -le 48 ]; then src=static/favicon.svg
  else src=static/icon.svg; fi
  rsvg-convert -w "$s" -h "$s" "$src" -o "$d/archiviste.png"
done

# Documentation
cp README.md "$PKG/usr/share/doc/archiviste/"
cp NOUVEAUTES.md "$PKG/usr/share/doc/archiviste/"
printf 'Archiviste — Cyril SAINTE-CLUQUE (Anamnesis · CSC).\nhttps://github.com/csaintecluque-ui/Archiviste\n' > "$PKG/usr/share/doc/archiviste/copyright"

# Contrôle du paquet
SIZE="$(du -sk "$PKG" --exclude=DEBIAN | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: archiviste
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, poppler-utils, xdg-utils
Recommends: gir1.2-wnck-3.0
Installed-Size: $SIZE
Maintainer: Cyril SAINTE-CLUQUE <csaintecluque-ui@users.noreply.github.com>
Homepage: https://github.com/csaintecluque-ui/Archiviste
Description: Gestionnaire de fichiers et assistant IA local (Ollama)
 Archiviste permet de parcourir, trier, modifier et ranger ses fichiers,
 de discuter avec une IA locale (Ollama, qwen3.5:4b par défaut), de créer
 des agents qui agissent sur les fichiers avec validation, et d'enregistrer
 des prompts. Tout reste sur l'ordinateur.
EOF
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  update-desktop-database -q /usr/share/applications 2>/dev/null || true
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
cat > "$PKG/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
update-desktop-database -q /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"

mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$PKG" "dist/archiviste_${VERSION}_all.deb" >/dev/null
echo "✓ dist/archiviste_${VERSION}_all.deb"
