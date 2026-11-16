"""Cloud-only diagnosis of COPR 11330722; never modifies application behavior.

Run from the repository root under Xvfb and a private D-Bus session.
The original suite keeps its 6s limit. Focused trials record that checkpoint
and continue the SAME wait to 30s, distinguishing a late update from a lost one.
Only synthetic files in TemporaryDirectory are touched.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import subprocess
import threading
import time
import traceback
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import test_native_parity as support
import test_native_file_behaviors as behaviors
from mirivue_gtk4.pane import Pane
from mirivue_gtk4.backend import MediaService, State
from mirivue_gtk4.core import metadata
from gi.repository import GLib

TARGET = "test_local_folder_updates_for_external_create_edit_rename_and_delete"
events = deque(maxlen=4000)
started = time.monotonic()
active_case = None
extended = False
timeouts = []
outcomes = []


def record(kind, **data):
    events.append(dict(t=round(time.monotonic() - started, 6),
                       thread=threading.current_thread().name, kind=kind, **data))


def signature(path):
    try:
        return metadata.fingerprint(Path(path))
    except OSError as error:
        return type(error).__name__


def row_data(row):
    return None if row is None else dict(
        path=str(row.path), size=row.sort_values[1],
        signature=row.file_signature, error=row.error)


def snapshot(pane):
    return dict(
        generation=pane.generation, closed=pane.closed,
        changed=sorted(pane.changed), change_timer=pane.change_timer,
        monitor_cancelled=pane.monitor.is_cancelled() if pane.monitor else None,
        rows=[dict(model=row_data(item.row), disk=signature(item.path))
              for item in list(pane.items.values())],
        futures=[dict(done=f.done(), cancelled=f.cancelled(),
                      error=str(f.exception()) if f.done() and not f.cancelled() else None)
                 for f in pane.futures])


def state_snapshot():
    if active_case is None or not hasattr(active_case, "window"):
        return None
    return snapshot(active_case.window.active)


original_until = support.until


def diagnosed_until(condition, seconds=6):
    caller = sys._getframe(1)
    origin = f"{Path(caller.f_code.co_filename).name}:{caller.f_lineno}"
    begin = time.monotonic()
    try:
        result = original_until(condition, seconds)
        record("wait_ok", origin=origin, elapsed=time.monotonic() - begin)
        return result
    except AssertionError as error:
        if str(error) != "Native GTK operation did not finish":
            raise
        checkpoint = dict(origin=origin, elapsed=time.monotonic() - begin,
                          state=state_snapshot())
        timeouts.append(checkpoint)
        record("deadline_6s", **checkpoint)
        for event in list(events)[-100:]:
            print("DIAGNOSTIC_CHECKPOINT_TRACE " + json.dumps(event, default=str), flush=True)
        # Preserve the original suite's assertion. Only isolated trials extend.
        if not extended or seconds != 6:
            raise
        try:
            result = original_until(condition, 24)
            record("late_success", origin=origin,
                   elapsed=time.monotonic() - begin, state=state_snapshot())
            return result
        except AssertionError:
            record("deadline_30s", origin=origin,
                   elapsed=time.monotonic() - begin, state=state_snapshot())
            raise


def instrument():
    original_event = Pane.changed_event
    original_flush = Pane.flush_changes
    original_enrich = Pane.enrich
    original_enriched = Pane.enriched
    original_basic = metadata.basic_entry
    original_read = State.read
    original_put = State.put
    original_inspect = MediaService.inspect

    def event(pane, monitor, file, other, kind, generation):
        record("monitor", event=str(kind), generation=generation,
               current_generation=pane.generation,
               file=file.get_path() if file else None,
               other=other.get_path() if other else None)
        return original_event(pane, monitor, file, other, kind, generation)

    def flush(pane):
        record("flush_before", state=snapshot(pane))
        result = original_flush(pane)
        record("flush_after", state=snapshot(pane))
        return result

    def enrich(pane, paths, generation, cancel):
        record("enrich_start", paths=[str(p) for p in paths], generation=generation)
        try:
            return original_enrich(pane, paths, generation, cancel)
        finally:
            record("enrich_end", paths=[str(p) for p in paths], generation=generation)

    def enriched(pane, generation, path, row, thumbnail):
        live = signature(path)
        record("delivery_before", row=row_data(row), disk=live,
               stale_signature=row.file_signature is not None and row.file_signature != live,
               generation=generation, current_generation=pane.generation)
        result = original_enriched(pane, generation, path, row, thumbnail)
        item = pane.items.get(str(path))
        record("delivery_after", row=row_data(item.row) if item else None)
        return result

    def basic(path, is_dir=False):
        before = signature(path)
        row = original_basic(path, is_dir)
        record("basic_read", before=before, row=row_data(row), after=signature(path))
        return row

    def read(state, path):
        row = original_read(state, path)
        record("cache_read", path=str(path), disk=signature(path), row=row_data(row))
        return row

    def put(state, row):
        result = original_put(state, row)
        record("cache_put", row=row_data(row), disk=signature(row.path), result=result)
        return result

    def inspect(service, path, cancelled=lambda: False, force=False):
        record("inspect_start", path=str(path), disk=signature(path))
        row = original_inspect(service, path, cancelled, force)
        record("inspect_end", row=row_data(row), disk=signature(path))
        return row

    return [
        patch.object(Pane, "changed_event", event),
        patch.object(Pane, "flush_changes", flush),
        patch.object(Pane, "enrich", enrich),
        patch.object(Pane, "enriched", enriched),
        patch.object(metadata, "basic_entry", basic),
        patch.object(State, "read", read),
        patch.object(State, "put", put),
        patch.object(MediaService, "inspect", inspect),
    ]


class Result(unittest.TextTestResult):
    def startTest(self, test):
        global active_case
        active_case = test
        record("test_start", test=test.id())
        super().startTest(test)

    def stopTest(self, test):
        record("test_stop", test=test.id())
        super().stopTest(test)


def run_suite(suite, output, label, tracing):
    global active_case
    events.clear()
    timeouts.clear()
    begin = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    summary = dict(label=label, tracing=tracing, tests=result.testsRun,
                   failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), elapsed=time.monotonic() - begin,
                   checkpoints=list(timeouts), ok=result.wasSuccessful())
    outcomes.append(summary)
    output.joinpath(label + ".json").write_text(json.dumps(
        dict(summary=summary, events=list(events),
             failures=result.failures and [str(x[1]) for x in result.failures],
             errors=result.errors and [str(x[1]) for x in result.errors]),
        ensure_ascii=False, indent=2, default=str))
    print("DIAGNOSTIC_RESULT " + json.dumps(summary, default=str), flush=True)
    if not summary["ok"] or summary["checkpoints"]:
        for event in list(events)[-120:]:
            print("DIAGNOSTIC_TRACE " + json.dumps(event, default=str), flush=True)
    active_case = None
    return result


def main():
    global extended
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--case", choices=("suite", "plain", "traced", "suite-plain", "suite-traced"))
    parser.add_argument("--label")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    support.until = diagnosed_until
    if args.case:
        extended = args.case != "suite"
        patches = instrument() if args.case in ("traced", "suite-traced") else []
        for p in patches:
            p.start()
        try:
            suite = (unittest.defaultTestLoader.discover("tests") if args.case in ("suite", "suite-plain", "suite-traced")
                     else unittest.TestSuite([behaviors.NativeFileBehaviorsTests(TARGET)]))
            run_suite(suite, output, args.label, args.case in ("traced", "suite-traced"))
        finally:
            for p in reversed(patches):
                p.stop()
        return 1 if any(not item["ok"] or item["checkpoints"] for item in outcomes) else 0

    # Each process owns a fresh Gtk.Application registration. Reusing a class
    # across separate unittest runners leaves its D-Bus object exported.
    cases = [("suite", "suite-original")]
    cases += [(mode, f"focused-{mode}-{n:02d}")
              for mode in ("plain", "traced") for n in range(args.trials)]
    cases += [(mode, f"{mode}-{n:02d}")
              for mode in ("suite-plain", "suite-traced") for n in range(5)]
    summaries = []
    for mode, label in cases:
        process = subprocess.run(
            [sys.executable, __file__, "--output", str(output), "--case", mode,
             "--label", label], timeout=180)
        report = output / (label + ".json")
        if not report.exists():
            raise RuntimeError(f"Diagnostic process {label} exited {process.returncode} without a report")
        summary = json.loads(report.read_text())["summary"]
        summaries.append(summary)
    output.joinpath("summary.json").write_text(json.dumps(summaries, indent=2, default=str))
    findings = any(not item["ok"] or item["checkpoints"] for item in summaries)
    print("DIAGNOSTIC_FINDINGS=" + str(findings).lower(), flush=True)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
