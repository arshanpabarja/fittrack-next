"""Offline, device-bound activation. Every launch verifies the signed license."""

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.license_public_key import PUBLIC_KEY_HEX

PRODUCT = "lifebox-desktop"
DEVICE_PATTERN = re.compile(r"LBX-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}\Z")


class LicenseError(Exception):
    pass


def normalize_device_id(value):
    if not isinstance(value, str):
        raise LicenseError("شناسهٔ دستگاه معتبر نیست.")
    value = value.strip().upper()
    if not DEVICE_PATTERN.fullmatch(value):
        raise LicenseError("شناسهٔ دستگاه معتبر نیست.")
    return value


def device_id_from_guid(guid):
    if not isinstance(guid, str) or not guid.strip():
        raise LicenseError("شناسهٔ ویندوز قابل خواندن نیست.")
    digest = hashlib.sha256(
        (PRODUCT + ":v1:" + guid.strip().lower()).encode("utf-8")
    ).hexdigest().upper()[:32]
    return "LBX-" + "-".join(digest[index:index + 8] for index in range(0, 32, 8))


def current_device_id():
    # No hostname, environment override, MAC address, or random fallback: these
    # would silently allow a copied installation to become another device.
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        return device_id_from_guid(guid)
    except (ImportError, OSError) as exc:
        raise LicenseError("شناسهٔ دستگاه خوانده نشد؛ فعال‌سازی فقط روی ویندوز پشتیبانی می‌شود.") from exc


def encode_part(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_part(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid encoding")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def verification_key():
    try:
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
    except ValueError as exc:
        raise LicenseError("کلید فعال‌سازیِ سازنده تنظیم نشده است؛ با سازنده تماس بگیرید.") from exc


def verify_license(token, device_id, public_key=None):
    public_key = verification_key() if public_key is None else public_key
    device_id = normalize_device_id(device_id)
    try:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError("Invalid size")
        prefix, payload_part, signature_part = token.strip().split(".")
        if prefix != "LB1":
            raise ValueError("Invalid version")
        payload = _decode_part(payload_part)
        signature = _decode_part(signature_part)
        public_key.verify(signature, b"LB1." + payload)
        claims = json.loads(payload)
        if not isinstance(claims, dict):
            raise ValueError("Invalid claims")
        if claims.get("product") != PRODUCT or type(claims.get("version")) is not int or claims["version"] != 1:
            raise ValueError("Invalid product")
        for field in ("device", "license_id", "customer", "issued_at"):
            if not isinstance(claims.get(field), str) or not claims[field].strip():
                raise ValueError("Invalid field")
        licensed_device = normalize_device_id(claims["device"])
    except (ValueError, binascii.Error, InvalidSignature, UnicodeError, LicenseError, RecursionError) as exc:
        raise LicenseError("کد فعال‌سازی معتبر نیست یا تغییر کرده است.") from exc
    if licensed_device != device_id:
        raise LicenseError("این کد برای دستگاه دیگری صادر شده است.")
    return claims


class LicenseStore:
    def __init__(self, path, device_id, public_key=None):
        self.path = Path(path)
        self.device_id = normalize_device_id(device_id)
        self.public_key = verification_key() if public_key is None else public_key

    def load(self):
        try:
            # Bound input before reading a potentially replaced file.
            with self.path.open("r", encoding="utf-8") as stream:
                token = stream.read(4097)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as exc:
            raise LicenseError("فایل فعال‌سازی قابل خواندن نیست.") from exc
        return verify_license(token, self.device_id, self.public_key)

    def activate(self, token):
        claims = verify_license(token, self.device_id, self.public_key)
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False,
                prefix=".activation-", suffix=".tmp",
            ) as stream:
                temporary = Path(stream.name)
                stream.write(token.strip())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise LicenseError("فعال‌سازی ذخیره نشد؛ دسترسی نوشتن به پوشهٔ برنامه را بررسی کنید.") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return claims
