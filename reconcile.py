"""Synthetic, single-currency settlement reconciliation. Amounts are integer cents."""
from collections import Counter
from datetime import date


def reconcile(events, bank, cutoff):
    """Quarantine conflicting IDs; block affected batches instead of inventing totals."""
    date.fromisoformat(cutoff)
    groups, issues, blocked = {}, [], set()
    for row in events:
        try:
            when = date.fromisoformat(row['date'])
        except (KeyError, TypeError, ValueError):
            issues.append({'id': row.get('id'), 'reason': 'invalid_date'})
            blocked.add(row.get('batch'))
            continue
        if when > date.fromisoformat(cutoff):
            continue
        groups.setdefault(row.get('id'), []).append(row)
    clean = []
    for key, rows in groups.items():
        if not key or any(row != rows[0] for row in rows):
            issues.append({'id': key, 'reason': 'conflicting_or_missing_id'})
            blocked.update(r.get('batch') for r in rows)
            continue
        if len(rows) > 1:
            issues.append({'id': key, 'reason': 'identical_duplicate_ignored'})
        row = rows[0]
        try:
            date.fromisoformat(row['date'])
            valid = (row['currency'] == 'HKD' and row['kind'] in ('capture', 'refund', 'fee')
                     and type(row['amount']) is int and row['amount'] > 0
                     and bool(row['batch']) and bool(row['order']))
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            issues.append({'id': key, 'reason': 'invalid_fields'})
            blocked.add(row.get('batch'))
        elif row['date'] <= cutoff:
            clean.append(row)
    captures = {r['id']: r for r in clean if r['kind'] == 'capture'}
    refunded = Counter()
    for row in sorted(clean, key=lambda r: (r['date'], r['id'])):
        if row['kind'] != 'refund':
            continue
        original = captures.get(row.get('capture_id'))
        if (not original or original['order'] != row['order'] or original['date'] > row['date']
                or refunded[row.get('capture_id')] + row['amount'] > original['amount']):
            issues.append({'id': row['id'], 'reason': 'invalid_refund_reference_or_total'})
            blocked.add(row['batch'])
        else:
            refunded[row['capture_id']] += row['amount']
    expected = Counter()
    for row in clean:
        expected[row['batch']] += row['amount'] * (1 if row['kind'] == 'capture' else -1)
    actual, bank_seen = Counter(), {}
    for row in bank:
        try:
            when = date.fromisoformat(row['date'])
        except (KeyError, TypeError, ValueError):
            issues.append({'id': row.get('id'), 'reason': 'invalid_bank_date'})
            blocked.add(row.get('batch'))
            continue
        if when > date.fromisoformat(cutoff):
            continue
        if (row.get('id') in bank_seen or not row.get('id') or row.get('currency') != 'HKD'
                or type(row.get('amount')) is not int or not row.get('batch')):
            issues.append({'id': row.get('id'), 'reason': 'invalid_or_duplicate_bank_row'})
            blocked.add(row.get('batch'))
            if row.get('id') in bank_seen:
                blocked.add(bank_seen[row['id']])
            continue
        bank_seen[row['id']] = row['batch']
        date.fromisoformat(row['date'])
        if row['date'] <= cutoff:
            actual[row['batch']] += row['amount']
    # A refund must not rely on a capture in a quarantined batch.
    while True:
        dependent = {r['batch'] for r in clean if r['kind'] == 'refund'
                     and r.get('capture_id') in captures
                     and captures[r['capture_id']]['batch'] in blocked}
        if dependent <= blocked:
            break
        blocked.update(dependent)
    result = []
    for batch in sorted((set(expected) | set(actual) | blocked) - {None, ''}):
        status = ('blocked' if batch in blocked else 'unmatched_bank' if batch not in expected
                  else 'pending' if batch not in actual else 'matched' if expected[batch] == actual[batch]
                  else 'mismatch')
        result.append({'batch': batch, 'expected_cents': None if batch in blocked else expected.get(batch),
                       'bank_cents': actual.get(batch), 'status': status})
    return {'batches': result, 'issues': issues,
            'accepted_events': [r for r in clean if r['batch'] not in blocked]}


def demo():
    base = dict(date='2026-10-01', currency='HKD', batch='B1', order='O1')
    events = [dict(base, id='C1', kind='capture', amount=10000),
              dict(base, id='R1', kind='refund', amount=2000, capture_id='C1'),
              dict(base, id='F1', kind='fee', amount=300)]
    bank = [dict(id='BANK1', date='2026-10-03', currency='HKD', batch='B1', amount=7700)]
    return events, bank


if __name__ == '__main__':
    import json
    events, bank = demo()
    print(json.dumps(reconcile(events + [events[0]], bank, '2026-10-03'), indent=2))
