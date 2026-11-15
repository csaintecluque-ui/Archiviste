#!/bin/sh
# Remplace /usr/lib/archiviste/installer-maj pendant les tests : note le paquet qu'on lui demande d'installer.
echo "$1" >> "${ARCHI_INSTALL_LOG:-/tmp/archi-install.log}"
exit 0
