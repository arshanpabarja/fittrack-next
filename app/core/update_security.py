import base64
import hashlib
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.license_public_key import PUBLIC_KEY_HEX


VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def validate_version(version):
    version = str(version or "").strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("شماره نسخه باید مانند 1.2.0 باشد.")
    return version


def version_tuple(version):
    normalized = validate_version(version)
    core = normalized.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(part) for part in core.split("."))


def file_sha256(path):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def release_manifest(version, sha256, size):
    version = validate_version(version)
    sha256 = str(sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256) or type(size) is not int or size <= 0:
        raise ValueError("مشخصات فایل نسخه معتبر نیست.")
    return f"LBU1\n{version}\n{sha256}\n{size}\n".encode("utf-8")


def encode_signature(signature):
    return "LBU1." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def decode_signature(value):
    prefix, encoded = str(value).strip().split(".", 1)
    if prefix != "LBU1" or len(encoded) > 200:
        raise ValueError("امضای نسخه معتبر نیست.")
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


def verify_release(version, sha256, size, signature):
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        public.verify(
            decode_signature(signature),
            release_manifest(version, sha256, int(size)),
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise ValueError("امضای دیجیتال نسخه جدید معتبر نیست.") from exc
    return True
