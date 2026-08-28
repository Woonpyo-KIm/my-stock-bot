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
    [0.0, "#1e3a8a"],  # 파랑 (하락)
    [0.25, "#60a5fa"],  
    [0.50, "#e2e8f0"],  # 회색 (보합 0%)
    [0.75, "#f87171"],  
    [1.0, "#dc2626"]   # 빨강 (상승)
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
def load_krx_universe_v3():
    try:
        x = fdr.StockListing('KRX')
        if x is not None and not x.empty:
            x = x.copy()
            x["Code"] = x["Code"].astype(str).str.zfill(6)
            x["Name"] = x["Name"].astype(str).str.strip()
            
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
def get_price_v3(code):
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

def analyze_krx(code, name, sector_name="💡 기타 우량주", marcap=0, volume=0):
    code = str(code).zfill(6)
    x = get_price_v3(code)
    
    base = {"Ticker": code, "Company": name, "Sector": sector_name, "Chart": pd.DataFrame()}
    if x.empty: 
        return {**base, "Current Price": 0, "1Y Return": 0, "3M Return": 0, "1M Return": 0, 
                "Trend Score": 0, "Score": 0, "Action": "⚪ 데이터 없음", "BB Breakout": False, "Max Drawdown": 0.0}
    
    c = pd.to_numeric(x.Close, errors="coerce").dropna()
    cur = float(c.iloc[-1])
    
    ma20_series = c.rolling(20).mean()
    std20_series = c.rolling(20).std()
    upper_band_series = ma20_series + (std20_series * 2)
    lower_band_series = ma20_series - (std20_series * 2)
    
    cur_upper = upper_band_series.iloc[-1] if len(upper_band_series) >= 20 else cur
    cur_ma20 = ma20_series.iloc[-1] if len(ma20_series) >= 20 else cur
    
    is_bb_breakout = (cur > cur_upper) if pd.notna(cur_upper) else False
    
    chart_df = x.tail(100).copy()
    chart_df['MA20'] = ma20_series
    chart_df['Upper Band'] = upper_band_series
    chart_df['Lower Band'] = lower_band_series
    base["Chart"] = chart_df[['Close', 'MA20', 'Upper Band', 'Lower Band']]

    r5, r1, r3, r1m = [ret(c, d) for d in (1825, 365, 90, 30)]
    
    ma60 = c.rolling(60).mean().iloc[-1] if len(c) >= 60 else np.nan
    ma120 = c.rolling(120).mean().iloc[-1] if len(c) >= 120 else np.nan
    
    trend = (35 if cur > cur_ma20 else 0) + (35 if pd.notna(ma60) and cur > ma60 else 0) + (30 if pd.notna(ma120) and cur > ma120 else 0)
    vol = float(c.pct_change().tail(60).std() * np.sqrt(252) * 100)
    dd = float((c / c.cummax() - 1).min() * 100)
    
    score = 50
    score += 15 if r5 >= 100 else 10 if r5 >= 50 else 5 if r5 > 0 else -10 if r5 < -30 else 0
    score += 20 if r1 >= 30 else 14 if r1 >= 15 else 7 if r1 > 0 else -12 if r1 < -20 else 0
    score += 15 if r3 >= 20 else 10 if r3 >= 10 else 5 if r3 > 0 else -10 if r3 < -15 else 0
    score += 10 if r1m >= 10 else 6 if r1m >= 3 else 2 if r1m > 0 else -8 if r1m < -10 else 0
    score += trend * .20
    
    if is_bb_breakout: score += 15 
    if vol > 80: score -= 5
    if dd < -35: score -= 5
    score = int(max(0, min(100, round(score))))
    
    if is_bb_breakout and score >= 75: action = "🚀 BB 상단 돌파 (강력매수)"
    elif score >= 80: action = "🟢 강력 매수"
    elif score >= 70: action = "🟢 매수/보유"
    elif score >= 58: action = "🟡 관망"
    elif score >= 45: action = "🟠 비중 축소"
    else: action = "🔴 매도"
    
    return {
        **base, "Current Price": cur, "1Y Return": round(r1, 2), "3M Return": round(r3, 2), 
        "1M Return": round(r1m, 2), "Trend Score": int(trend), "Score": score, 
        "Action": action, "BB Breakout": is_bb_breakout, "Max Drawdown": round(dd, 2)
    }

@st.cache_data(ttl=1800, show_spinner=False)
def news_kr(stock_name, limit=5):
    out = []
    try:
        u = f"https://news.google.com/rss/search?q={requests.utils.quote(stock_name + ' 주식 전망')}&hl=ko&gl=KR&ceid=KR:ko"
        r = requests.get(u, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(r.content) if r.ok else None
        if root:
            for item in root.findall(".//item"):
                t = item.find("title")
                if t is not None and t.text:
                    z = t.text.replace(" - 네이버", "").replace(" - YTN", "").strip()
                    if z not in out: out.append(z)
                if len(out) >= limit: break
    except Exception: pass
    return out or ["최신 뉴스 수집 불가"]

def resolve_krx(input_text, u):
    text = str(input_text).strip()
    if text.isdigit():
        code = text.zfill(6)
        m = u[u.Code == code]
        if not m.empty:
            r = m.iloc[0]
            return code, r["Name"], str(r.get("Sector_Mapped", "💡 기타 우량주"))
        return code, code, "💡 기타 우량주"
    
    m = u[u.Name.str.contains(text, case=False, na=False)]
    if not m.empty:
        r = m.iloc[0]
        return r["Code"], r["Name"], str(r.get("Sector_Mapped", "💡 기타 우량주"))
    
    return text, text, "💡 기타 우량주"

def outlook(df):
    a = df["Score"].mean(); r3 = df["3M Return"].mean(); r1 = df["1M Return"].mean()
    hot = (df["Score"] >= 75).mean() * 100; pos = (df["3M Return"] > 0).mean() * 100
    p = sum([a >= 70, r3 > 5, r1 > 2, hot >= 30, pos >= 60]) - sum([a < 50, r3 < -5, r1 < -2, hot < 10, pos < 40])
    label = "🔥 강한 상승장 (Bull)" if p >= 4 else "☀️ 완만한 상승장" if p >= 2 else "🧊 강한 하락장 (Bear)" if p <= -4 else "❄️ 약세/방어장" if p <= -2 else "☁️ 혼조세/관망"
    return label, f"평균 점수 {a:.1f}점 | 3개월 평균 {r3:.1f}% | 1개월 평균 {r1:.1f}% | 주도주 비중 {hot:.1f}%"

# ==========================================
# 🚀 메인 화면 헤더
# ==========================================
st.markdown("<h1 style='text-align:center'>🗺️ AI MARKET MAP PRO V3 (KRX)</h1>", unsafe_allow_html=True)
st.caption("🔥 볼린저 밴드 상단 돌파 로직 탑재 · 시가총액/점수 기반 트리맵 · 한국 증시 최적화")

if "portfolio_data_krx" not in st.session_state:
    st.session_state.portfolio_data_krx = pd.DataFrame([
        {"Stock": "두산로보틱스", "Quantity": 10.0, "Avg Price": 75000.0},
        {"Stock": "한화오션", "Quantity": 20.0, "Avg Price": 28000.0},
        {"Stock": "테스", "Quantity": 30.0, "Avg Price": 21000.0},
        {"Stock": "에스에이엠티", "Quantity": 100.0, "Avg Price": 3200.0}
    ])

# ==========================================
# 🚀 사이드바 (분석 설정)
# ==========================================
with st.sidebar:
    st.header("⚙️ 분석 설정")
    st.markdown("**🔍 기술적 스크리닝 범위**")
    pool_size = st.slider("최초 스캔 종목 수 (KRX 시총 상위)", 50, 300, 150, 50)
    n = st.slider("최종 표출 종목 수 (상위 점수)", 20, 100, 40, 10)
    workers = st.slider("병렬 수집 속도 (스레드)", 2, 8, 5)
    
    st.divider()
    if st.button("🔄 캐시 초기화", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ==========================================
# 🚀 포트폴리오 입력창 (Expander)
# ==========================================
is_expanded = not st.session_state.get("analysis_complete_krx", False)

with st.expander("💼 내 보유 포트폴리오 입력 (클릭하여 열기/접기)", expanded=is_expanded):
    st.markdown("### 📝 국내 보유 종목 입력")
    st.caption("셀을 클릭하여 종목명(예: 삼성전자, 두산로보틱스) 또는 6자리 코드를 입력하세요.")
    
    with st.form("portfolio_form_krx"):
        edited_df = st.data_editor(
            st.session_state.portfolio_data_krx, 
            num_rows="dynamic", 
            use_container_width=True, 
            hide_index=True, 
            column_config={
                "Stock": st.column_config.TextColumn("종목명 / 코드", help="예: 두산로보틱스, 005930", required=True),
                "Quantity": st.column_config.NumberColumn("보유 수량", help="보유 주식 수", min_value=0.0),
                "Avg Price": st.column_config.NumberColumn("매수 평균가 (원)", help="평균 매수 단가", min_value=0.0, format="%d 원")
            },
            key="portfolio_editor_krx"
        )
        run = st.form_submit_button("🗺️ 저장 및 PRO V3 국내 증시 분석 시작", use_container_width=True, type="primary")

# ==========================================
# 🚀 메인 분석 로직
# ==========================================
if run:
    st.session_state.portfolio_data_krx = edited_df.copy()
    ps = edited_df.dropna(subset=["Stock"]).to_dict(orient="records")
    ps = [p for p in ps if str(p.get("Stock", "")).strip() != ""]

    u, fallback = load_krx_universe_v3()
    c = u.head(pool_size)
    jobs = {}
    
    for _, r in c.iterrows():
        jobs[r.Code] = (r["Name"], r.get("Sector_Mapped", "💡 기타 우량주"), 0, 0)
        
    for p in ps:
        input_text = str(p["Stock"])
        code, name, sec = resolve_krx(input_text, u)
        jobs[code] = (name, sec, 0, 0)
        
    results = []; bar = st.progress(0)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs = {ex.submit(analyze_krx, *((code,)+info)): code for code, info in jobs.items()}
        for i, f in enumerate(as_completed(fs), 1):
            try: results.append(f.result())
            except Exception: pass
            bar.progress(i / max(1, len(fs)))
            
    bar.empty(); df = pd.DataFrame(results)
    
    if df.empty: st.error("주가 데이터를 불러오는 데 실패했습니다."); st.stop()
    
    p_rows = []
    for p in ps:
        input_text = str(p["Stock"])
        code, name, _ = resolve_krx(input_text, u)
        m = df[df.Ticker == code]
        if m.empty: continue
        r = m.iloc[0].to_dict()
        q = float(p.get("Quantity", 0))
        a = float(p.get("Avg Price", 0))
        cur = r["Current Price"]
        r.update({
            "Quantity": q, "Avg Price": a, "Valuation": cur * q, "Total Cost": a * q,
            "Total PnL": cur * q - a * q, "Total Return": ((cur / a - 1) * 100 if a > 0 else np.nan),
            "Owned": True
        })
        p_rows.append(r)
        
    my_codes = [resolve_krx(str(p["Stock"]), u)[0] for p in ps]
    df["Owned"] = df.Ticker.isin(my_codes)
    
    df_others = df[~df["Owned"]].sort_values(["Score", "3M Return"], ascending=False).head(n)
    df_port = df[df["Owned"]]
    df = pd.concat([df_port, df_others]).sort_values(["Score", "3M Return"], ascending=False).reset_index(drop=True)
    
    st.session_state.update(market_results_krx=df, portfolio_results_krx=pd.DataFrame(p_rows), analysis_complete_krx=True)
    st.rerun()

# ==========================================
# 🚀 결과 대시보드 렌더링
# ==========================================
if st.session_state.get("analysis_complete_krx"):
    df = st.session_state.market_results_krx; pf = st.session_state.portfolio_results_krx
    ol, why = outlook(df)
    
    st.markdown("## 🧠 AI 시장 국면 진단")
    o_col1, o_col2 = st.columns(2)
    o_col1.metric("시장 상태", ol)
    o_col2.metric("전체 평균 점수", f"{df['Score'].mean():.1f} 점")
    o_col3, o_col4 = st.columns(2)
    o_col3.metric("3개월 평균 수익률", f"{df['3M Return'].mean():.1f}%")
    o_col4.metric("1개월 평균 수익률", f"{df['1M Return'].mean():.1f}%")
    st.info(why)
    
    top = df.iloc[0]; st.markdown("## 🏆 오늘의 AI 최우수 픽 (1등 추천주)")
    t_col1, t_col2 = st.columns(2)
    t_col1.metric("종목명", top.Company)
    t_col2.metric("섹터", top.Sector)
    t_col3, t_col4, t_col5 = st.columns(3)
    t_col3.metric("AI 점수", f"{top['Score']} 점")
    t_col4.metric("1개월 수익률", f"{top['1M Return']:.1f}%")
    t_col5.metric("시그널", top.Action)
    
    t1, t2, t3, t4 = st.tabs(["🗺️ 마켓 트리맵", "🔥 섹터 순위", "💼 내 포트폴리오", "🔍 전체 상세 순위"])
    
    with t1:
        x = df.copy()
        x["Display Name"] = x.apply(
            lambda r: f"📌{'🚀' if r['BB Breakout'] else ''} {r.Company}" if r.Owned else f"{'🚀 ' if r['BB Breakout'] else ''}{r.Company}", axis=1
        )
        
        x["Prospect Size"] = (pd.to_numeric(x["Score"], errors="coerce").clip(0, 100) + 1) ** 2

        max_abs_ret = max(abs(x["1M Return"].min()), abs(x["1M Return"].max()))
        if max_abs_ret == 0: max_abs_ret = 1.0
        
        fig = px.treemap(
            x, path=["Sector", "Display Name"], values="Prospect Size", color="1M Return", 
            color_continuous_scale=COLOR_SCALE, 
            range_color=[-max_abs_ret, max_abs_ret], 
            custom_data=["Score", "3M Return", "1M Return", "Action", "Company"]
        )
        fig.update_layout(height=600, margin=dict(t=0,l=0,r=0,b=0), coloraxis_showscale=True)
        fig.update_traces(
            textinfo="label",
            hovertemplate="<b>%{customdata[4]}</b><br>점수: %{customdata[0]}점<br>1개월 수익률: %{customdata[2]:.1f}%<br>상태: %{customdata[3]}<extra></extra>"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("📌 마크: 내 보유 종목 | 🚀 마크: 볼린저 밴드 상단 돌파 | 색상: 1개월 수익률 (0% 회색, 상승 빨강, 하락 파랑)")
        
        st.divider()
        st.markdown("### 🖱️ 종목 차트 & BB 밴드 Quick View")
        sel_quick = st.selectbox("조회할 종목을 선택하세요:", ["(선택 안함)"] + df.Company.tolist())
        if sel_quick != "(선택 안함)":
            r_quick = df[df.Company == sel_quick].iloc[0]
            if isinstance(r_quick["Chart"], pd.DataFrame) and not r_quick["Chart"].empty:
                st.markdown(f"#### 📉 {r_quick.Company} 최근 100일 차트 & 볼린저 밴드")
                st.caption("주가(Close), 20일 이동평균선(MA20), 상단 밴드(Upper Band), 하단 밴드(Lower Band)")
                st.line_chart(r_quick["Chart"], use_container_width=True)
            st.markdown("**📰 최근 관련 뉴스**")
            for z in news_kr(sel_quick, 3): st.markdown(f"- {z}")
    
    with t2:
        s = df.groupby("Sector").agg(Avg_Score=("Score","mean"), Avg_1M=("1M Return","mean")).reset_index().sort_values("Avg_Score", ascending=False)
        fig = px.bar(
            s.sort_values("Avg_Score"), x="Avg_Score", y="Sector", orientation="h", text="Avg_Score", 
            color="Avg_1M", color_continuous_scale=COLOR_SCALE, range_color=[-max_abs_ret, max_abs_ret]
        )
        fig.update_traces(texttemplate='%{text:.1f}점')
        fig.update_layout(height=500, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with t3:
        if pf.empty: st.warning("포트폴리오 데이터가 없습니다.")
        else:
            ev = pf["Valuation"].sum(); cost = pf["Total Cost"].sum(); pnl = ev - cost
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.metric("총 평가 금액", f"{ev:,.0f} 원")
            p_col2.metric("총 매수 금액", f"{cost:,.0f} 원")
            p_col3.metric("총 평가 손익", f"{pnl:,.0f} 원", delta=f"{(pnl/cost*100 if cost>0 else 0):.2f}%")
            
            cols = ["Company", "Avg Price", "Current Price", "Valuation", "Total Return", "Score", "Action"]
            pf_display = pf[cols].copy()
            pf_display = pf_display.rename(columns={
                "Company": "종목명", "Avg Price": "평균 단가", "Current Price": "현재가", 
                "Valuation": "평가 금액", "Total Return": "수익률 (%)", "Score": "AI 점수", "Action": "행동 지침"
            })
            for col in ["평균 단가", "현재가", "평가 금액"]:
                pf_display[col] = pf_display[col].apply(lambda x: f"{x:,.0f} 원")
            st.dataframe(pf_display, use_container_width=True, hide_index=True)
            
    with t4:
        cols = ["Company", "Sector", "Score", "Action", "BB Breakout", "Current Price", "1Y Return", "3M Return", "Max Drawdown"]
        q = df[cols].copy(); q.insert(0, "순위", range(1, len(q)+1))
        q = q.rename(columns={
            "Company": "종목명", "Sector": "섹터", "Score": "점수", "Action": "시그널", 
            "BB Breakout": "BB 상단돌파", "Current Price": "현재가", "1Y Return": "1년 수익률", 
            "3M Return": "3개월 수익률", "Max Drawdown": "최대 낙폭"
        })
        q["현재가"] = q["현재가"].apply(lambda x: f"{x:,.0f} 원")
        st.dataframe(q, use_container_width=True, hide_index=True)
else:
    st.info("👆 위 포트폴리오 입력칸에 종목을 입력하고 **저장 및 PRO V3 국내 증시 분석 시작** 버튼을 누르세요.")
