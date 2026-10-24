import unittest
from reconcile import reconcile, demo


class ReconciliationTests(unittest.TestCase):
    def run_case(self, change=None, cutoff='2026-10-03'):
        events, bank = demo()
        if change:
            change(events, bank)
        return reconcile(events, bank, cutoff)

    def test_hand_calculated(self):
        row = self.run_case()['batches'][0]
        self.assertEqual((row['expected_cents'], row['status']), (7700, 'matched'))

    def test_identical_duplicate(self):
        result = self.run_case(lambda e, b: e.append(e[0].copy()))
        self.assertEqual(result['batches'][0]['expected_cents'], 7700)
        self.assertEqual(len(result['issues']), 1)

    def test_conflict(self):
        self.assertEqual(self.run_case(lambda e, b: e.append(dict(e[0], amount=20000)))['batches'][0]['status'], 'blocked')

    def test_refund_exceeds_capture(self):
        self.assertEqual(self.run_case(lambda e, b: e[1].update(amount=10001))['batches'][0]['status'], 'blocked')

    def test_missing_capture(self):
        self.assertEqual(self.run_case(lambda e, b: e[1].update(capture_id='missing'))['batches'][0]['status'], 'blocked')

    def test_currency(self):
        self.assertEqual(self.run_case(lambda e, b: e[1].update(currency='USD'))['batches'][0]['status'], 'blocked')

    def test_cutoff(self):
        self.assertEqual(self.run_case(cutoff='2026-10-02')['batches'][0]['status'], 'pending')

    def test_mismatch(self):
        self.assertEqual(self.run_case(lambda e, b: b[0].update(amount=7600))['batches'][0]['status'], 'mismatch')

    def test_duplicate_bank(self):
        self.assertEqual(self.run_case(lambda e, b: b.append(b[0].copy()))['batches'][0]['status'], 'blocked')

    def test_cumulative_refund(self):
        self.assertEqual(self.run_case(lambda e, b: e.append(dict(e[1], id='R2', amount=9000)))['batches'][0]['status'], 'blocked')

    def test_future_conflict_does_not_rewrite_cutoff(self):
        result = self.run_case(lambda e,b: e.append(dict(e[0], date='2026-11-01', amount=20000)))
        self.assertEqual(result['batches'][0]['status'], 'matched')

    def test_invalid_bank_date_is_exception(self):
        result = self.run_case(lambda e,b: b[0].update(date='invalid'))
        self.assertEqual(result['batches'][0]['status'], 'blocked')
        self.assertEqual(result['accepted_events'], [])

    def test_invalid_event_date(self):
        self.assertEqual(self.run_case(lambda e,b: e[0].update(date='bad'))['batches'][0]['status'],'blocked')

    def test_blocked_capture_blocks_dependent_refund(self):
        def change(e,b):
            e[1]['batch']='REFUND'
            e[2]['amount']=-1
        result=self.run_case(change)
        self.assertTrue(all(x['status']=='blocked' for x in result['batches']))

    def test_future_bank_duplicate_not_current_error(self):
        result=self.run_case(lambda e,b: b.append(dict(b[0],date='2026-11-01')))
        self.assertEqual(result['batches'][0]['status'],'matched')

    def test_bank_conflict_blocks_both_batches(self):
        result=self.run_case(lambda e,b: b.append(dict(b[0],batch='B2')))
        self.assertTrue(all(row['status']=='blocked' for row in result['batches']))


if __name__ == '__main__':
    unittest.main()
