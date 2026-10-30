#!/usr/bin/env bash
# Install and verify the maintained guides without touching application settings.
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:?Usage: install_docs.sh DESTINATION}"
documents=(
  'README.md'
  'CHANGELOG.md'
  'BETA-1.0.0.md'
  'NATIF-GNOME-0.6.23.md'
  'NATIF-GNOME-0.6.24.md'
  'STABILISATION-GNOME.md'
  'packaging/PUBLICATION.md'
)
for document in "${documents[@]}"; do
  install -Dm644 "$source_root/$document" "$destination/$document"
  cmp -- "$source_root/$document" "$destination/$document"
done
printf '%s guides installés et vérifiés dans %s\n' "${#documents[@]}" "$destination"
