import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO V3 (KRX)", page_icon="🗺️", layout="wide")

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
    [0.2
