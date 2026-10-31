"""Dependency-free configuration. Monetary assumptions are NOT market facts."""
import os
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def money(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('金額必須是數字') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('金額必須是有限的非負數')
    return result

def load_env(path=ROOT / '.env'):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.strip().replace('_', '').isalnum():
            raise ValueError('.env 格式錯誤')
        os.environ.setdefault(key.strip(), value.strip().strip('\"\''))

def business_values(data):
    fields=('fee_pct','shipping','packing','reserve','min_margin')
    if any(k not in data for k in fields):raise ValueError('請填齊所有費用設定')
    result={k:money(data[k]) for k in fields}
    # Saved settings from before the PayPal split have no payment fields: their fee_pct was the combined rate,
    # so the payment part reads as zero instead of being counted twice.
    # Settings saved before the order-level fields read them as zero, which reproduces the earlier formula.
    for k in OPTIONAL_FIELDS:result[k]=money(data.get(k) or 0)
    if result['fee_pct']+result['payment_pct']+result['conversion_pct']>=1 or result['min_margin']>1:raise ValueError('費率合計須小於 100%，最低淨利率不可超過 100%')
    if result['tax_pct']>1:raise ValueError('買家稅率不可超過 100%')
    if min(result.values())<0:raise ValueError('費用設定不可為負數')
    return result

OPTIONAL_FIELDS=('payment_pct','payment_fixed','buyer_shipping','tax_pct','conversion_pct')

def fee_terms(settings):
    """Selling costs as `rate*sale + constant` (TWD), following real Discogs/PayPal statements:
    Discogs takes fee_pct of item + shipping charged to the buyer; PayPal takes payment_pct of item + shipping +
    buyer tax plus payment_fixed; withdrawing USD to TWD costs conversion_pct of what remains after both fees (the
    tax is remitted through Discogs). The shipping charged to the buyer is income set against the actual postage."""
    d,p,x,t=settings.fee_pct,settings.payment_pct,settings.conversion_pct,settings.tax_pct
    rate=d+p*(1+t)+x*(1-d-p*(1+t))
    constant=settings.payment_fixed*(1-x)+settings.shipping+settings.packing+settings.reserve-settings.buyer_shipping*(1-rate)
    return rate,constant

ASSUMPTION_FIELDS=('fee_pct',)+OPTIONAL_FIELDS+('shipping','packing','reserve')

def assumptions(settings):
    return {k:str(getattr(settings,k)) for k in ASSUMPTION_FIELDS}

def fees(settings, sale):
    """Selling costs in TWD for one item sold at `sale` TWD (negative when buyer-paid shipping exceeds them)."""
    rate,constant=fee_terms(settings)
    return sale*rate+constant

@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv('DB_PATH', str(ROOT / 'data/live.sqlite3'))))
    token: str = field(default_factory=lambda: os.getenv('DISCOGS_TOKEN', ''))
    user_agent: str = field(default_factory=lambda: os.getenv('DISCOGS_USER_AGENT', 'SimplesRecordResearch/0.1'))
    currency: str = field(default_factory=lambda: os.getenv('MARKET_CURRENCY', 'USD').upper())
    fee_pct: Decimal = field(default_factory=lambda: money(os.getenv('TOTAL_FEE_PCT', '0.12')))
    # PayPal: percentage of the sale (receiving + currency conversion) and a fixed fee per order in TWD.
    payment_pct: Decimal = field(default_factory=lambda: money(os.getenv('PAYMENT_FEE_PCT') or '0'))
    payment_fixed: Decimal = field(default_factory=lambda: money(os.getenv('PAYMENT_FIXED_TWD') or '0'))
    # Order-level terms: shipping charged to the buyer (TWD equivalent), buyer tax rate PayPal also charges on,
    # and the USD-to-TWD withdrawal conversion rate.
    buyer_shipping: Decimal = field(default_factory=lambda: money(os.getenv('BUYER_SHIPPING_TWD') or '0'))
    tax_pct: Decimal = field(default_factory=lambda: money(os.getenv('BUYER_TAX_PCT') or '0'))
    conversion_pct: Decimal = field(default_factory=lambda: money(os.getenv('CONVERSION_FEE_PCT') or '0'))
    shipping: Decimal = field(default_factory=lambda: money(os.getenv('SHIPPING_COST_TWD', '600')))
    packing: Decimal = field(default_factory=lambda: money(os.getenv('PACKING_COST_TWD', '50')))
    reserve: Decimal = field(default_factory=lambda: money(os.getenv('RISK_RESERVE_TWD', '0')))
    min_margin: float = field(default_factory=lambda: float(os.getenv('MIN_MARGIN', '.15')))
    hot_ratio: float = field(default_factory=lambda: float(os.getenv('HOT_RATIO', '3')))
    max_supply: int = field(default_factory=lambda: int(os.getenv('MAX_SUPPLY', '3')))
    # Demand scan and demand-first sourcing: Want floor, Want/Have floor, albums per night, Discogs calls per night.
    # An empty value (as copied from .env.example) means the default.
    # Official marketplace APIs; empty means the platform reports a missing key instead of searching.
    rakuten_app_id: str = field(default_factory=lambda: os.getenv('RAKUTEN_APPLICATION_ID', ''))
    rakuten_access_key: str = field(default_factory=lambda: os.getenv('RAKUTEN_ACCESS_KEY', ''))
    ebay_client_id: str = field(default_factory=lambda: os.getenv('EBAY_CLIENT_ID', ''))
    ebay_client_secret: str = field(default_factory=lambda: os.getenv('EBAY_CLIENT_SECRET', ''))
    scan_min_want: int = field(default_factory=lambda: int(os.getenv('SCAN_MIN_WANT') or '50'))
    demand_min_ratio: float = field(default_factory=lambda: float(os.getenv('DEMAND_MIN_RATIO') or '2'))
    demand_albums: int = field(default_factory=lambda: int(os.getenv('DEMAND_ALBUMS') or '100'))
    # Versions with this many or more copies for sale on Discogs are left out of the nightly sourcing list.
    demand_max_for_sale: int = field(default_factory=lambda: int(os.getenv('DEMAND_MAX_FOR_SALE') or '10'))
    scan_budget: int = field(default_factory=lambda: int(os.getenv('SCAN_REQUEST_BUDGET') or '600'))
    scan_max_new: int = field(default_factory=lambda: int(os.getenv('SCAN_MAX_NEW') or '150'))
    price_drop: float = field(default_factory=lambda: float(os.getenv('PRICE_DROP', '.20')))
    min_score: float = field(default_factory=lambda: float(os.getenv('MIN_SCORE', '60')))
    urgent_score: float = 85
    cooldown_days: int = 7
    skip_days: int = 30
    fx_max_age_days: int = 7
    snapshot_max_age_days: int = 2
    weights: tuple = (.30, .35, .15, .20)
    telegram_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    telegram_chat: str = field(default_factory=lambda: os.getenv('TELEGRAM_CHAT_ID', ''))

    def __post_init__(self):
        self.db_path = Path(self.db_path).resolve()
        primary = os.getenv('DATA_BACKEND') == 'google_sheets'
        if primary or self.db_path.exists():
            from db import connect
            with connect(self.db_path) as c:
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone():
                    row=c.execute("SELECT value FROM meta WHERE key='business_assumptions'").fetchone()
                    if row:
                        for key,value in business_values(json.loads(row[0])).items():
                            setattr(self,key,float(value) if key=='min_margin' else value)
        if not 0 <= self.fee_pct+self.payment_pct+self.conversion_pct < 1 or self.tax_pct > 1 or not 0 <= self.min_margin <= 1:
            raise ValueError('費率與淨利率門檻必須介於 0 與 1')
        if len(self.weights) != 4 or abs(sum(self.weights) - 1) > 1e-9:
            raise ValueError('四個權重的總和必須為 1')
