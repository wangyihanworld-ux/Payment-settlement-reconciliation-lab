"""Opt-in daily observation cutoff. Dates are assumed in a single local calendar."""
from datetime import date
from reconcile import reconcile


def visible_events(events, observed_cutoff):
    boundary = date.fromisoformat(observed_cutoff)
    visible = []
    for event in events:
        # Missing receipt date is an error, not a guessed business date.
        received = date.fromisoformat(event['received_date'])
        occurred = date.fromisoformat(event['date'])
        if received < occurred:
            raise ValueError('Receipt date precedes business occurrence')
        if received <= boundary:
            visible.append({key: value for key, value in event.items() if key != 'received_date'})
    return visible


def reconcile_as_known(events, bank, business_cutoff, observed_cutoff):
    return reconcile(visible_events(events, observed_cutoff),
                     visible_events(bank, observed_cutoff), business_cutoff)
