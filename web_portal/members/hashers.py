import base64
import hashlib
import hmac

from django.contrib.auth.hashers import BasePasswordHasher, mask_hash


class LifeBoxLegacyPasswordHasher(BasePasswordHasher):
    """Verify hashes created by the pre-Django LifeBox server."""

    algorithm = "lifebox_pbkdf2_sha256"

    def encode(self, password, salt, iterations=310000):
        if isinstance(salt, str):
            salt_bytes = base64.urlsafe_b64decode(salt.encode())
            salt_text = salt
        else:
            salt_bytes = salt
            salt_text = base64.urlsafe_b64encode(salt_bytes).decode()
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, int(iterations))
        return f"{self.algorithm}${int(iterations)}${salt_text}${base64.urlsafe_b64encode(digest).decode()}"

    def verify(self, password, encoded):
        try:
            algorithm, iterations, salt, digest = encoded.split("$", 3)
            if algorithm != self.algorithm:
                return False
            candidate = self.encode(password, salt, int(iterations)).split("$", 3)[3]
            return hmac.compare_digest(candidate, digest)
        except (TypeError, ValueError):
            return False

    def safe_summary(self, encoded):
        algorithm, iterations, salt, digest = encoded.split("$", 3)
        return {
            "algorithm": algorithm,
            "iterations": iterations,
            "salt": mask_hash(salt),
            "hash": mask_hash(digest),
        }

    def must_update(self, encoded):
        return True
