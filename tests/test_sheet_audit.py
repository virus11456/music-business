import unittest
from sheet_primary import memory_schema
from sheet_records import capture
from sheet_audit import audit_tables, audit_comparisons

class AuditTests(unittest.TestCase):
    def data(self):
        c=memory_schema()
        try:return capture(c)
        finally:c.close()

    def test_empty_roundtrip_and_no_mutation(self):
        data=self.data(); before=repr(data)
        self.assertTrue(audit_tables(data)['ok'])
        self.assertEqual(repr(data),before)

    def test_broken_headers_and_missing_parent(self):
        data=self.data();data['meta'][0][0]='wrong'
        self.assertFalse(audit_tables(data)['ok'])
        data=self.data();data['version_searches'].append([99,'{}','[]','2026-09-13','[]'])
        self.assertIn('missing_parent',[e['code'] for e in audit_tables(data)['errors']])

    def row(self):
        return dict(key='candidate-1-2',format='CD',source_format='CD',sale_twd='100.00',source_twd='70.00',gross_twd='30.00',gross_margin=.3,want=5)

    def test_arithmetic_duplicate_and_format(self):
        row=self.row()
        self.assertTrue(audit_comparisons([row])['ok'])
        self.assertFalse(audit_comparisons([row,row])['ok'])
        row['source_format']='Vinyl'
        self.assertFalse(audit_comparisons([row])['ok'])
        row=self.row();row['gross_twd']='40'
        self.assertFalse(audit_comparisons([row])['ok'])

    def test_null_price_and_barcode_conflict(self):
        row=self.row();row['gross_twd']=None
        self.assertTrue(audit_comparisons([row])['ok'])
        row.update(barcodes=['123'],source_barcodes=['456'])
        self.assertFalse(audit_comparisons([row])['ok'])

    def test_rounded_low_sale_high_negative_margin(self):
        row=self.row();row.update(sale_twd='1.00',source_twd='1000.00',gross_twd='-999.00',gross_margin=float(1-1000/1.004))
        self.assertTrue(audit_comparisons([row])['ok'])

    def test_catalog_conflict(self):
        row=self.row();row.update(catalog_no='TOCP-123',source_catalog_no='TOCP-456')
        self.assertFalse(audit_comparisons([row])['ok'])
