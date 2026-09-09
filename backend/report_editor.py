"""Versioned human corrections preserve the original scraped evidence."""
from copy import deepcopy
from datetime import datetime, timezone
from intelligence_engine import _sections


def revise(data, payload):
    if payload.get('revision', 0) != data.get('revision', 0):
        raise ValueError('This report changed. Reload before saving your edits.')
    edits = payload.get('edits')
    if not isinstance(edits, list) or len(edits) > 300:
        raise ValueError('Provide at most 300 item corrections.')
    note = payload.get('note', '')
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError('Change note must be at most 2000 characters.')
    result = deepcopy(data)
    for edit in edits:
        if not isinstance(edit, dict) or type(edit.get('index')) is not int or not 0 <= edit['index'] < len(result['items']):
            raise ValueError('Invalid item index.')
        row = result['items'][edit['index']]
        for key in ('item', 'details', 'category'):
            value = edit.get(key)
            if not isinstance(value, str) or len(value) > 2000 or (key != 'details' and not value.strip()):
                raise ValueError('Each correction needs a category, item and details (maximum 2000 characters each).')
        if any(row.get(key, '') != edit[key] for key in ('item', 'details', 'category')):
            row.setdefault('original', {k: row.get(k) for k in ('item', 'details', 'category', 'confidence', 'verified')})
            row.update({k: edit[k] for k in ('item', 'details', 'category')})
            row.update(user_edited=True, verified=False, confidence=0)
    result['sections'] = _sections(result['items'])
    result['verified_count'] = sum(bool(row.get('verified')) for row in result['items'])
    result['overall_confidence'] = sum(row.get('confidence', 0) for row in result['items']) / max(1, len(result['items']))
    result['vehicles'] = []  # Cached vehicle cards must not contradict corrected items.
    result['stats'] = {'sources': len(result.get('sources', [])), 'items': len(result['items']), 'verified': result['verified_count'], 'vehicles': 0, 'discounts': len(result['sections'].get('Discounts', [])), 'bonuses': len(result['sections'].get('Bonuses', []))}
    result['revision'] = data.get('revision', 0) + 1
    result.setdefault('revisions', []).append({'revision': result['revision'], 'note': note, 'at': datetime.now(timezone.utc).isoformat()})
    result['exports'] = {'pdf': True, 'json': True}
    result['email_sent'] = False
    result['email_error'] = None
    return result
