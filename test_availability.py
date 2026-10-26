import unittest
from availability import reconcile_as_known, visible_events
from fulfillment import fulfillment, order_cash_review
from reconcile import demo


class AvailabilityTests(unittest.TestCase):
    def test_late_bank_record_changes_known_status(self):
        events, bank = demo()
        events = [dict(row, received_date='2026-10-01') for row in events]
        bank = [dict(row, received_date='2026-10-05') for row in bank]
        self.assertEqual(reconcile_as_known(events, bank, '2026-10-03', '2026-10-03')['batches'][0]['status'], 'pending')
        self.assertEqual(reconcile_as_known(events[::-1], bank, '2026-10-03', '2026-10-05')['batches'][0]['status'], 'matched')

    def test_repeat_delivery_is_same_business_event(self):
        events, bank = demo()
        received = [dict(row, received_date='2026-10-01') for row in events]
        received.append(dict(events[0], received_date='2026-10-04'))
        result = reconcile_as_known(received, [dict(bank[0], received_date='2026-10-03')], '2026-10-03', '2026-10-05')
        self.assertEqual(result['batches'][0]['expected_cents'], 7700)

    def test_missing_or_impossible_receipt_date_fails(self):
        with self.assertRaises(KeyError):
            visible_events([{'date':'2026-10-01'}], '2026-10-05')
        with self.assertRaises(ValueError):
            visible_events([{'date':'2026-10-02','received_date':'2026-10-01'}], '2026-10-05')

    def test_installments_and_overpayment_are_distinct(self):
        lines = [dict(line_id='L', order='O', sku='S', quantity=1, unit_price_cents=100, currency='HKD')]
        state = fulfillment(lines, [], '2026-10-01')
        payments = [dict(order='O', kind='capture', amount=40), dict(order='O', kind='capture', amount=60)]
        self.assertEqual(order_cash_review(state, payments)[0]['payment_status'], 'fully_captured')
        payments.append(dict(order='O', kind='capture', amount=1))
        self.assertEqual(order_cash_review(state, payments)[0]['payment_status'], 'overpaid_requires_review')
