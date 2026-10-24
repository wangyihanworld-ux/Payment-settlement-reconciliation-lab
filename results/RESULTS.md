# Synthetic order-to-settlement demonstration

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
