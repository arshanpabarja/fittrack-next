import tempfile
import unittest
from pathlib import Path

from app.data.audit import AuditRepository
from app.services.audit import AuditService


class AuditTests(unittest.TestCase):
    def test_activity_is_append_only_searchable_and_redacts_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditService(AuditRepository(Path(directory) / "state.db"))
            audit.set_actor("manager-a")
            first = audit.record(
                "member_update",
                entity_type="member",
                entity_id=12,
                summary="ویرایش عضو نمونه",
                before={"plan": "قدیمی", "password": "never-store"},
                after={"plan": "جدید", "embedding": "never-store"},
            )
            audit.record(
                "manager_login_failed",
                actor="manager-b",
                summary="ورود ناموفق",
                success=False,
                error="رمز اشتباه",
            )

            rows = audit.list_activity(search="عضو نمونه")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], first)
            self.assertNotIn("password", rows[0]["before_json"])
            self.assertNotIn("embedding", rows[0]["after_json"])
            failed = audit.list_activity(action="manager_login_failed")
            self.assertEqual(failed[0]["actor"], "manager-b")
            self.assertFalse(failed[0]["success"])


if __name__ == "__main__":
    unittest.main()
