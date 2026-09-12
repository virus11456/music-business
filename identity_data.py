"""Validated barcode evidence; never equates a barcode with a unique pressing."""
import json,re,unicodedata

def barcodes(value):
    values=value if isinstance(value,list) else [value]
    result=set()
    for value in values:
        if not isinstance(value,str):continue
        code=re.sub(r'[\s-]','',unicodedata.normalize('NFKC',value))
        if len(code) not in (8,12,13,14) or not code.isascii() or not code.isdigit() or len(set(code))==1:continue
        if (sum(int(n)*(3 if i%2==0 else 1) for i,n in enumerate(reversed(code[:-1])))+int(code[-1]))%10==0:
            result.add(code.zfill(14))
    return sorted(result)

def source_codes(source):
    value=source.get('barcodes',[]) if hasattr(source,'get') else []
    if not isinstance(value,list):value=[value]
    found=re.findall(r'(?:JAN|EAN|UPC|Barcode|條碼|条码)\s*[:：#]?\s*([0-9][0-9 -]{6,22}[0-9])',unicodedata.normalize('NFKC',str(source['title'])),re.I)
    return barcodes(list(value or [])+found)

def release_codes(c,rid):
    row=c.execute('SELECT value FROM meta WHERE key=?',(f'release_barcodes_{rid}',)).fetchone()
    if not row:return []
    try:return barcodes(json.loads(row[0]))
    except (ValueError,TypeError):return []

def enrich(c,source):
    source=dict(source)
    row=c.execute('SELECT value FROM meta WHERE key=?',(f"source_identity_{source['id']}",)).fetchone()
    if row:
        try:
            data=json.loads(row[0])
            if data['identity']==[source[k] for k in ('title','artist','format','catalog_no')]:
                source['barcodes']=barcodes(data.get('barcodes',[]));source['labels']=data.get('labels','') if isinstance(data.get('labels',''),str) else ''
        except (ValueError,KeyError,TypeError):pass
    return source

def save_source(c,source,item):
    if 'barcodes' not in item and 'labels' not in item:return
    data={'identity':[source[k] for k in ('title','artist','format','catalog_no')],'barcodes':barcodes(item.get('barcodes',[])),'labels':item.get('labels','')}
    c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(f"source_identity_{source['id']}",json.dumps(data,ensure_ascii=False)))
