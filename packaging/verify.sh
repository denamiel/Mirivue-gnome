#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export LANGUAGE=fr LC_ALL=C.UTF-8
export GSK_RENDERER=cairo
export PYTHONFAULTHANDLER=1
test_root="$(mktemp -d)"
cleanup() {
    # Session services can finish writing after the private bus exits.
    for attempt in 1 2 3; do
        if rm -rf -- "$test_root"; then return; fi
        sleep .1
    done
}
trap cleanup EXIT
export XDG_CONFIG_HOME="$test_root/config" XDG_STATE_HOME="$test_root/state" XDG_CACHE_HOME="$test_root/cache" XDG_DATA_HOME="$test_root/data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
# GVfs daemons must inherit the same isolated XDG directories as the tests.
# A bus started before these exports would inspect a different trash directory.
run_native_checks() {
/usr/bin/python3 packaging/check_release.py
/usr/bin/python3 -m compileall -q mirivue_gtk4 tests packaging
/usr/bin/python3 -m mirivue_gtk4 --check-dependencies
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m mirivue_gtk4 --smoke-test
/usr/bin/python3 - <<'PY'
import subprocess
subprocess.run(['/usr/bin/python3', '-m', 'mirivue_gtk4', '--window-smoke-test'], check=True, timeout=35)
PY
}
export -f run_native_checks
if [[ "${MIRIVUE_TEST_BUS_ISOLATED:-}" == 1 ]]; then
    run_native_checks
else
    dbus-run-session -- bash -euo pipefail -c run_native_checks
fi
