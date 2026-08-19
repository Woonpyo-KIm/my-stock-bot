import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO v4.4 (US Market)", page_icon="🗺️", layout="wide")

# ==========================================
# 📱 모바일 최적화 커스텀 CSS 주입
# ==========================================
st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.3rem !important; }
    h3 { font-size: 1.1rem !important; }
    [data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
        word-break: break-word !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

# 파랑-회색-빨강 컬러 스케일
COLOR_SCALE = [
    [0.0,  "#1e3a8a"],  # 최저점 (파랑)
    [0.25, "#60a5fa"],  
    [0.50, "#e2e8f0"],  # 중간점 (회색)
    [0.75, "#f87171"],  
    [1.0,  "#dc2626"]   # 최고점 (빨강)
]

# S&P 500 공식 섹터 영문 -> 이모지 매핑
SP500_SECTOR_MAP = {
    "Information Technology": "⚡ Technology",
    "Health Care": "🧬 Healthcare",
    "Financials": "💰 Financials",
    "Consumer Discretionary": "🛒 Consumer Disc.",
    "Communication Services": "📱 Communication",
    "Industrials": "🏗️ Industrials",
    "Consumer Staples": "🍔 Staples",
    "Energy": "🔋 Energy",
    "Real Estate": "🏠 Real Estate",
    "Utilities": "💡 Utilities",
    "Materials": "🧪 Materials"
}

# 기본 오프라인 fallback 종목 리스트
US_TOP_TICKERS = [
    ("AAPL", "Apple", "Information Technology"), ("MSFT", "Microsoft", "Information Technology"), 
    ("NVDA", "NVIDIA", "Information Technology"), ("GOOGL", "Alphabet", "Communication Services"),
    ("AMZN", "Amazon", "Consumer Discretionary"), ("META", "Meta", "Communication Services"), 
    ("BRK-B", "Berkshire", "Financials"), ("LLY", "Eli Lilly", "Health Care"),
    ("TSLA", "Tesla", "Consumer Discretionary"), ("V", "Visa", "Financials"), 
    ("JPM", "JPMorgan", "Financials"), ("UNH", "UnitedHealth", "Health Care"),
    ("WMT", "Walmart", "Consumer Staples"), ("MA", "Mastercard", "Financials"), 
    ("JNJ", "Johnson & Johnson", "Health Care"), ("PG", "P&G", "Consumer Staples"),
    ("HD", "Home Depot", "Consumer Discretionary"), ("ORCL", "Oracle", "Information Technology"), 
    ("CVX", "Chevron", "Energy"), ("MRK", "Merck", "Health Care"),
    ("KO", "Coca-Cola", "Consumer Staples"), ("PEP", "PepsiCo", "Consumer Staples"), 
    ("AVGO", "Broadcom", "Information Technology"), ("COST", "Costco", "Consumer Staples"),
    ("MCD", "McDonald's", "Consumer Discretionary"), ("CRM", "Salesforce", "Information Technology"), 
    ("AMD", "AMD", "Information Technology"), ("NFLX", "Netflix", "Communication Services"),
    ("DELL", "Dell Tech", "Information Technology"), ("ANET", "Arista Networks", "Information Technology")
]

@st.cache_data(ttl=3600, show_spinner=False)
def load_us_universe():
    try:
        x = fdr.StockListing('S&P500')
        if x is not None and not x.empty:
            x = x.copy()
            symbol_col = "Symbol" if "Symbol" in x.columns else "Ticker"
            name_col = "Name" if "Name" in x.columns else "Symbol"
            sector_col = "Sector" if "Sector" in x.columns else "Industry"
            
            x = x.rename(columns={symbol_col: "Code", name_col: "Name", sector_col: "RawSector"})
            x["Code"] = x["Code"].astype(str).str.strip().str.upper()
            x["Name"] = x["Name"].astype(str).str.strip()
            x["Sector"] = x["RawSector"].map(SP500_SECTOR_MAP).fillna("💡 Growth/Others")
            x["Marcap"] = 0
            x["Volume"] = 0
            return x.drop_duplicates("Code"), False
    except Exception:
        pass
    
    fallback_df = pd.DataFrame([
        {"Code": c, "Name": n, "Sector": SP500_SECTOR_MAP.get(s, "💡 Growth/Others"), "Marcap": 0, "Volume": 0} 
        for c, n, s in US_TOP_TICKERS
    ])
    return fallback_df, True

@st.cache_data(ttl=1800, show_spinner=False)
def get_price(ticker):
    try:
        end = dt.date.today(); start = end - dt.timedelta(days=365*5+45)
        x = fdr.DataReader(str(ticker).strip().upper(), start, end)
        if x is None or x.empty or "Close" not in x: return pd.DataFrame()
        x = x.copy(); x.index = pd.to_datetime(x.index); return x.sort_index()
    except Exception: return pd.DataFrame()

def ret(close, days):
    if close.empty: return 0.0
    p = close[close.index <= close.index[-1] - pd.Timedelta(days=days)]
    if p.empty: return 0.0
    return (close.iloc[-1] / p.iloc[-1] - 1) * 100 if p.iloc[-1] > 0 else 0.0

def analyze(ticker, name, sector_name="💡 Growth/Others", marcap=0, volume=0):
    ticker = str(ticker).upper()
    x = get_price(ticker)
    base = {
        "Ticker": ticker, 
        "Company": name, 
        "Sector": sector_name, 
        "Market Cap": float(marcap or 0), 
        "Volume": float(volume or 0), 
        "Chart": x.tail(100)
    }
    
    if x.empty: 
        return {**base, "Current Price": 0, "5Y Return": 0, "1Y Return": 0, "3M Return": 0, "1M Return": 0, "Vol Momentum": 0, "Volatility": 0, "Max Drawdown": 0, "Trend Score": 0, "Score": 0, "Action": "⚪ No Data", "Est. Market Price": 0}
    
    c = pd.to_numeric(x.Close, errors="coerce").dropna(); cur = float(c.iloc[-1])
    r5, r1, r3, r1m = [ret(c, d) for d in (1825, 365, 90, 30)]
    vm = 0
    if "Volume" in x:
        v = pd.to_numeric(x.Volume, errors="coerce").dropna()
        if len(v) >= 40 and v.iloc[-40:-20].mean() > 0: vm = (v.tail(20).mean() / v.iloc[-40:-20].mean() - 1) * 100
    
    ma20 = c.rolling(20).mean().iloc[-1]
    ma60 = c.rolling(60).mean().iloc[-1] if len(c) >= 60 else np.nan
    ma120 = c.rolling(120).mean().iloc[-1] if len(c) >= 120 else np.nan
    
    trend = (35 if cur > ma20 else 0) + (35 if pd.notna(ma60) and cur > ma60 else 0) + (30 if pd.notna(ma120) and cur > ma120 else 0)
    vol = float(c.pct_change().tail(60).std() * np.sqrt(252) * 100)
    dd = float((c / c.cummax() - 1).min() * 100)
    
    est_market_price = float(ma60) if pd.notna(ma60) else cur
    
    score = 50
    score += 15 if r5 >= 100 else 10 if r5 >= 50 else 5 if r5 > 0 else -10 if r5 < -30 else 0
    score += 20 if r1 >= 30 else 14 if r1 >= 15 else 7 if r1 > 0 else -12 if r1 < -20 else 0
    score += 15 if r3 >= 20 else 10 if r3 >= 10 else 5 if r3 > 0 else -10 if r3 < -15 else 0
    score += 10 if r1m >= 10 else 6 if r1m >= 3 else 2 if r1m > 0 else -8 if r1m < -10 else 0
    score += 10 if vm >= 50 else 6 if vm >= 20 else 2 if vm >= 0 else -5 if vm < -30 else 0
    score += trend * .20
    if vol > 80: score -= 5
    if dd < -35: score -= 5
    score = int(max(0, min(100, round(score))))
    
    # 모바일용 문구 간소화
    action = "🟢 Strong Buy" if score >= 82 and r3 > 5 and r1m > 0 else "🟢 Buy/Hold" if score >= 72 and r3 >= 0 else "🟡 Watch" if score >= 62 else "🟠 Trim" if score >= 48 else "🔴 Sell"
    
    return {
        **base, "Current Price": cur, "5Y Return": round(r5, 2), "1Y Return": round(r1, 2), 
        "3M Return": round(r3, 2), "1M Return": round(r1m, 2), "Vol Momentum": round(vm, 2), 
        "Volatility": round(vol, 2), "Max Drawdown": round(dd, 2), "Trend Score": int(trend), 
        "Score": score, "Action": action, "Est. Market Price": est_market_price
    }

@st.cache_data(ttl=1800, show_spinner=False)
def news(ticker, limit=5):
    out = []
    try:
        u = f"https://news.google.com/rss/search?q={requests.utils.quote(ticker + ' stock')}&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(u, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(r.content) if r.ok else None
        if root:
            for item in root.findall(".//item"):
                t = item.find("title")
                if t is not None and t.text:
                    z = t.text.replace(" - Yahoo Finance", "").strip()
                    if z not in out: out.append(z)
                if len(out) >= limit: break
    except Exception: pass
    return out or ["Failed to fetch recent news."]

def resolve(ticker, u):
    ticker = str(ticker).strip().upper()
    m = u[u.Code == ticker]
    if not m.empty:
        r = m.iloc[0]; return ticker, r.Name, str(r.Sector)
    return ticker, ticker, "💡 Growth/Others"

def outlook(df):
    a = df["Score"].mean(); r3 = df["3M Return"].mean(); r1 = df["1M Return"].mean()
    hot = (df["Score"] >= 75).mean() * 100; pos = (df["3M Return"] > 0).mean() * 100
    p = sum([a >= 70, r3 > 5, r1 > 2, hot >= 30, pos >= 60]) - sum([a < 50, r3 < -5, r1 < -2, hot < 10, pos < 40])
    label = "🟢 Strong Bull" if p >= 4 else "🟢 Mild Bull" if p >= 2 else "🔴 Strong Bear" if p <= -4 else "🟠 Bear/Defensive" if p <= -2 else "🟡 Neutral/Mixed"
    return label, f"Avg Score {a:.1f}, Avg 3M {r3:.1f}%, Avg 1M {r1:.1f}%, HOT ratio {hot:.1f}%, Positive 3M ratio {pos:.1f}%"

st.markdown("<h1 style='text-align:center'>🗺️ AI MARKET MAP PRO v4.4</h1>", unsafe_allow_html=True)
st.caption("🔥 Accurate Sector Mapping · Relative Dynamic Color Scaling · Mobile Optimized")

# ==========================================
# 🚀 입력창 패널 (Sidebar)
# ==========================================
if "portfolio_data_us" not in st.session_state:
    st.session_state.portfolio_data_us = pd.DataFrame([
        {"Ticker": "DELL", "Quantity": 20.0, "Avg Price": 90.00},
        {"Ticker": "TSLA", "Quantity": 10.0, "Avg Price": 150.50},
        {"Ticker": "NVDA", "Quantity": 25.0, "Avg Price": 80.00},
        {"Ticker": "AAPL", "Quantity": 0.0, "Avg Price": 0.0}
    ])

with st.sidebar:
    st.header("💼 My Portfolio Input")
    with st.form("portfolio_form_us"):
        st.caption("Enter US Tickers (e.g. AAPL, DELL).")
        edited_df = st.data_editor(
            st.session_state.portfolio_data_us,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="portfolio_editor_us"
        )
        run = st.form_submit_button("🗺️ Start PRO US Market Analysis", use_container_width=True, type="primary")

    st.divider()
    
    st.header("⚙️ Analysis Settings")
    st.markdown("**🔍 Technical Ranking Screening**")
    pool_size = st.slider("Initial Scan Pool (S&P 500 Caps)", 50, 300, 150, 50)
    n = st.slider("Final Displayed Stocks (Top Score)", 20, 100, 50, 10)
    workers = st.slider("Concurrent Requests (Speed)", 2, 8, 5)
    
    if st.button("🔄 Clear Cache", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ==========================================
# 🚀 분석 실행 및 화면 렌더링
# ==========================================
if run:
    st.session_state.portfolio_data_us = edited_df.copy()
    ps = edited_df.dropna(subset=["Ticker"]).to_dict(orient="records")
    ps = [p for p in ps if str(p.get("Ticker", "")).strip() != ""]

    u, fallback = load_us_universe()
    if fallback:
        st.warning("⚠️ S&P 500 listing failed. Falling back to core US mega-caps.")
            
    c = u.head(pool_size)
    jobs = {}
    for _, r in c.iterrows():
        jobs[r.Code] = (r.Name, r.Sector, 0, 0)
        
    for p in ps:
        code, name, sec = resolve(p["Ticker"], u)
        if code: jobs[code] = (name, sec, 0, 0)
        
    results = []; bar = st.progress(0)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs = {ex.submit(analyze, *((code,)+info)): code for code, info in jobs.items()}
        for i, f in enumerate(as_completed(fs), 1):
            try: results.append(f.result())
            except Exception: pass
            bar.progress(i / max(1, len(fs)))
    bar.empty(); df = pd.DataFrame(results)
    
    if df.empty: st.error("Failed to load US price data."); st.stop()
    
    p_rows = []
    for p in ps:
        code, _, _ = resolve(p["Ticker"], u)
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
        
    df["Owned"] = df.Ticker.isin([r["Ticker"] for r in p_rows])
    
    df_others = df[~df["Owned"]].sort_values(["Score", "3M Return"], ascending=False).head(n)
    df_port = df[df["Owned"]]
    
    df = pd.concat([df_port, df_others]).sort_values(["Score", "3M Return"], ascending=False).reset_index(drop=True)
    
    st.session_state.update(market_results_us=df, portfolio_results_us=pd.DataFrame(p_rows), analysis_complete_us=True)

if st.session_state.get("analysis_complete_us"):
    df = st.session_state.market_results_us; pf = st.session_state.portfolio_results_us
    ol, why = outlook(df)
    
    st.markdown("## 🧠 AI Market Outlook")
    o_col1, o_col2 = st.columns(2)
    o_col1.metric("Market Phase", ol)
    o_col2.metric("Avg Score", f"{df['Score'].mean():.1f}")
    o_col3, o_col4 = st.columns(2)
    o_col3.metric("Avg 3M Return", f"{df['3M Return'].mean():.1f}%")
    o_col4.metric("Avg 1M Return", f"{df['1M Return'].mean():.1f}%")
    st.info(why)
    
    top = df.iloc[0]; st.markdown("## 🏆 Ranking TOP PICK")
    t_col1, t_col2 = st.columns(2)
    t_col1.metric("Ticker", top.Ticker)
    t_col2.metric("Sector", top.Sector)
    t_col3, t_col4, t_col5 = st.columns(3)
    t_col3.metric("Score", f"{top['Score']} pts")
    t_col4.metric("3M Return", f"{top['3M Return']:.1f}%")
    t_col5.metric("Action", top.Action)
    
    t1, t2, t3, t4, t5 = st.tabs(["🗺️ Market Map", "🔥 Sectors", "💼 Portfolio", "🔍 Details", "🏆 Ranking"])
    
    with t1:
        x = df.copy()
        x["Display Name"] = x.apply(lambda r: "📌 " + r.Ticker if r.Owned else r.Ticker, axis=1)
        x["Prospect"] = pd.to_numeric(x["Score"], errors="coerce").clip(0, 100)
        x["Prospect Size"] = (x["Prospect"] + 1) ** 2

        # [수정] 스케일 버그 완벽 해결: 현재 화면 종목들의 최소점~최고점을 범위로 지정하여 상대 평가
        min_score = float(x["Prospect"].min())
        max_score = float(x["Prospect"].max())
        
        if min_score == max_score:
            min_score = max(0.0, min_score - 10.0)
            max_score = min(100.0, max_score + 10.0)
            
        dynamic_range = [min_score, max_score]

        fig = px.treemap(
            x, path=["Sector", "Display Name"], values="Prospect Size", color="Prospect",
            color_continuous_scale=COLOR_SCALE, 
            range_color=dynamic_range, 
            custom_data=["Prospect", "3M Return", "1M Return", "Action"]
        )
        fig.update_layout(height=600, margin=dict(t=0,l=0,r=0,b=0), coloraxis_showscale=True)
        fig.update_traces(
            textinfo="label",
            hovertemplate=(
                "<b>%{label}</b><br>Score: %{customdata[0]}<br>"
                "3M Return: %{customdata[1]:.1f}%<br>1M Return: %{customdata[2]:.1f}%<br>"
                "%{customdata[3]}<extra></extra>"
            )
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"📌 Relative Color Range: Min Score ({min_score:.0f} pts, Blue) ~ Max Score ({max_score:.0f} pts, Red)")
        
        st.divider()
        st.markdown("### 🖱️ Stock Quick View")
        sel_quick = st.selectbox("Select a Ticker from the map:", ["(None Selected)"] + df.Ticker.tolist())
        
        if sel_quick != "(None Selected)":
            r_quick = df[df.Ticker == sel_quick].iloc[0]
            
            reasons = []
            if r_quick["Trend Score"] >= 70: reasons.append("✅ **Trend Bullish:** Breaking above 20/60/120-day moving averages.")
            elif r_quick["Trend Score"] >= 35: reasons.append("⚠️ **Trend Neutral:** Recovering short-term MAs.")
            else: reasons.append("🚨 **Trend Bearish:** Trending below major MAs.")
            
            if r_quick['3M Return'] > 15: reasons.append(f"✅ **Return Momentum:** Surged {r_quick['3M Return']:.1f}% (3M).")
            elif r_quick['3M Return'] < -10: reasons.append(f"🚨 **Short-term Correction:** Dropped {r_quick['3M Return']:.1f}% (3M).")
            
            st.info("\n\n".join(reasons))
            
            st.markdown("**📈 Last 100 Days Price Trend**")
            if isinstance(r_quick["Chart"], pd.DataFrame) and not r_quick["Chart"].empty:
                st.line_chart(r_quick["Chart"][["Close"]].rename(columns={"Close": "Price ($)"}), use_container_width=True)
            
            st.markdown("**📰 Recent News**")
            for i, z in enumerate(news(sel_quick, 5), 1):
                st.markdown(f"- {z}")
    
    with t2:
        s = df.groupby("Sector").agg(Avg_Score=("Score","mean"), Avg_1M=("1M Return","mean"), Avg_3M=("3M Return","mean"), Avg_1Y=("1Y Return","mean"), Count=("Ticker","count")).reset_index().sort_values("Avg_Score", ascending=False)
        fig = px.bar(s.sort_values("Avg_Score"), x="Avg_Score", y="Sector", orientation="h", text="Avg_Score", color="Avg_Score", color_continuous_scale=COLOR_SCALE, range_color=dynamic_range)
        fig.update_traces(texttemplate='%{text:.1f}')
        fig.update_layout(height=500, coloraxis_showscale=False); st.plotly_chart(fig, use_container_width=True); st.dataframe(s.round(1), use_container_width=True, hide_index=True)
    
    with t3:
        if pf.empty: st.warning("No portfolio data.")
        else:
            ev = pf["Valuation"].sum(); cost = pf["Total Cost"].sum(); pnl = ev - cost
            p_col1, p_col2 = st.columns(2)
            p_col1.metric("Total Valuation", f"$ {ev:,.2f}")
            p_col2.metric("Total Cost", f"$ {cost:,.2f}")
            p_col3, p_col4 = st.columns(2)
            p_col3.metric("Total PnL", f"$ {pnl:,.2f}")
            p_col4.metric("Total Return", f"{(ev/cost-1)*100:.2f}%" if cost>0 else "-")
            
            cols = ["Ticker", "Company", "Quantity", "Avg Price", "Est. Market Price", "Valuation", "Total PnL", "Total Return", "Score", "Action", "3M Return"]
            pf_display = pf[cols].copy()
            for col in ["Avg Price", "Est. Market Price", "Valuation", "Total PnL"]:
                pf_display[col] = pf_display[col].apply(lambda x: f"$ {x:,.2f}")
                
            st.dataframe(pf_display, use_container_width=True, hide_index=True)
    
    with t4:
        sel = st.selectbox("Search Stock Details", df.Ticker.tolist()); r = df[df.Ticker == sel].iloc[0]
        d_col1, d_col2 = st.columns(2)
        d_col1.metric("Score", f"{r['Score']}")
        d_col2.metric("Current Price", f"$ {r['Current Price']:,.2f}")
        d_col3, d_col4, d_col5 = st.columns(3)
        d_col3.metric("1M Return", f"{r['1M Return']:.1f}%")
        d_col4.metric("3M Return", f"{r['3M Return']:.1f}%")
        d_col5.metric("Action", r["Action"])
        
        d_col6, d_col7 = st.columns(2)
        d_col6.metric("1Y Return", f"{r['1Y Return']:.1f}%")
        d_col7.metric("Est. Market Price", f"$ {r['Est. Market Price']:,.2f}")
        d_col8, d_col9 = st.columns(2)
        d_col8.metric("Trend Score", f"{r['Trend Score']}/100")
        d_col9.metric("Max Drawdown", f"{r['Max Drawdown']:.1f}%")
        
        if isinstance(r["Chart"], pd.DataFrame) and not r["Chart"].empty: st.line_chart(r["Chart"][["Close"]].rename(columns={"Close":"Price ($)"}), use_container_width=True)
        st.markdown("### 📰 Recent News")
        for i, z in enumerate(news(sel, 5), 1): st.markdown(f"**{i}.** {z}")
    
    with t5:
        cols = ["Ticker", "Company", "Sector", "Score", "Action", "Current Price", "Est. Market Price", "5Y Return", "1Y Return", "3M Return", "1M Return", "Max Drawdown"]
        q = df[cols].copy(); q.insert(0, "Rank", range(1, len(q)+1))
        for col in ["Current Price", "Est. Market Price"]:
            q[col] = q[col].apply(lambda x: f"$ {x:,.2f}")
        st.dataframe(q, use_container_width=True, hide_index=True)
else:
    st.info("👆 Open the sidebar (top left) to enter your portfolio and click **Start PRO US Market Analysis** to begin.")
