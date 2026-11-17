"""External, rollback-capable installer for a manually approved LifeBox release."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from contextlib import closing


def _write_result(runtime, version, status, error=""):
    target = runtime / "update-result.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"version": version, "status": status, "error": str(error)[:1000]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _wait_for_process(pid, timeout=120):
    if os.name == "nt":
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return
        try:
            result = ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
            if result == 0x00000102:
                raise RuntimeError("برنامه در زمان تعیین‌شده بسته نشد.")
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return
        time.sleep(0.25)
    raise RuntimeError("برنامه در زمان تعیین‌شده بسته نشد.")


def _safe_extract(package, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(package) as archive:
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            if destination != target and destination not in target.parents:
                raise RuntimeError("فایل نسخه جدید مسیر ناامن دارد.")
            unix_mode = (item.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise RuntimeError("فایل نسخه جدید شامل پیوند نمادین ناامن است.")
        archive.extractall(destination)


def _backup_sqlite(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as current:
        with closing(sqlite3.connect(destination)) as backup:
            current.backup(backup)


def _backup_data(runtime, destination):
    for folder in ("database", "state"):
        source_dir = runtime / folder
        if not source_dir.is_dir():
            continue
        for source in source_dir.iterdir():
            target = destination / folder / source.name
            if source.is_file() and source.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                _backup_sqlite(source, target)
            elif source.is_file() and source.name in {"plans.json", "activation.lic"}:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    plans = runtime / "database" / "plans.json"
    if plans.is_file():
        target = destination / "database" / plans.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plans, target)


def install(package, install_dir, runtime, pid, version):
    if install_dir.parent != runtime or not (install_dir / "LifeBox.exe").is_file():
        raise RuntimeError("مسیر نصب LifeBox معتبر نیست.")
    _wait_for_process(pid)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = runtime / "updates" / f"stage-{version}-{stamp}"
    work.mkdir(parents=True, exist_ok=False)
    _safe_extract(package, work)
    candidate = work / "LifeBox"
    executable = candidate / "LifeBox.exe"
    if not executable.is_file():
        raise RuntimeError("فایل LifeBox.exe در نسخه جدید پیدا نشد.")
    environment = os.environ.copy()
    environment["FITTRACK_RUNTIME_DIR"] = str(runtime)
    environment["FITTRACK_DATA_DIR"] = str(runtime / "database")
    environment["QT_QPA_PLATFORM"] = "offscreen"
    subprocess.run(
        [str(executable), "--check-desktop-release"],
        cwd=candidate,
        env=environment,
        check=True,
        timeout=45,
    )
    backup_root = runtime / "backups" / f"before-{version}-{stamp}"
    _backup_data(runtime, backup_root / "data")
    previous = backup_root / "application"
    previous.parent.mkdir(parents=True, exist_ok=True)
    os.replace(install_dir, previous)
    marker = runtime / "updates" / f"started-{version}-{stamp}.ok"
    process = None
    try:
        os.replace(candidate, install_dir)
        process = subprocess.Popen(
            [str(install_dir / "LifeBox.exe"), "--update-marker", str(marker)],
            cwd=install_dir,
            env=environment,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if marker.is_file():
                _write_result(runtime, version, "succeeded")
                return
            if process.poll() is not None:
                raise RuntimeError("نسخه جدید قبل از تکمیل راه‌اندازی بسته شد.")
            time.sleep(0.5)
        raise RuntimeError("نسخه جدید در زمان تعیین‌شده آماده نشد.")
    except Exception as exc:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
        failed = runtime / "updates" / f"failed-{version}-{stamp}"
        if install_dir.exists():
            os.replace(install_dir, failed)
        os.replace(previous, install_dir)
        subprocess.Popen([str(install_dir / "LifeBox.exe")], cwd=install_dir, env=environment)
        _write_result(runtime, version, "rolled_back", exc)
        raise
    finally:
        marker.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    runtime = args.runtime_dir.resolve()
    result_path = runtime / "update-result.json"
    result_path.unlink(missing_ok=True)
    try:
        install(
            args.package.resolve(), args.install_dir.resolve(), runtime,
            args.pid, args.version,
        )
    except Exception as exc:
        if not result_path.exists():
            _write_result(runtime, args.version, "failed", exc)
            executable = args.install_dir.resolve() / "LifeBox.exe"
            if executable.is_file():
                environment = os.environ.copy()
                environment["FITTRACK_RUNTIME_DIR"] = str(runtime)
                environment["FITTRACK_DATA_DIR"] = str(runtime / "database")
                subprocess.Popen([str(executable)], cwd=executable.parent, env=environment)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
