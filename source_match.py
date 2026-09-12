"""Conservative demand-first admission; evidence never confirms a release."""
import re,unicodedata
from matching import normalized,media

# Explicit non-record products; do not reject records merely mentioning an OBI/booklet.
MERCH=re.compile(r'T[- ]?shirt|T卹|T恤|ショルダーバッグ|スマホポーチ|コースター|掛毯|吊飾|扭蛋|吉他帶|無刷電變',re.I)

def identified_format(value, title=''):
    text=unicodedata.normalize('NFKC',str(value or '')+' '+str(title or ''))
    patterns={'CD':r'(?<![a-z])(?:CD|SACD)(?![a-z])|compact disc',
              'Vinyl':r'vinyl|黑膠|黑胶|アナログ|(?<![a-z])LP(?![a-z])',
              'Cassette':r'cassette|カセット|卡帶|卡带|錄音帶|录音带'}
    found=[kind for kind,pattern in patterns.items() if re.search(pattern,text,re.I)]
    return found[0] if len(found)==1 else None

# Only an unambiguous hyphenated catalog token; never infer from a year or barcode.
def source_catalog(source):
    explicit=str(source['catalog_no'] or '').strip()
    if normalized(explicit) not in ('','none','na','未確認','unknown'):return explicit
    title=unicodedata.normalize('NFKC',str(source['title'] or '')).upper()
    matches=re.findall(r'(?<![A-Z0-9])([A-Z]{2,6})[-‐‑–—](\d{3,7})(?![A-Z0-9]|[-‐‑–—]\d)',title)
    values={prefix+'-'+number for prefix,number in matches if prefix not in ('CD','LP','SACD','DVD','BLU','ISBN','JAN','EAN','UPC')}
    return next(iter(values)) if len(values)==1 else ''

def evidence(source,release):
    title=source['title']
    if MERCH.search(title):return []
    source_format=identified_format(source['format'],title);target_format=identified_format(release['format'])
    if not source_format or source_format!=target_format:return []
    from identity_data import source_codes,barcodes
    source_barcodes=source_codes(source);target_barcodes=barcodes(release.get('barcodes',[]) if hasattr(release,'get') else [])
    if source_barcodes and target_barcodes and not set(source_barcodes)&set(target_barcodes):return []
    reasons=[]
    if set(source_barcodes)&set(target_barcodes):reasons.append('有效條碼一致，仍需核對壓片')
    catalog=normalized(source_catalog(source))
    if catalog and catalog not in ('none','na') and catalog in [normalized(x) for x in release['catno'].split(',')]:
        reasons.append('規格品番一致，仍需核對壓片')
        if not source['catalog_no']:reasons.append('唱片編號取自賣場標題，仍需核對實物')
    target_catalogs=[normalized(x) for x in release['catno'].split(',') if normalized(x) not in ('','none','na','未確認')]
    if catalog not in ('','none','na','未確認') and target_catalogs and catalog not in target_catalogs:return []
    # Discogs can include translated titles separated by '='; either complete title is evidence.
    titles=[normalized(x) for x in release['title'].split('=')]
    source_title=normalized(title)
    if any(len(t)>=4 and t in source_title for t in titles):
        reasons.append('專輯名稱包含一致文字，仍需核對版本')
    if not reasons:return []
    if source_format and source_format==target_format:reasons.append('格式一致')
    label=release['labels'] if 'labels' in release.keys() else ''
    explicit_labels=source.get('labels','') if hasattr(source,'get') else ''
    if set(normalized(x) for x in explicit_labels.split(',') if x.strip())&set(normalized(x) for x in label.split(',') if x.strip()):reasons.append('來源 Label 一致，僅作輔助證據')
    if any(len(normalized(x))>=4 and normalized(x) in source_title for x in label.split(',')):
        reasons.append('標題含相同 Label，僅作輔助證據')
    return reasons
