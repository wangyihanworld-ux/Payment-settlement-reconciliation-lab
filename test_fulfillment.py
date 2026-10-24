import unittest
import uuid
from pathlib import Path
from fulfillment import fulfillment, order_cash_review
from event_store import EventStore


class FulfillmentTests(unittest.TestCase):
    def setUp(self):
        self.lines = [dict(line_id='L1',order='O1',sku='S1',quantity=5,unit_price_cents=2000,currency='HKD')]

    def event(self, id, kind, quantity, **extra):
        return dict(id=id,kind=kind,quantity=quantity,line_id='L1',date='2026-10-01',**extra)

    def test_split_shipments(self):
        result=fulfillment(self.lines,[self.event('S1','ship',2),self.event('S2','ship',3)],'2026-10-02')
        self.assertEqual(result['lines'][0]['unfulfilled'],0)
        self.assertEqual(len(result['accepted']),2)

    def test_cancel_unshipped_only(self):
        result=fulfillment(self.lines,[self.event('S1','ship',3),self.event('C1','cancel',3)],'2026-10-02')
        self.assertEqual(result['lines'][0]['cancelled'],0)
        self.assertEqual(result['issues'][0]['reason'],'exceeds_unfulfilled_quantity')

    def test_partial_return_not_new_demand(self):
        result=fulfillment(self.lines,[self.event('S1','ship',5),self.event('R1','return',2,shipment_id='S1')],'2026-10-02')
        self.assertEqual((result['lines'][0]['net_delivered'],result['lines'][0]['unfulfilled']),(3,0))

    def test_cumulative_return(self):
        result=fulfillment(self.lines,[self.event('S1','ship',2),self.event('R1','return',2,shipment_id='S1'),self.event('R2','return',1,shipment_id='S1')],'2026-10-02')
        self.assertEqual(result['lines'][0]['returned'],2)
        self.assertEqual(len(result['issues']),1)

    def test_return_before_shipment(self):
        result=fulfillment(self.lines,[self.event('R1','return',1,shipment_id='S1'),self.event('S1','ship',2)],'2026-10-02')
        self.assertEqual(result['lines'][0]['returned'],0)

    def test_duplicate_no_extra_shipment(self):
        e=self.event('S1','ship',2)
        result=fulfillment(self.lines,[e,e.copy()],'2026-10-02')
        self.assertEqual(result['lines'][0]['shipped'],2)

    def test_conflicting_id_quarantined(self):
        result=fulfillment(self.lines,[self.event('S1','ship',2),self.event('S1','ship',3)],'2026-10-02')
        self.assertEqual(result['lines'][0]['shipped'],0)

    def test_future_excluded(self):
        result=fulfillment(self.lines,[self.event('S1','ship',2)],'2026-09-30')
        self.assertEqual(result['lines'][0]['shipped'],0)

    def test_future_conflict_excluded(self):
        event=self.event('S1','ship',2)
        result=fulfillment(self.lines,[event,dict(event,date='2026-11-01',quantity=3)],'2026-10-02')
        self.assertEqual(result['lines'][0]['shipped'],2)

    def test_order_join_flags(self):
        result=fulfillment(self.lines,[self.event('C1','cancel',1)],'2026-10-02')
        review=order_cash_review(result,[dict(order='O1',kind='capture',amount=10000)])
        self.assertTrue(review[0]['paid_but_unfulfilled'])
        self.assertTrue(review[0]['refund_review'])

    def test_duplicate_line_rejected(self):
        with self.assertRaises(ValueError):
            fulfillment(self.lines*2,[],'2026-10-02')

    def test_unknown_order(self):
        with self.assertRaises(ValueError):
            order_cash_review(fulfillment(self.lines,[],'2026-10-02'),[dict(order='missing',kind='capture',amount=1)])

class StoreTests(unittest.TestCase):
    def test_restart_preserves_idempotence(self):
        path=Path(f'test-{uuid.uuid4().hex}.db')
        store=EventStore(path)
        event={'id':'RESTART','amount':100}
        try:
            store.ingest(event)
            store.close()
            store=EventStore(path)
            self.assertEqual(store.ingest(event),'duplicate')
            self.assertEqual(len(store.events()),2)
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_attempts_preserve_conflict(self):
        store=EventStore(':memory:')
        try:
            e={'id':'E1','amount':100}
            self.assertEqual(store.ingest(e),'accepted')
            self.assertEqual(store.ingest(e),'duplicate')
            self.assertEqual(store.ingest(dict(e,amount=200)),'conflict')
            self.assertEqual(len(store.events()),3)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM inbox').fetchone()[0],1)
        finally:
            store.close()

    def test_invalid_id(self):
        store=EventStore(':memory:')
        try:
            with self.assertRaises(ValueError):
                store.ingest({'id':''})
        finally:
            store.close()
