"""Create update metadata signed by the LifeBox owner's existing password."""

import argparse
import getpass
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.password_activation import derive_password_key, password_configuration, public_key_hex
from app.core.update_security import encode_signature, file_sha256, release_manifest, validate_version


def sign(package, version, password):
    version = validate_version(version)
    sha256, size = file_sha256(package)
    salt, expected_public = password_configuration()
    key = derive_password_key(password, salt)
    if public_key_hex(key) != expected_public:
        raise ValueError("رمز اصلی برنامه صحیح نیست.")
    signature = encode_signature(key.sign(release_manifest(version, sha256, size)))
    return {
        "version": version,
        "sha256": sha256,
        "size": size,
        "signature": signature,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.package.is_file():
        parser.error("Package does not exist.")
    try:
        result = sign(args.package, args.version, getpass.getpass("Owner password: "))
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    output = args.output or args.package.with_suffix(".release.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    raise SystemExit(main())
