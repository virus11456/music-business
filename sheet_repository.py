"""Explicit migration/readback adapter; does not silently enable Sheet-primary mode."""
import os
import re
import threading
import time

_request_lock = threading.Lock()
_next_request = 0.0
from urllib.parse import quote
from sheet_records import PREFIX, TABLES, compare
from sheet_sync import cell

OWNER = 'simples_data_v1'


class SheetRepository:
    def __init__(self, spreadsheet_id, session=None):
        if not isinstance(spreadsheet_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,150}', spreadsheet_id):
            raise ValueError('Invalid spreadsheet ID')
        self.base = 'https://sheets.googleapis.com/v4/spreadsheets/' + spreadsheet_id
        if session is None:
            from google.oauth2.service_account import Credentials
            from google.auth.transport.requests import AuthorizedSession
            credentials = Credentials.from_service_account_file(
                os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'],
                scopes=['https://www.googleapis.com/auth/spreadsheets'])
            session = AuthorizedSession(credentials)
        self.session = session

    def request(self, method, suffix='', **kwargs):
        global _next_request
        try:
            with _request_lock:
                delay = _next_request - time.monotonic()
                if delay > 0: time.sleep(delay)
                _next_request = time.monotonic() + 1.1
                response = self.session.request(method, self.base + suffix, timeout=40, **kwargs)
        except Exception:
            raise ValueError('Sheet request result unknown; read back before retrying') from None
        if response.status_code >= 400:
            raise ValueError('Sheet request failed; no migration completion claimed')
        return response.json()

    def inventory(self):
        info = self.request('GET', params={'fields': 'sheets(properties,developerMetadata)'})
        return {s['properties']['title']: s for s in info.get('sheets', [])}

    @staticmethod
    def owned(sheet):
        return any(m.get('metadataKey') == 'simples_owner' and m.get('metadataValue') == OWNER
                   for m in sheet.get('developerMetadata', []))

    def read(self, names):
        if not names or any(n not in TABLES for n in names):
            raise ValueError('Unsupported business table')
        existing = self.inventory()
        for name in names:
            sheet = existing.get(PREFIX + name)
            if not sheet or not self.owned(sheet):
                raise ValueError('Business sheet missing or not owned by the application')
        params = [('ranges', "'" + PREFIX + n + "'") for n in names]
        params += [('valueRenderOption', 'UNFORMATTED_VALUE'), ('dateTimeRenderOption', 'SERIAL_NUMBER')]
        reply = self.request('GET', '/values:batchGet', params=params)
        ranges = reply.get('valueRanges', [])
        if len(ranges) != len(names):
            raise ValueError('Incomplete Sheet read')
        return {name: value.get('values', []) for name, value in zip(names, ranges)}

    def seed_missing(self, tables):
        """Only creates absent data tabs. Existing data is never overwritten by migration."""
        if not tables or any(name not in TABLES for name in tables):
            raise ValueError('Unsupported business table')
        existing = self.inventory()
        for name in tables:
            old = existing.get(PREFIX + name)
            if old and not self.owned(old):
                raise ValueError('Same-name Sheet belongs to another workflow; stopped')
        old_names = [n for n in tables if PREFIX + n in existing]
        if old_names:
            report = compare({n: tables[n] for n in old_names}, self.read(old_names))
            if not report['equal']:
                raise ValueError('Existing Sheet differs from migration source; stopped without overwrite')
        next_id = max([s['properties']['sheetId'] for s in existing.values()] or [0]) + 1
        created = []
        for name, rows in tables.items():
            if name in old_names:
                continue
            sid = next_id; next_id += 1
            reqs = [
                {'addSheet': {'properties': {'sheetId': sid, 'title': PREFIX + name,
                    'gridProperties': {'rowCount': max(2, len(rows)), 'columnCount': len(rows[0]), 'frozenRowCount': 1}}}},
                {'createDeveloperMetadata': {'developerMetadata': {'metadataKey': 'simples_owner',
                    'metadataValue': OWNER, 'visibility': 'DOCUMENT', 'location': {'sheetId': sid}}}},
                {'updateCells': {'start': {'sheetId': sid, 'rowIndex': 0, 'columnIndex': 0},
                    'rows': [{'values': [cell(v) for v in row]} for row in rows], 'fields': 'userEnteredValue'}},
            ]
            # One table is atomic. On an interrupted migration the next run verifies existing tabs.
            self.request('POST', ':batchUpdate', json={'requests': reqs})
            created.append(name)
        report = compare(tables, self.read(list(tables)))
        if not report['equal']:
            raise ValueError('Migration readback mismatch; primary switch forbidden')
        return {'verified': True, 'created': created, **report}

    def replace(self, expected, updated):
        """Validate the last read before one atomic multi-table write (single app writer)."""
        if set(expected) != set(updated) or not updated:
            raise ValueError('Invalid replacement tables')
        if not compare(expected, self.read(list(expected)))['equal']:
            raise ValueError('Sheet changed since read; reload before applying this change')
        existing = self.inventory()
        requests = []
        for name, rows in updated.items():
            sheet = existing[PREFIX + name]
            if not self.owned(sheet):
                raise ValueError('Sheet ownership changed')
            sid = sheet['properties']['sheetId']
            requests.extend([
                {'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {
                    'rowCount': max(2, len(rows), sheet['properties']['gridProperties']['rowCount']),
                    'columnCount': max(len(rows[0]), sheet['properties']['gridProperties']['columnCount'])}},
                    'fields': 'gridProperties.rowCount,gridProperties.columnCount'}},
                {'updateCells': {'range': {'sheetId': sid},
                    'rows': [{'values': [cell(v) for v in row]} for row in rows], 'fields': 'userEnteredValue'}},
            ])
        self.request('POST', ':batchUpdate', json={'requests': requests})

    def format_data_tables(self):
        """Readable data sheets without changing source values or unrelated tabs."""
        existing = self.inventory()
        requests = []
        for name in TABLES:
            sheet = existing.get(PREFIX + name)
            if not sheet or not self.owned(sheet):
                raise ValueError('Data sheet missing; formatting stopped')
            sid = sheet['properties']['sheetId']
            requests.extend([
                {'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1},
                    'cell': {'userEnteredFormat': {'backgroundColor': {'red': .14, 'green': .31, 'blue': .24},
                        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
                        'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat'}},
                {'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS'},
                    'properties': {'pixelSize': 180}, 'fields': 'pixelSize'}},
            ])
            if name == 'purchase_items':
                for start,end,width in [(0,1,260),(1,2,120),(2,4,360)]:
                    requests.append({'updateDimensionProperties': {'range': {'sheetId': sid,
                        'dimension': 'COLUMNS','startIndex': start,'endIndex': end},
                        'properties': {'pixelSize': width},'fields': 'pixelSize'}})
                requests.append({'repeatCell': {'range': {'sheetId': sid,'startRowIndex': 1},
                    'cell': {'userEnteredFormat': {'wrapStrategy': 'WRAP','verticalAlignment': 'TOP'}},
                    'fields': 'userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment'}})
        self.request('POST', ':batchUpdate', json={'requests': requests})
        return {'formatted': len(TABLES)}
