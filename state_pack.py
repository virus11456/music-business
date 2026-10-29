"""Compact wire format for long lists of similar rows (comparisons).

Rows become columns; a column whose values repeat is sent as a dictionary of
distinct values plus indices. Missing keys are listed so a client restores the
exact rows. Pure transport: `unpack(pack(rows)) == rows` for JSON values.
"""
import json

MEDIA_TYPE = 'application/vnd.simples.packed+json'
VERSION = 1


def pack(rows):
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    columns = {}
    for field in fields:
        values = [row.get(field) for row in rows]
        index, distinct, positions = {}, [], []
        for value in values:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if key not in index:
                index[key] = len(distinct)
                distinct.append(value)
            positions.append(index[key])
        column = {'d': distinct, 'i': positions} if len(distinct) * 2 <= len(rows) else {'v': values}
        missing = [i for i, row in enumerate(rows) if field not in row]
        if missing:
            column['m'] = missing
        columns[field] = column
    return {'version': VERSION, 'n': len(rows), 'f': fields, 'c': columns}


def unpack(packed):
    if packed.get('version') != VERSION:
        raise ValueError('Unsupported packed format')
    rows = [{} for _ in range(packed['n'])]
    for field in packed['f']:
        column = packed['c'][field]
        missing = set(column.get('m', ()))
        values = [column['d'][i] for i in column['i']] if 'd' in column else column['v']
        for i, value in enumerate(values):
            if i not in missing:
                rows[i][field] = value
    return rows


def packed_state(state):
    """Same state with workflow.comparisons replaced by its packed form; the input is not modified."""
    workflow = dict(state['workflow'])
    workflow['comparisons_packed'] = pack(workflow.pop('comparisons'))
    return {**state, 'workflow': workflow}
