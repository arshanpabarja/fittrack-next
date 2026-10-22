"""One owner-chosen password; clients retain only a signed device activation."""

import hmac
import json
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core import license_public_key as configuration
from app.core.licensing import LicenseError, PRODUCT, encode_part, normalize_device_id


def derive_password_key(password, salt):
    if not isinstance(password, str) or not password or len(password) > 256:
        raise LicenseError("رمز را وارد کنید؛ طول رمز حداکثر ۲۵۶ نویسه است.")
    seed = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_hex(key):
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ).hex()


def password_configuration():
    try:
        salt = bytes.fromhex(getattr(configuration, "PASSWORD_SALT_HEX", ""))
        public = bytes.fromhex(configuration.PUBLIC_KEY_HEX)
        if len(salt) != 16 or len(public) != 32:
            raise ValueError("Invalid password configuration")
        return salt, public.hex()
    except (TypeError, ValueError) as exc:
        raise LicenseError("رمز اصلی برنامه هنوز تعیین نشده است؛ ابزار تعیین رمز را روی سیستم سازنده باز کنید.") from exc


def make_activation(key, device):
    claims = {
        "product": PRODUCT, "version": 1, "device": normalize_device_id(device),
        "customer": "Password activation", "license_id": str(uuid.uuid4()),
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "LB1." + encode_part(payload) + "." + encode_part(key.sign(b"LB1." + payload))


def activate_with_password(password, store):
    salt, expected_public = password_configuration()
    key = derive_password_key(password, salt)
    if not hmac.compare_digest(public_key_hex(key), expected_public):
        raise LicenseError("رمز اشتباه است.")
    return store.activate(make_activation(key, store.device_id))
