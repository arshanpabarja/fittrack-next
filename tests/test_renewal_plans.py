import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QComboBox

from app.domain.models import MemberDetails, SignupPlan
from app.services.plans import PlansService
from app.services.walk_in import WalkInSignupService
from app.ui.pages.members import MemberDialog, RenewalDialog


class RenewalPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_local_catalog_reaches_renewal_with_correct_gender_price_and_status(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plans.json"
            path.write_text(json.dumps({
                "مرد": [{"id": 10, "name": "آقایان ۱۲ جلسه", "price": "۲,۴۰۰,۰۰۰"},
                        {"id": 11, "name": "غیرفعال ۱۲ جلسه", "price": 100, "is_active": False}],
                "زن": [{"id": 20, "name": "بانوان ۸ جلسه", "price": 1800000}],
                "همه": [{"id": 30, "name": "عمومی ۱۰ جلسه", "price": 2000000}],
            }, ensure_ascii=False), encoding="utf-8-sig")
            plans = WalkInSignupService(path, None, None).list_plans()
            self.assertEqual(plans, tuple(p for p in PlansService(None, path).load() if p.is_active))
            self.assertEqual([p.gender for p in plans], ["male", "female", "all"])
            for gender, expected, price in [("مرد", [10, 30], 2400000),
                                            ("زن", [20, 30], 1800000),
                                            ("male", [10, 30], 2400000),
                                            ("female", [20, 30], 1800000)]:
                with self.subTest(gender=gender):
                    member = SimpleNamespace(full_name="عضو آزمایشی", gender=gender,
                                             remaining_sessions=0, plan="")
                    dialog = RenewalDialog(member, plans=plans)
                    self.assertEqual([p.id for p in dialog.available_plans], expected)
                    self.assertTrue(dialog.submit.isEnabled())
                    self.assertEqual(dialog.amount.value(), price)
                    dialog.close()

    def test_member_edit_uses_active_plan_dropdown_and_preserves_current_plan(self):
        member = MemberDetails(
            id=1,
            first_name="آرش",
            last_name="احمدی",
            mobile="09120000001",
            national_id="0012345678",
            plan="پلن قدیمی ۱۲ جلسه",
            used_sessions=3,
            debt=0,
            signup_time="1405/06/01",
            father_name="علی",
            certificate_no="12",
            address="تهران",
            age=30,
            gender="مرد",
            payment=0,
        )
        plans = (
            SignupPlan(1, "بدنسازی ۸ جلسه", 1_000_000, "male", 8, True),
            SignupPlan(2, "عمومی ۱۰ جلسه", 1_200_000, "all", 10, True),
            SignupPlan(3, "پلن غیرفعال ۶ جلسه", 900_000, "all", 6, False),
        )
        dialog = MemberDialog(member, plans=plans)
        self.assertIsInstance(dialog.plan, QComboBox)
        self.assertEqual(
            [dialog.plan.itemText(index) for index in range(dialog.plan.count())],
            ["پلن قدیمی ۱۲ جلسه", "بدنسازی ۸ جلسه", "عمومی ۱۰ جلسه"],
        )
        self.assertEqual(dialog.plan.currentText(), member.plan)

        saved = []
        dialog.save_requested.connect(saved.append)
        dialog.plan.setCurrentText("بدنسازی ۸ جلسه")
        self.assertEqual(dialog.remaining_sessions.maximum(), 8)
        dialog._emit_save()
        self.assertEqual(saved[0]["plan"], "بدنسازی ۸ جلسه")
        dialog.close()
