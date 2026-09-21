import os
import time
import uuid
import sys
import threading
from pathlib import Path

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


def _load_pcpos():
    library = Path(__file__).resolve().parents[2] / "Library"
    if str(library) not in sys.path:
        sys.path.append(str(library))
    import clr

    clr.AddReference(str(library / "pec.pcpos.dll"))
    from Intek.PcPosLibrary import PCPOS

    return PCPOS


def _response_value(value):
    return str(value or "").rsplit("=", 1)[-1].strip()


class RealPosTerminal:
    """Legacy PEC LAN protocol. Call charge from a worker, never the UI thread."""

    def __init__(self, host="192.168.100.54", port=3030, timeout=60, factory=None):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._factory = factory or _load_pcpos
        self._lock = threading.Lock()
        self._uncertain = False
        self._pending_terminal = None

    def charge(self, amount):
        try:
            parsed = int(amount)
            if isinstance(amount, bool) or parsed <= 0 or str(parsed) != str(amount).strip():
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            return PaymentReceipt(False, 0, "", "مبلغ پرداخت باید عدد صحیح مثبت به تومان باشد.")
        amount = parsed
        if not self._lock.acquire(blocking=False):
            return PaymentReceipt(False, amount, "", "کارتخوان مشغول پرداخت دیگری است؛ منتظر بمانید.")
        sent = False
        try:
            if self._uncertain:
                return self._unknown(amount)
            try:
                pcpos = self._factory()
                terminal = pcpos()
                terminal.Ip = self.host
                terminal.Port = self.port
                terminal.ConnectionType = pcpos.cnType.LAN
                terminal.Amount = str(amount * 10)
            except Exception as exc:
                return PaymentReceipt(False, amount, "", f"درایور کارتخوان آماده نیست: {exc}")
            self._pending_terminal = terminal
            sent = True
            deadline = time.monotonic() + self.timeout
            terminal.send_transaction()
            while time.monotonic() < deadline:
                response = terminal.Response
                if response is not None:
                    try:
                        code = _response_value(response.GetTrxnResp())
                    except Exception as exc:
                        if "Object reference not set" not in str(exc):
                            raise
                        code = ""
                    if code:
                        if code == "00":
                            reference = _response_value(response.GetTrxnRRN())
                            if not reference:
                                self._uncertain = True
                                return self._unknown(amount)
                            self._pending_terminal = None
                            return PaymentReceipt(True, amount, reference, f"پرداخت موفق؛ شماره پیگیری: {reference}")
                        self._pending_terminal = None
                        return PaymentReceipt(False, amount, "", f"پرداخت ناموفق؛ کد کارتخوان: {code}")
                time.sleep(0.25)
            self._uncertain = True
            return self._unknown(amount)
        except Exception:
            # A send/read failure can happen after the bank has charged the card.
            self._uncertain = sent
            return self._unknown(amount)
        finally:
            self._lock.release()

    def _unknown(self, amount):
        return PaymentReceipt(
            False, amount, "",
            "نتیجه پرداخت کارتخوان مشخص نیست. برای جلوگیری از برداشت دوباره، "
            "ابتدا رسید دستگاه و وضعیت بانکی را بررسی کنید. "
            "پرداخت جدید تا بررسی و اجرای دوباره برنامه مسدود است.",
        )


def create_pos_terminal(values):
    mode = values["pos_mode"]
    if mode == "real":
        return RealPosTerminal(values["pos_host"], values["pos_port"], values["pos_timeout"])
    if mode == "fake":
        return FakePosTerminal()
    raise ValueError("حالت کارتخوان باید real یا fake باشد.")
