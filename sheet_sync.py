"""Optional Google Sheets synchronization. Credentials never enter browser state.

Only writes the managed source/calculation tabs; editable Inputs are preserved.
Requires an existing spreadsheet explicitly selected by the owner.
"""
import json
import os
from sync_failure import SyncFailure
from pathlib import Path
from db import connect, now

PREFIX='SIMPLES_'

def configured():
    path=os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE','')
    return bool(path and Path(path).is_file())

def cell(value,formula=False):
    if value is None:
        return {}
    if formula:
        return {'userEnteredValue':{'formulaValue':value}}
    kind='boolValue' if isinstance(value,bool) else 'numberValue' if isinstance(value,(int,float)) else 'stringValue'
    return {'userEnteredValue':{kind:value}}

def build_tables(settings):
    with connect(settings.db_path) as c:
        market=[['release_id','artist','title','format','lowest_price','currency','num_for_sale','captured_at','source_url']]
        indices={}
        for r in c.execute('SELECT r.*,s.lowest_price,s.currency,s.num_for_sale,s.captured_at FROM releases r JOIN snapshots s ON s.id=(SELECT id FROM snapshots WHERE release_id=r.release_id ORDER BY captured_at DESC LIMIT 1) ORDER BY r.release_id'):
            indices[r['release_id']]=len(market)+1
            market.append([r['release_id'],r['artist'],r['title'],r['format'],float(r['lowest_price']) if r['lowest_price'] is not None else None,
                           r['currency'],r['num_for_sale'],r['captured_at'],f"https://www.discogs.com/release/{r['release_id']}"])
        sources=[['offer_id','release_id','vendor','cost_total','currency','media_condition','sleeve_condition','version_confirmed','captured_at','source_url','預定售價','售價幣別','持有商品','確認供貨','出貨天數']]
        offers=c.execute('SELECT * FROM sourcing_offers ORDER BY id').fetchall()
        for r in offers:
            sources.append([r['id'],r['release_id'],r['vendor'],float(r['amount']),r['currency'],r['media_cond'],r['sleeve_cond'],bool(r['version_confirmed']),r['recorded_at'],r['source_url'],float(r['sale_price']) if r['sale_price'] else None,r['sale_currency'],bool(r['owned_confirmed']),bool(r['supply_confirmed']),r['dispatch_days']])
        inputs=[['參數','數值','說明'],['合計費率',float(settings.fee_pct),'請按實際費用調整'],['淨出貨運費 TWD',float(settings.shipping),'賣家自行承擔部分'],
                ['包材 TWD',float(settings.packing),'每件包材'],['風險準備 TWD',float(settings.reserve),'每件預留費用'],['最低淨利率',settings.min_margin,'初始篩選門檻'],
                ['','', ''],['幣別','1 外幣 = TWD','匯率日期 YYYY-MM-DD']]
        for cc in ('TWD','USD','JPY','EUR','GBP'):
            fx=c.execute('SELECT * FROM fx_rates WHERE currency=? ORDER BY rate_date DESC LIMIT 1',(cc,)).fetchone()
            inputs.append([cc,1 if cc=='TWD' else float(fx['twd_per_unit']) if fx else None,now()[:10] if cc=='TWD' else fx['rate_date'] if fx else None])
        analysis=[['offer_id','release_id','售價 TWD','進貨成本 TWD','費用 TWD','估算淨利 TWD','淨利率','資料檢查','候選結果','毛利 TWD','毛利率','售價依據']]
        formula_positions=set()
        for i,r in enumerate(offers,2):
            mi=indices.get(r['release_id'])
            src=f"'{PREFIX}Sources'!"
            m=f"'{PREFIX}Discogs'!"
            inp=f"'{PREFIX}Inputs'!"
            # Exact currency lookups; missing and expired rates remain visibly unavailable.
            def rate_formula(cc):
                table=f'{inp}$A$9:$C$13'
                return f'IF(COUNTIF({inp}$A$9:$A$13,{cc})<>1,"缺匯率",IF(OR(VLOOKUP({cc},{table},2,FALSE)="",VLOOKUP({cc},{table},3,FALSE)=""),"缺匯率",IF(OR(TODAY()-DATEVALUE(VLOOKUP({cc},{table},3,FALSE))>7,TODAY()<DATEVALUE(VLOOKUP({cc},{table},3,FALSE))),"匯率日期無效",VLOOKUP({cc},{table},2,FALSE))))'
            sale=f'IF({m}E{mi}="","缺行情",IF(ISNUMBER({rate_formula(f"{m}F{mi}")}),{m}E{mi}*({rate_formula(f"{m}F{mi}")}),"缺有效匯率"))' if mi else '"缺行情"'
            sale=f'IF({src}K{i}<>"",IF(ISNUMBER({rate_formula(f"{src}L{i}")}),{src}K{i}*({rate_formula(f"{src}L{i}")}),"缺有效匯率"),{sale})'
            cost=f'IF(ISNUMBER({rate_formula(f"{src}E{i}")}),{src}D{i}*({rate_formula(f"{src}E{i}")}),"缺有效匯率")'
            check=(f'IF({src}H{i}<>TRUE,"待核對版本",IF(OR(TODAY()-DATEVALUE(LEFT({src}I{i},10))>2,TODAY()-DATEVALUE(LEFT({m}H{mi},10))>2),"報價或行情過期",IF(AND(ISNUMBER(C{i}),ISNUMBER(D{i}),C{i}>0,{m}G{mi}>0),"資料齊全","缺有效價格／匯率")))' if mi else '"缺行情"')
            vals=[f'={src}A{i}',f'={src}B{i}','='+sale,'='+cost,
                  f'=IF(ISNUMBER(C{i}),C{i}*{inp}$B$2+SUM({inp}$B$3:$B$5),"待補資料")',
                  f'=IF(AND(ISNUMBER(C{i}),ISNUMBER(D{i}),ISNUMBER(E{i})),C{i}-D{i}-E{i},"待補資料")',
                  f'=IF(AND(ISNUMBER(F{i}),ISNUMBER(C{i}),C{i}>0),F{i}/C{i},"待補資料")','='+check,
                  f'=IF(H{i}<>"資料齊全",H{i},IF(AND(F{i}>0,G{i}>={inp}$B$6),"候選：仍需核對品相與供貨","暫無空間"))',
                  f'=IF(AND(ISNUMBER(C{i}),ISNUMBER(D{i})),C{i}-D{i},"待補資料")',
                  f'=IF(AND(ISNUMBER(J{i}),ISNUMBER(C{i}),C{i}>0),J{i}/C{i},"待補資料")',
                  f'=IF({src}K{i}<>"","人工預定售價","最低掛牌價（非成交價）")']
            analysis.append(vals)
            formula_positions.update((i-1,j) for j in range(len(vals)))
    candidates=[['平台','商品編號','搜尋詞','商品名稱','藝人','格式','規格品番','商品標價（未含進貨費用）','幣別','價格類型','庫存狀態','來源連結','擷取時間']]
    with connect(settings.db_path) as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='platform_candidates'").fetchone():
            for r in c.execute('SELECT * FROM platform_candidates ORDER BY id'):
                candidates.append([r['platform'],r['external_id'],r['query'],r['title'],r['artist'],r['format'],r['catalog_no'],float(r['price']) if r['price'] else None,r['currency'],r['price_kind'],r['availability'],r['source_url'],r['captured_at']])
    import comparisons
    comparison_rows=[['配對狀態','Discogs 版本','格式','商品','平台','貨源連結','來源標價','來源幣別','參考售價 TWD','總成本 TWD','價差 TWD','毛利 TWD','毛利率','淨利 TWD','淨利率','待確認事項','計算說明','Want 人數','Have 人數','刊登狀態','Discogs 刊登編號','成本依據']]
    with connect(settings.db_path) as c:
        has_platforms=c.execute("SELECT 1 FROM sqlite_master WHERE name='platform_candidates'").fetchone()
    if has_platforms:
        comparison_data=comparisons.build(settings)
        from sheet_audit import audit_comparisons
        if not audit_comparisons(comparison_data)['ok']:
            raise SyncFailure('comparison_invalid')
        for r in comparison_data:
            def number(key):return float(r[key]) if r[key] is not None else None
            comparison_rows.append([r['status'],r['release_id'],r['format'],r['source_title'],r['vendor'],r['source_url'],number('source_price'),r['source_currency'],number('sale_twd'),number('cost_twd'),number('spread_twd'),number('gross_twd'),r['gross_margin'],number('net_twd'),r['net_margin'],'；'.join(r['issues']),'預估毛利按來源標價計算；未含未填的進貨費用。已填總成本時改用總成本。匯率 https://www.exchangerate-api.com',r.get('want'),r.get('have'),'已上架（人工登錄）' if r.get('listing_status')=='listed' else '未上架',r.get('listing_id'),'進貨總成本' if r.get('cost_basis')=='confirmed_total' else '來源標價'])
    return {'Comparisons':comparison_rows,'PlatformCandidates':candidates,'Discogs':market,'Sources':sources,'Inputs':inputs,'Analysis':analysis},formula_positions

def sync(settings,session=None):
    with connect(settings.db_path) as c:
        row=c.execute("SELECT value FROM meta WHERE key='google_sheet_id'").fetchone()
    if not row:
        raise ValueError('尚未選擇 Google Sheets 試算表')
    if session is None:
        if not configured():
            raise ValueError('尚未設定 Google Sheets 帳號授權')
        try:
            from google.oauth2.service_account import Credentials
            from google.auth.transport.requests import AuthorizedSession
        except ImportError:
            raise ValueError('尚未安裝 Google Sheets 連接套件') from None
        creds=Credentials.from_service_account_file(os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'],scopes=['https://www.googleapis.com/auth/spreadsheets'])
        session=AuthorizedSession(creds)
    base='https://sheets.googleapis.com/v4/spreadsheets/'+row[0]
    def request(method,url,**kwargs):
        code='write_unknown' if method=='POST' else 'readback_failed' if url.endswith('/values:batchGet') else 'read_failed'
        try:
            response=session.request(method,url,timeout=40,**kwargs)
        except Exception:
            raise SyncFailure(code) from None
        if response.status_code>=400:
            raise SyncFailure('write_rejected' if method=='POST' and response.status_code<500 else code)
        try:return response.json()
        except (ValueError,TypeError):raise SyncFailure(code) from None
    info=request('GET',base,params={'fields':'sheets(properties,developerMetadata)'})
    existing={s['properties']['title']:s for s in info.get('sheets',[])}
    tables,formulas=build_tables(settings)
    requests=[]
    written={}
    ids=set(s['properties']['sheetId'] for s in existing.values())
    for title,rows in tables.items():
        name=PREFIX+title
        existing_sheet=existing.get(name)
        if existing_sheet:
            if not any(m.get('metadataKey')=='simples_owner' and m.get('metadataValue')=='record_business_v1' for m in existing_sheet.get('developerMetadata',[])):
                raise SyncFailure('ownership_conflict',[title])
            sid=existing_sheet['properties']['sheetId']
            if title=='Inputs':
                continue # User-owned assumptions and rates survive every subsequent sync.
        else:
            sid=max(ids or {0})+1;ids.add(sid)
            requests.extend([{'addSheet':{'properties':{'sheetId':sid,'title':name}}},
                {'createDeveloperMetadata':{'developerMetadata':{'metadataKey':'simples_owner','metadataValue':'record_business_v1','visibility':'DOCUMENT','location':{'sheetId':sid}}}}])
        written[title]=rows
        encoded=[{'values':[cell(v,title=='Analysis' and (i,j) in formulas) for j,v in enumerate(values)]} for i,values in enumerate(rows)]
        requests.extend([
            {'updateSheetProperties':{'properties':{'sheetId':sid,'gridProperties':{'rowCount':max(1000,len(rows)+10),'columnCount':max(26,len(rows[0])),'frozenRowCount':1}},'fields':'gridProperties'}},
            {'updateCells':{'range':{'sheetId':sid},'rows':encoded,'fields':'userEnteredValue'}},
            {'repeatCell':{'range':{'sheetId':sid,'startRowIndex':0,'endRowIndex':1},'cell':{'userEnteredFormat':{'backgroundColor':{'red':.14,'green':.31,'blue':.24},'textFormat':{'bold':True,'foregroundColor':{'red':1,'green':1,'blue':1}}}},'fields':'userEnteredFormat'}},
            {'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':0,'endIndex':len(rows[0])},'properties':{'pixelSize':170},'fields':'pixelSize'}}])
    request('POST',base+':batchUpdate',json={'requests':requests})
    from sheet_audit import audit_written_tables
    reply=request('GET',base+'/values:batchGet',params=[('ranges',"'"+PREFIX+name+"'") for name in written]+[('valueRenderOption','FORMULA')])
    verification=audit_written_tables(written,reply.get('valueRanges',[]))
    if not verification['ok']:
        raise SyncFailure('readback_mismatch',[e.get('table') for e in verification['errors']])
    with connect(settings.db_path) as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES('last_sheet_sync',?)",(now(),))
    return {'synced':True,'verification':verification,'source_rows':len(tables['Sources'])-1,'market_rows':len(tables['Discogs'])-1}
