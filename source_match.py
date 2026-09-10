"""Conservative demand-first admission; evidence never confirms a release."""
import re
from matching import normalized,media

# Explicit non-record products; do not reject records merely mentioning an OBI/booklet.
MERCH=re.compile(r'T[- ]?shirt|T卹|T恤|ショルダーバッグ|スマホポーチ|コースター|掛毯|吊飾|扭蛋|吉他帶|無刷電變',re.I)

def evidence(source,release):
    title=source['title']
    if MERCH.search(title):return []
    source_format=media(source['format']);target_format=media(release['format'])
    if source_format and target_format and source_format!=target_format:return []
    reasons=[]
    catalog=normalized(source['catalog_no'])
    if catalog and catalog not in ('none','na') and catalog in [normalized(x) for x in release['catno'].split(',')]:
        reasons.append('規格品番一致，仍需核對壓片')
    # Discogs can include translated titles separated by '='; either complete title is evidence.
    titles=[normalized(x) for x in release['title'].split('=')]
    source_title=normalized(title)
    if any(len(t)>=4 and t in source_title for t in titles):
        reasons.append('專輯名稱包含一致文字，仍需核對版本')
    if not reasons:return []
    if source_format and source_format==target_format:reasons.append('格式一致')
    return reasons
