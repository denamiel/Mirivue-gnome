#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export LANGUAGE=fr LC_ALL=C.UTF-8
export GSK_RENDERER=cairo
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
export XDG_CONFIG_HOME="$test_root/config" XDG_STATE_HOME="$test_root/state" XDG_CACHE_HOME="$test_root/cache" XDG_DATA_HOME="$test_root/data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
/usr/bin/python3 packaging/check_release.py
/usr/bin/python3 -m compileall -q mirivue_gtk4 tests packaging
/usr/bin/python3 -m mirivue_gtk4 --check-dependencies
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m mirivue_gtk4 --smoke-test
/usr/bin/python3 - <<'PY'
import subprocess
subprocess.run(['/usr/bin/python3', '-m', 'mirivue_gtk4', '--window-smoke-test'], check=True, timeout=35)
PY
