"""Generate a fully synthetic order/fulfillment/payment reconciliation evidence pack."""
import json
from pathlib import Path
from reconcile import reconcile, demo
from fulfillment import fulfillment, order_cash_review
from event_store import EventStore


def run():
    payments, bank=demo()
    lines=[dict(line_id='L1',order='O1',sku='DEMO-SKU',quantity=5,unit_price_cents=2000,currency='HKD')]
    flow=[dict(id='S1',line_id='L1',date='2026-10-01',kind='ship',quantity=2),
          dict(id='S2',line_id='L1',date='2026-10-02',kind='ship',quantity=2),
          dict(id='CANCEL1',line_id='L1',date='2026-10-02',kind='cancel',quantity=1),
          dict(id='RETURN1',line_id='L1',date='2026-10-03',kind='return',quantity=1,shipment_id='S1')]
    store=EventStore(':memory:')
    try:
        attempts=[store.ingest(e) for e in payments+[payments[0]]]
        settled=reconcile(store.events(),bank,'2026-10-03')
    finally:
        store.close()
    shipped=fulfillment(lines,flow,'2026-10-03')
    return dict(data_type='synthetic',currency='HKD',cutoff='2026-10-03',
                ingestion_attempts=attempts, settlement=settled, fulfillment=shipped,
                order_review=order_cash_review(shipped,settled['accepted_events']))


if __name__=='__main__':
    output=Path('results'); output.mkdir(exist_ok=True)
    result=run()
    (output/'demo.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'RESULTS.md').write_text('''# Synthetic order-to-settlement demonstration

The order is HKD 100.00: five units at HKD 20.00. Two split shipments dispatch
four units. One unshipped unit is cancelled and one shipped unit is returned.
The quantity identity is 5 = 4 shipped + 1 cancelled + 0 unfulfilled;
net delivered is 4 - 1 = 3. Returns do not recreate outstanding demand.

Captured 100.00 - recorded refund 20.00 - fee 3.00 = settlement 77.00,
which matches the synthetic bank entry. Nevertheless, cancelled/returned item
value is 40.00, exceeding the recorded refund of 20.00: refund review is true.
This is a review flag, NOT proof that a further refund is contractually due.
The example shows why matched bank totals do not prove order-level completeness.

Four ingestion attempts produce three unique events: the retried capture is
recorded as a duplicate and does not increase the settlement. No real customers,
payments, deployment, time saving or business benefits are claimed.
''',encoding='utf-8')
    print(json.dumps({'settlement':result['settlement']['batches'],'order_review':result['order_review']},indent=2))
