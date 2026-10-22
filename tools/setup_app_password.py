"""Set one application password locally. Never writes the plaintext password."""

import argparse
import ast
import getpass
import os
from pathlib import Path
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.licensing import LicenseError, current_device_id
from app.core.password_activation import derive_password_key, make_activation, public_key_hex


def _atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def set_password(password, confirmation):
    if password != confirmation:
        raise LicenseError("رمز و تکرار آن یکسان نیستند.")
    if len(password) < 8 or len(password) > 256 or not password.strip():
        raise LicenseError("یک رمز بین ۸ تا ۲۵۶ نویسه انتخاب کنید.")
    device = current_device_id()
    owner_dir = ROOT / ".license-owner"
    configuration = ROOT / "app" / "core" / "license_public_key.py"
    salt = None
    key = None
    if configuration.exists():
        try:
            values = {}
            for statement in ast.parse(configuration.read_text(encoding="utf-8")).body:
                if isinstance(statement, ast.Assign):
                    for target in statement.targets:
                        if isinstance(target, ast.Name) and target.id in {"PUBLIC_KEY_HEX", "PASSWORD_SALT_HEX"}:
                            values[target.id] = ast.literal_eval(statement.value)
            previous_salt = bytes.fromhex(values.get("PASSWORD_SALT_HEX", ""))
            if len(previous_salt) == 16:
                candidate = derive_password_key(password, previous_salt)
                if public_key_hex(candidate) == values.get("PUBLIC_KEY_HEX"):
                    salt, key = previous_salt, candidate
        except (ValueError, TypeError, SyntaxError):
            pass
    if key is None:
        salt = secrets.token_bytes(16)
        key = derive_password_key(password, salt)
    public = public_key_hex(key)
    # Retain a public configuration backup so existing releases can be identified.
    # No private signing key, DPAPI blob, password, or password-derived seed is saved.
    if configuration.exists():
        backup = owner_dir / ("public-before-password-" + secrets.token_hex(6) + ".txt")
        _atomic_write(backup, configuration.read_text(encoding="utf-8"))
    _atomic_write(owner_dir / "build-check.lic", make_activation(key, device))
    _atomic_write(configuration,
        '"""Fixed password verifier. Contains no plaintext password or private key."""\n\n'
        f'PUBLIC_KEY_HEX = "{public}"\nPASSWORD_SALT_HEX = "{salt.hex()}"\n')


def run_gui():
    from tools.setup_app_password_ui import run
    return run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    if args.gui:
        return run_gui()
    try:
        set_password(getpass.getpass("Application password: "), getpass.getpass("Repeat password: "))
    except (LicenseError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    print("Password configured. Run build_desktop_release.py to update the customer release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
