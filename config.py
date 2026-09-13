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
    if result['fee_pct']>=1 or result['min_margin']>1:raise ValueError('費率須小於 100%，最低淨利率不可超過 100%')
    return result

@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv('DB_PATH', str(ROOT / 'data/live.sqlite3'))))
    token: str = field(default_factory=lambda: os.getenv('DISCOGS_TOKEN', ''))
    user_agent: str = field(default_factory=lambda: os.getenv('DISCOGS_USER_AGENT', 'SimplesRecordResearch/0.1'))
    currency: str = field(default_factory=lambda: os.getenv('MARKET_CURRENCY', 'USD').upper())
    fee_pct: Decimal = field(default_factory=lambda: money(os.getenv('TOTAL_FEE_PCT', '0.12')))
    shipping: Decimal = field(default_factory=lambda: money(os.getenv('SHIPPING_COST_TWD', '600')))
    packing: Decimal = field(default_factory=lambda: money(os.getenv('PACKING_COST_TWD', '50')))
    reserve: Decimal = field(default_factory=lambda: money(os.getenv('RISK_RESERVE_TWD', '0')))
    min_margin: float = field(default_factory=lambda: float(os.getenv('MIN_MARGIN', '.15')))
    hot_ratio: float = field(default_factory=lambda: float(os.getenv('HOT_RATIO', '3')))
    max_supply: int = field(default_factory=lambda: int(os.getenv('MAX_SUPPLY', '3')))
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
        if not 0 <= self.fee_pct < 1 or not 0 <= self.min_margin <= 1:
            raise ValueError('費率與淨利率門檻必須介於 0 與 1')
        if len(self.weights) != 4 or abs(sum(self.weights) - 1) > 1e-9:
            raise ValueError('四個權重的總和必須為 1')
