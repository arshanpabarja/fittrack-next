import os
import time
import uuid

from app.domain.models import PaymentReceipt


class FakePosTerminal:
    """Deterministic local POS adapter used until the real terminal is enabled."""

    def charge(self, amount):
        amount = max(0, int(amount))
        time.sleep(0.8)
        should_fail = os.getenv("FITTRACK_FAKE_POS_RESULT", "success").lower() == "fail"
        if should_fail:
            return PaymentReceipt(False, amount, "", "پرداخت آزمایشی ناموفق بود.")
        reference = f"TEST-{uuid.uuid4().hex[:12].upper()}"
        return PaymentReceipt(True, amount, reference, "پرداخت آزمایشی موفق بود.")

