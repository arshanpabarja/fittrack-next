import threading
import unittest
from unittest.mock import Mock, patch

from app.integrations.pos import RealPosTerminal, FakePosTerminal, create_pos_terminal
from app.services.preferences import DEFAULTS


class PosTests(unittest.TestCase):
    def terminal(self, code="RS = 00", reference="RN = 812770823734"):
        terminal = Mock()
        terminal.Response.GetTrxnResp.return_value = code
        terminal.Response.GetTrxnRRN.return_value = reference
        pcpos = Mock(return_value=terminal)
        factory = Mock(return_value=pcpos)
        return RealPosTerminal(factory=factory), terminal, pcpos, factory

    def test_legacy_lan_protocol_converts_toman_and_preserves_receipt(self):
        pos, terminal, pcpos, _ = self.terminal()
        receipt = pos.charge(2_400_000)
        self.assertTrue(receipt.success)
        self.assertEqual(receipt.amount, 2_400_000)
        self.assertEqual(receipt.reference, "812770823734")
        self.assertEqual(terminal.Amount, "24000000")
        self.assertEqual(terminal.Ip, "192.168.100.54")
        self.assertEqual(terminal.Port, 3030)
        self.assertEqual(terminal.ConnectionType, pcpos.cnType.LAN)
        terminal.send_transaction.assert_called_once_with()

    def test_decline_does_not_approve_and_allows_next_request(self):
        pos, _, _, factory = self.terminal("RS = 51")
        self.assertFalse(pos.charge(100).success)
        self.assertFalse(pos.charge(100).success)
        self.assertEqual(factory.call_count, 2)

    def test_unprefixed_response(self):
        pos, _, _, _ = self.terminal("00", "1234")
        self.assertEqual(pos.charge(100).reference, "1234")

    def test_uninitialized_response_is_polled(self):
        pos, terminal, _, _ = self.terminal()
        terminal.Response.GetTrxnResp.side_effect = [
            RuntimeError("Object reference not set"), "", "RS = 00",
        ]
        with patch("app.integrations.pos.time.sleep"):
            self.assertTrue(pos.charge(100).success)

    def test_timeout_blocks_resubmission(self):
        pos, terminal, _, factory = self.terminal()
        terminal.Response = None
        with patch("app.integrations.pos.time.monotonic", side_effect=[0, 0, 61]), patch("app.integrations.pos.time.sleep"):
            self.assertFalse(pos.charge(100).success)
        self.assertFalse(pos.charge(100).success)
        factory.assert_called_once_with()

    def test_send_exception_blocks_resubmission(self):
        pos, terminal, _, factory = self.terminal()
        terminal.send_transaction.side_effect = RuntimeError("connection lost")
        self.assertFalse(pos.charge(100).success)
        self.assertFalse(pos.charge(100).success)
        factory.assert_called_once_with()

    def test_success_without_rrn_requires_reconciliation(self):
        pos, _, _, factory = self.terminal(reference="RN = ")
        self.assertFalse(pos.charge(100).success)
        self.assertFalse(pos.charge(100).success)
        factory.assert_called_once_with()

    def test_missing_driver_does_not_fall_back_to_fake(self):
        factory = Mock(side_effect=ImportError("missing driver"))
        receipt = RealPosTerminal(factory=factory).charge(100)
        self.assertFalse(receipt.success)
        self.assertIn("missing driver", receipt.message)

    def test_invalid_amount_never_contacts_terminal(self):
        pos, _, _, factory = self.terminal()
        for amount in [0, -1, 1.5, True, None, "bad"]:
            self.assertFalse(pos.charge(amount).success)
        factory.assert_not_called()

    def test_concurrent_request_is_rejected(self):
        pos, terminal, _, factory = self.terminal()
        entered, release = threading.Event(), threading.Event()
        def send():
            entered.set()
            release.wait(3)
        terminal.send_transaction.side_effect = send
        thread = threading.Thread(target=pos.charge, args=(100,))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertFalse(pos.charge(200).success)
            factory.assert_called_once_with()
        finally:
            release.set()
            thread.join(3)

    def test_factory_defaults_to_real_and_fake_requires_explicit_mode(self):
        self.assertIsInstance(create_pos_terminal(DEFAULTS), RealPosTerminal)
        self.assertIsInstance(create_pos_terminal({**DEFAULTS, "pos_mode": "fake"}), FakePosTerminal)
        with self.assertRaises(ValueError):
            create_pos_terminal({**DEFAULTS, "pos_mode": "invalid"})
