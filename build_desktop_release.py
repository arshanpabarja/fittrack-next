"""Compile a desktop release without distributing the project or owner keys."""

import argparse
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import zipfile

from app.core.licensing import verification_key
from app.core.password_activation import password_configuration

ROOT = Path(__file__).resolve().parent


@contextmanager
def exclusive_build():
    import msvcrt
    lock_path = ROOT / "build" / "desktop-build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("Another desktop build is running. Wait for it to finish before retrying.") from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def compiler_command():
    command = [
        sys.executable, "-m", "nuitka", "--mode=standalone", "--python-flag=isolated",
        "--progress-bar=none",
        "--enable-plugin=pyqt6", "--include-qt-plugins=sensible,multimedia",
        "--include-module=clr", "--include-package=pythonnet",
        "--include-package-data=pythonnet", "--include-package-data=certifi",
        "--windows-console-mode=disable", "--windows-icon-from-ico=icon.ico",
        "--output-filename=LifeBox.exe", "--output-dir=build/desktop",
        "--include-data-dir=assets=assets", "--include-data-dir=models=models",
        "--include-data-files=Vazirmatn-Bold.ttf=Vazirmatn-Bold.ttf",
        "--include-data-files=app/ui/theme.qss=app/ui/theme.qss",
        "--assume-yes-for-downloads", "launch.py",
    ]
    ssl_policy = Path(ssl.__file__).with_name("codex-rejected-cas.pem")
    if ssl_policy.is_file():
        command.insert(-1, f"--include-data-files={ssl_policy}=codex-rejected-cas.pem")
    return command


def stage_runtime_files(distribution):
    distribution = Path(distribution)
    if not (distribution / "LifeBox.exe").is_file():
        raise RuntimeError("Compiled LifeBox.exe was not found.")
    # DLLs are explicitly staged after compilation (Nuitka data-dir flags omit
    # executable libraries). No database, state, source, or owner tool is copied.
    library = distribution / "Library"
    library.mkdir(exist_ok=True)
    for source in (ROOT / "Library").glob("*.dll"):
        shutil.copy2(source, library / source.name)
    (distribution / "README.txt").write_text(
        "Life Box\n\n"
        "Extract the whole folder to a writable local directory and run LifeBox.exe.\n"
        "Keep your club's database folder beside this folder, or set FITTRACK_DATA_DIR.\n"
        "On first launch, enter the application password supplied by the owner.\n"
        "Activation is checked at every launch and works offline.\n"
        "Keep state/ and database/ when updating an existing installation.\n"
        "Camera and payment terminal drivers still need installation on the target PC.\n",
        encoding="utf-8",
    )


def smoke_check(distribution):
    from app.core.licensing import LicenseStore, current_device_id
    distribution = Path(distribution)
    state = distribution / "state"
    # This is a build checkout, never an existing installation. Refuse to touch
    # any pre-existing runtime state, even if a previous build was interrupted.
    state.mkdir()
    activation = state / "activation.lic"
    diagnostic = ROOT / "build" / "release-check-error.txt"
    diagnostic.unlink(missing_ok=True)
    try:
        device = current_device_id()
        test_token = ROOT / ".license-owner" / "build-check.lic"
        if not test_token.is_file():
            raise RuntimeError("Set the application password using set-app-password.cmd before building.")
        LicenseStore(activation, device).activate(test_token.read_text(encoding="utf-8"))
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["FITTRACK_RELEASE_CHECK_DIAGNOSTIC"] = str(diagnostic)
        try:
            subprocess.run(
                [str(distribution.resolve() / "LifeBox.exe"), "--check-desktop-release"],
                cwd=distribution, env=environment, check=True, timeout=25,
            )
        except subprocess.CalledProcessError as exc:
            details = diagnostic.read_text(encoding="utf-8") if diagnostic.is_file() else "No diagnostic was produced."
            raise RuntimeError(f"Compiled release check failed ({exc.returncode}).\n{details}") from exc
    finally:
        diagnostic.unlink(missing_ok=True)
        activation.unlink(missing_ok=True)
        state.rmdir()


def package_release(distribution):
    distribution = Path(distribution)
    stage_runtime_files(distribution)
    files = sorted(path for path in distribution.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(distribution)
        # Ignore case because the target filesystem is Windows.
        public_ca_bundle = relative.as_posix().lower() in {
            "certifi/cacert.pem", "codex-rejected-cas.pem",
        }
        if path.suffix.lower() in {".py", ".pyw", ".pyc", ".pyo", ".dpapi", ".lic", ".db", ".sqlite", ".sqlite3"} or (path.suffix.lower() == ".pem" and not public_ca_bundle):
            raise RuntimeError(f"Release contains forbidden source or private data: {relative}")
        if path.name.lower().startswith(".env") or any(part.lower() in {"state", "logs", "database", ".license-owner", ".git", "tools", "web_portal"} for part in relative.parts):
            raise RuntimeError(f"Release contains forbidden directory: {relative}")
    destination = ROOT / "dist" / "lifebox-desktop.zip"
    destination.parent.mkdir(exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, Path("LifeBox") / path.relative_to(distribution))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-only", action="store_true", help="Package an already compiled release")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build the Windows release on Windows.")
    try:
        with exclusive_build():
            build(args)
    except RuntimeError as exc:
        parser.exit(1, f"{exc}\n")


def build(args):
    verification_key()  # Fail closed: an unprovisioned build must never ship.
    password_configuration()
    if not args.package_only:
        missing = [name for name in ("nuitka", "PyQt6", "numpy", "cv2", "cryptography", "pythonnet")
                   if importlib.util.find_spec(name) is None]
        if missing:
            raise RuntimeError("Missing build dependencies: " + ", ".join(missing))
        environment = os.environ.copy()
        environment.setdefault("NUITKA_CACHE_DIR", str(ROOT / "build" / "nuitka-cache"))
        temporary = ROOT / "build" / "desktop-temp"
        temporary.mkdir(parents=True, exist_ok=True)
        environment["TMP"] = str(temporary)
        environment["TEMP"] = str(temporary)
        subprocess.run(compiler_command(), cwd=ROOT, env=environment, check=True)
    distribution = ROOT / "build" / "desktop" / "launch.dist"
    stage_runtime_files(distribution)
    smoke_check(distribution)
    print(package_release(distribution))


if __name__ == "__main__":
    main()
