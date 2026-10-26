"""Auditable order-line fulfillment, with synthetic demonstration data only."""
from collections import Counter
from datetime import date


def fulfillment(lines, events, cutoff):
    """Reject invalid transitions, preserve accepted events and source IDs.

    Returns reduce delivered stock, not outstanding demand. Cancellation applies
    only to unshipped quantities. Same-day events use input sequence (documented).
    All orders in this educational model have one currency, HKD.
    """
    boundary = date.fromisoformat(cutoff)
    states = {}
    for row in lines:
        if (not isinstance(row.get('line_id'), str) or not row['line_id']
                or row['line_id'] in states or not row.get('order') or not row.get('sku')
                or row.get('currency') != 'HKD'
                or type(row.get('quantity')) is not int or row['quantity'] <= 0
                or type(row.get('unit_price_cents')) is not int or row['unit_price_cents'] < 0):
            raise ValueError('invalid or duplicate order line')
        states[row['line_id']] = dict(row, shipped=0, cancelled=0, returned=0)
    accepted, rejected, shipments, returns = [], [], {}, Counter()
    groups = {}
    for index, row in enumerate(events):
        try:
            when = date.fromisoformat(row['date'])
        except (KeyError, TypeError, ValueError):
            rejected.append({'id':row.get('id'),'reason':'invalid_date'})
            continue
        if when > boundary:
            continue
        groups.setdefault(row.get('id'), []).append((index, row))
    candidates = []
    for event_id, versions in groups.items():
        if not event_id or any(row != versions[0][1] for _, row in versions):
            rejected.append({'id': event_id, 'reason': 'conflicting_or_missing_id'})
            continue
        for _, duplicate in versions[1:]:
            rejected.append({'id': event_id, 'reason': 'identical_duplicate_ignored'})
        index, row = versions[0]
        try:
            when = date.fromisoformat(row['date'])
        except (KeyError, TypeError, ValueError):
            rejected.append({'id': event_id, 'reason': 'invalid_date'})
            continue
        if when <= boundary:
            candidates.append((when, index, row))
    for _, _, row in sorted(candidates, key=lambda x: (x[0], x[1])):
        state = states.get(row.get('line_id'))
        qty, kind = row.get('quantity'), row.get('kind')
        reason = None
        if not state or type(qty) is not int or qty <= 0:
            reason = 'invalid_line_or_quantity'
        elif kind in ('ship', 'cancel'):
            if qty > state['quantity'] - state['shipped'] - state['cancelled']:
                reason = 'exceeds_unfulfilled_quantity'
            else:
                state['shipped' if kind == 'ship' else 'cancelled'] += qty
                if kind == 'ship':
                    shipments[row['id']] = row
        elif kind == 'return':
            ship = shipments.get(row.get('shipment_id'))
            if (not ship or ship['line_id'] != row['line_id']
                    or returns[ship['id']] + qty > ship['quantity']):
                reason = 'invalid_return_reference_or_quantity'
            else:
                returns[ship['id']] += qty
                state['returned'] += qty
        else:
            reason = 'unknown_event_kind'
        if reason:
            rejected.append({'id': row['id'], 'reason': reason})
        else:
            accepted.append(dict(row))
    for state in states.values():
        state['unfulfilled'] = state['quantity'] - state['shipped'] - state['cancelled']
        state['net_delivered'] = state['shipped'] - state['returned']
    return {'lines': list(states.values()), 'accepted': accepted, 'issues': rejected}


def order_cash_review(fulfillment_result, payment_events):
    """Join already-validated payment events to logistics by order.

    Refunds need not imply a physical return. Value differences are review flags,
    not accounting receivables, revenue recognition or automatic refund orders.
    Caller supplies accepted events at the same cutoff; invalid events are unsafe.
    """
    totals = {}
    for line in fulfillment_result['lines']:
        value = totals.setdefault(line['order'], dict(captured_cents=0, refunded_cents=0,
                                                     order_value_cents=0,
                                                     cancellation_return_value_cents=0, unfulfilled_units=0))
        value['order_value_cents'] += line['quantity'] * line['unit_price_cents']
        value['cancellation_return_value_cents'] += (line['cancelled'] + line['returned']) * line['unit_price_cents']
        value['unfulfilled_units'] += line['unfulfilled']
    for row in payment_events:
        if row['order'] not in totals:
            raise ValueError('payment refers to unknown order')
        if row['kind'] in ('capture', 'refund'):
            field = 'captured_cents' if row['kind'] == 'capture' else 'refunded_cents'
            totals[row['order']][field] += row['amount']
    return [{'order': key, **value,
             'payment_status': ('overpaid_requires_review' if value['captured_cents'] > value['order_value_cents']
                                else 'fully_captured' if value['captured_cents'] == value['order_value_cents']
                                else 'partially_captured' if value['captured_cents'] else 'not_captured'),
             'logistics_requires_review': any(x['reason'] != 'identical_duplicate_ignored' for x in fulfillment_result['issues']),
             'paid_but_unfulfilled': value['captured_cents'] > value['refunded_cents'] and value['unfulfilled_units'] > 0,
             'refund_review': value['captured_cents'] > 0 and value['refunded_cents'] < value['cancellation_return_value_cents']}
            for key, value in sorted(totals.items())]
