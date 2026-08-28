import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO v5.0 (KRX)", page_icon="🗺️", layout="wide")

# ==========================================
# 📱 모바일 최적화 커스텀 CSS
# ==========================================
st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container { padding: 1rem 0.5rem !important; }
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.3rem !important; }
    h3 { font-size: 1.1rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.3rem !important; word-break: break-word !important; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
}
div[data-testid="stExpander"] {
    border: 2px solid #e2e8f0;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# 한국식 컬러 스케일: 0% 중앙(회색), 상승(빨강), 하락(파랑)
COLOR_SCALE = [
    [0.0,  "#1e3a8a"],  # 파랑 (하락)
    [0.25, "#60a5fa"],  
    [0.50, "#e2e8f0"],  # 회색 (보합 0%)
    [0.75, "#f87171"],  
    [1.0,  "#dc2626"]   # 빨강 (상승)
]

# 국내 주요 10대 섹터 키워드 매핑
SECTOR_KEYWORDS = {
    "⚡ AI/반도체": ["반도체", "HBM", "AI", "전자", "칩", "테스", "에스에이엠티", "SK하이닉스", "삼성전자"],
    "🤖 로봇/자동화": ["로봇", "자동화", "스마트팩토리", "기계", "두산로보틱스", "레인보우로보틱스"],
    "🚢 조선/방산": ["조선", "방산", "중공업", "항공", "우주", "한화오션", "HD현대중공업"],
    "🧬 바이오/제약": ["제약", "바이오", "의약", "헬스케어", "삼성바이오로직스", "셀트리온"],
    "🚗 자동차/부품": ["자동차", "부품", "모빌리티", "현대차", "기아"],
    "💰 금융/지주": ["금융", "은행", "증권", "보험", "지주", "KB금융", "신한지주"],
    "🔋 2차전지/배터리": ["배터리", "2차전지", "에너지솔루션", "에코프로", "포스코퓨처엠"],
    "📱 IT/통신/게임": ["통신", "소프트웨어", "인터넷", "게임", "NAVER", "카카오", "SK텔레콤"],
    "🏗️ 건설/철강/화학": ["건설", "철강", "화학", "소재", "POSCO홀딩스", "LG화학"],
    "💡 기타 우량주": []
}

def map_krx_sector(name, dept_sector=""):
    text = f"{name} {dept_sector}"
    for sec, keywords in SECTOR_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return sec
    return "💡 기타 우량주"

@st.cache_data(ttl=3600, show_spinner=False)
def load_krx_universe_v5():
    try:
        x = fdr.StockListing('KRX')
        if x is not None and not x.empty:
            x = x.copy()
            x["Code"] = x["Code"].astype(str).str.zfill(6)
            x["Name"] = x["Name"].astype(str).str.strip()
            
            # 섹터 매핑
            dept_col = "Dept" if "Dept" in x.columns else "Sector" if "Sector" in x.columns else ""
            x["Sector_Mapped"] = x.apply(lambda r: map_krx_sector(r["Name"], str(r.get(dept_col, ""))), axis=1)
            
            if "Marcap" not in x.columns: x["Marcap"] = 0
            if "Volume" not in x.columns: x["Volume"] = 0
            return x.drop_duplicates("Code"), False
    except Exception:
        pass
    
    fallback_df = pd.DataFrame([{"Code": "005930", "Name": "삼성전자", "Sector_Mapped": "⚡ AI/반도체", "Marcap": 0, "Volume": 0}])
    return fallback_df, True

@st.cache_data(ttl=1800, show_spinner=False)
def get_price_v5(code):
    try:
        end = dt.date.today()
        start = end - dt.timedelta(days=365*5+45)
        code_str = str(code).strip().zfill(6)
        x = fdr.DataReader(code_str, start, end)
        if x is None or x.empty or "Close" not in x: return pd.DataFrame()
        x = x.copy()
        x.index = pd.to_datetime(x.index)
        return x.sort_index()
    except Exception:
        return pd.DataFrame()

def ret(close, days):
    if close.empty: return 0.0
    p = close[close.index <= close.index[-1] - pd.Timedelta(days=days)]
    if p.empty: return 0.0
    return (close.iloc[-1] / p.iloc[-1] - 1) * 100 if p.iloc[-1] > 0 else 0.0

def analyze_krx(code, name, sector_name="
