import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO v4.3 (US Market)", page_icon="🗺️", layout="wide")

COLOR_SCALE = [
    [0.0,  "#1e3a8a"],  
    [0.25, "#60a5fa"],  
    [0.50, "#e2e8f0"],  
    [0.75, "#f87171"],  
    [1.0,  "#dc2626"]   
]

# US Market Sectors mapping by Tickers
SECTORS = {
    "⚡ Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CSCO", "AMD", "QCOM", "TXN", "IBM", "AMAT", "NOW", "INTU", "PLTR"],
    "🛒 Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "BKNG", "TJX"],
    "🧬 Healthcare": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "PFE", "ABT", "DHR"],
    "💰 Financials": ["JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "C"],
    "📱 Communication": ["GOOGL", "GOOG", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "CHTR"],
    "🏗️ Industrials": ["GE", "CAT", "UBER", "BA", "HON", "UNP", "UPS", "LMT", "RTX"],
    "🍔 Consumer Staples": ["WMT", "PG", "COST", "KO", "PEP", "PM", "TGT", "MO"],
    "🔋 Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX"],
    "🏠 Real Estate & Utils": ["PLD", "AMT", "EQIX", "NEE", "DUK", "SO"],
    "🧪 Materials": ["LIN", "SHW", "FCX", "ECL", "NEM"]
}

# US Mega-cap universe for scanning pool (Ticker, Company Name, Mock Weight)
US_TOP_TICKERS = [
    ("AAPL", "Apple", 3000), ("MSFT", "Microsoft", 3000), ("NVDA", "NVIDIA", 2500),
    ("GOOGL", "Alphabet", 1500), ("AMZN", "Amazon", 1500), ("META", "Meta", 1000),
    ("BRK-B", "Berkshire", 800), ("LLY", "Eli Lilly", 700), ("TSLA", "Tesla", 600),
    ("V", "Visa", 500), ("JPM", "JPMorgan", 500), ("UNH", "UnitedHealth", 450),
    ("WMT", "Walmart", 450), ("MA", "Mastercard", 400), ("JNJ", "Johnson & Johnson", 400),
    ("PG", "Procter & Gamble", 400), ("HD", "Home Depot", 350), ("ORCL", "Oracle", 350),
    ("CVX", "Chevron", 300), ("MRK", "Merck", 300), ("KO", "Coca-Cola", 250),
    ("PEP", "PepsiCo", 250), ("AVGO", "Broadcom", 600), ("COST", "Costco", 300),
    ("MCD", "McDonald's", 200), ("CRM", "Salesforce", 250), ("AMD", "AMD", 250),
    ("NFLX", "Netflix", 250), ("ADBE", "Adobe", 250), ("DIS", "Walt Disney", 200),
    ("INTC", "Intel", 150), ("BA", "Boeing", 150), ("CSCO", "Cisco", 200),
    ("QCOM", "Qualcomm", 200), ("TXN", "Texas Inst", 150), ("IBM", "IBM", 150),
    ("AMAT", "Applied Mat", 100), ("NOW", "ServiceNow", 100), ("INTU", "Intuit", 100),
    ("UBER", "Uber", 100), ("CAT", "Caterpillar", 100), ("GE", "Gen Electric", 100),
    ("HON", "Honeywell", 100), ("UNP", "Union Pacific", 100), ("UPS", "UPS", 100),
    ("LMT", "Lockheed", 100), ("RTX", "RTX Corp", 100), ("XOM", "ExxonMobil", 300),
    ("COP", "ConocoPhillips", 100), ("SLB", "Schlumberger", 100), ("PLD", "Prologis", 100),
    ("AMT", "American Tower", 100), ("NEE", "NextEra Energy", 100), ("LIN", "Linde", 100),
    ("SHW", "Sherwin-Williams", 100), ("FCX", "Freeport", 100),
    ("NKE", "Nike", 100), ("SBUX", "Starbucks", 100), ("BKNG", "Booking", 100),
    ("TJX", "TJX Companies", 100), ("ABBV", "AbbVie", 200), ("TMO", "Thermo Fisher", 150),
    ("PFE", "Pfizer", 150), ("ABT", "Abbott", 150), ("DHR", "Danaher", 150),
    ("BAC", "Bank of America", 200), ("WFC", "Wells Fargo", 100), ("GS", "Goldman Sachs", 100),
    ("MS", "Morgan Stanley", 100), ("AXP", "American Express", 100), ("C", "Citigroup", 100),
    ("CMCSA", "Comcast", 150), ("VZ", "Verizon", 150), ("T", "AT&T", 150)
]

def load_us_universe():
    return pd.DataFrame([{"Code": c, "Name": n, "Marcap": w * 1e9, "Volume": 0} for c, n, w in US_TOP_TICKERS])

@st.cache_data(ttl=1800, show_spinner=False)
def get_price(ticker):
    try:
        end = dt.date.today(); start = end - dt.timedelta(days=365*5+45)
        x = fdr.DataReader(str(ticker).strip().upper(), start, end)
        if x is None or x.empty or "Close" not in x: return pd.DataFrame()
        x = x.copy(); x.index = pd.to_datetime(x.index); return x.sort_index()
    except Exception: return pd.DataFrame()

def sector(ticker):
    for s, ks in SECTORS.items():
        if str(ticker).upper() in ks: return s
    return "💡 Others / Growth"

def ret(close, days):
    if close.empty: return 0.0
    p = close[close.index <= close.index[-1] - pd.Timedelta(days=days)]
    if p.empty: return 0.0
    return (close.iloc[-1] / p.iloc[-1] - 1) * 100 if p.iloc[-1] > 0 else 0.0

def analyze(ticker, name, marcap=0, volume=0):
    ticker = str(ticker).upper()
    x = get_price(ticker); base = {"Ticker": ticker, "Company": name, "Sector": sector(ticker), "Market Cap": float(marcap or 0), "Volume": float(volume or 0), "Chart": x.tail(100)}
    if x.empty: return {**base, "Current Price": 0, "5Y Return": 0, "1Y Return": 0, "3M Return": 0, "1M Return": 0, "Vol Momentum": 0, "Volatility": 0, "Max Drawdown": 0, "Trend Score": 0, "Score": 0, "Action": "⚪ Insufficient Data", "Est. Market Price": 0}
    c = pd.to_numeric(x.Close, errors="coerce").dropna(); cur = float(c.iloc[-1])
    r5, r1, r3, r1m = [ret(c, d) for d in (1825, 365, 90, 30)]
    vm = 0
    if "Volume" in x:
        v = pd.to_numeric(x.Volume, errors="coerce").dropna()
        if len(v) >= 40 and v.iloc[-40:-20].mean() > 0: vm = (v.tail(20).mean() / v.iloc[-40:-20].mean() - 1) * 100
    ma20 = c.rolling(20).mean().iloc[-1]; ma60 = c.rolling(60).mean().iloc[-1] if len(c) >= 60 else np.nan; ma120 = c.rolling(120).mean().iloc[-1] if len(c) >= 120 else np.nan
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
    action = "🟢 Strong Hold / Buy More" if score >= 82 and r3 > 5 and r1m > 0 else "🟢 Hold" if score >= 72 and r3 >= 0 else "🟡 Watch / Accumulate" if score >= 62 else "🟠 Trim Position" if score >= 48 else "🔴 Sell / Replace"
    
    return {**base, "Current Price": cur, "5Y Return": round(r5, 2), "1Y Return": round(r1, 2), "3M Return": round(r3, 2), "1M Return": round(r1m, 2), "Vol Momentum": round(vm, 2), "Volatility": round(vol, 2), "Max Drawdown": round(dd, 2), "Trend Score": int(trend), "Score": score, "Action": action, "Est. Market Price": est_market_price}

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
        r = m.iloc[0]; return ticker, r.Name, float(r.Marcap or 0)
    # Even if not in predefined universe, allow search via fdr.DataReader
    return ticker, ticker, 0

def outlook(df):
    a = df["Score"].mean(); r3 = df["3M Return"].mean(); r1 = df["1M Return"].mean()
    hot = (df["Score"] >= 75).mean() * 100; pos = (df["3M Return"] > 0).mean() * 100
    p = sum([a >= 70, r3 > 5, r1 > 2, hot >= 30, pos >= 60]) - sum([a < 50, r3 < -5, r1 < -2, hot < 10, pos < 40])
    label = "🟢 Strong Bull" if p >= 4 else "🟢 Mild Bull" if p >= 2 else "🔴 Strong Bear" if p <= -4 else "🟠 Bear/Defensive" if p <= -2 else "🟡 Neutral/Mixed"
    return label, f"Avg Score {a:.1f}, Avg 3M {r3:.1f}%, Avg 1M {r1:.1f}%, HOT ratio {hot:.1f}%, Positive 3M ratio {pos:.1f}%"

st.markdown("<h1 style='text-align:center'>🗺️ AI MARKET MAP PRO v4.3 (US Edition)</h1>", unsafe_allow_html=True)
st.caption("🔥 Technical Ranking Screening · Quick View · Auto 50:50 Color Scale · Persistent US Portfolio")

with st.sidebar:
    st.header("⚙️ Analysis Settings")
    st.markdown("**🔍 Technical Ranking Screening**")
    
    pool_size = st.slider("Initial Scan Pool (Top US Caps)", 20, len(US_TOP_TICKERS), 70, 10)
    n = st.slider("Final Displayed Stocks (Top Score)", 10, len(US_TOP_TICKERS), 30, 5)
    
    st.divider()
    workers = st.slider("Concurrent Requests", 2, 8, 5)
    
    if st.button("🔄 Clear Cache", use_container_width=True):
        st.cache_data.clear(); st.rerun()

if "portfolio_data_us" not in st.session_state:
    st.session_state.portfolio_data_us = pd.DataFrame([
        {"Ticker": "TSLA", "Quantity": 10.0, "Avg Price": 150.50},
        {"Ticker": "NVDA", "Quantity": 25.0, "Avg Price": 80.00},
        {"Ticker": "AAPL", "Quantity": 0.0, "Avg Price": 0.0},
        {"Ticker": "PLTR", "Quantity": 0.0, "Avg Price": 0.0}
    ])

with st.form("portfolio_form_us"):
    st.markdown("### 💼 My US Portfolio Input")
    st.caption("Use exact Tickers (e.g., AAPL). Click cells to edit. Navigation won't lose your data.")
    
    edited_df = st.data_editor(
        st.session_state.portfolio_data_us,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="portfolio_editor_us"
    )
    
    run = st.form_submit_button("🗺️ Start PRO US Market Analysis", use_container_width=True, type="primary")

if run:
    st.session_state.portfolio_data_us = edited_df.copy()
    ps = edited_df.dropna(subset=["Ticker"]).to_dict(orient="records")
    ps = [p for p in ps if str(p.get("Ticker", "")).strip() != ""]

    u = load_us_universe()
            
    c = u.head(pool_size)
    jobs = {}
    for _, r in c.iterrows():
        jobs[r.Code] = (r.Name, float(r.Marcap), float(r.Volume))
        
    for p in ps:
        code, name, m = resolve(p["Ticker"], u)
        if code: jobs[code] = (name, m, 0)
        
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
    a, b, c, d = st.columns(4); a.metric("Market Phase", ol); b.metric("Avg Score", f"{df['Score'].mean():.1f}"); c.metric("Avg 3M Return", f"{df['3M Return'].mean():.1f}%"); d.metric("Avg 1M Return", f"{df['1M Return'].mean():.1f}%")
    st.info(why)
    top = df.iloc[0]; st.markdown("## 🏆 Ranking TOP PICK")
    a, b, c, d, e = st.columns(5); a.metric("Ticker", top.Ticker); b.metric("Sector", top.Sector); c.metric("Score", f"{top['Score']} pts"); d.metric("3M Return", f"{top['3M Return']:.1f}%"); e.metric("Action", top.Action)
    t1, t2, t3, t4, t5 = st.tabs(["🗺️ Market Map", "🔥 Sectors", "💼 Portfolio", "🔍 Details", "🏆 Ranking"])
    
    with t1:
        x = df.copy()
        x["Market"] = "US Equities"
        x["Display Name"] = x.apply(lambda r: "📌 " + r.Ticker if r.Owned else r.Ticker, axis=1)
        x["Prospect"] = pd.to_numeric(x["Score"], errors="coerce").clip(0, 100)
        x["Prospect Size"] = (x["Prospect"] + 1) ** 2

        median_score = x["Prospect"].median()
        max_diff = max(x["Prospect"].max() - median_score, median_score - x["Prospect"].min())
        if max_diff == 0: max_diff = 1 
        dynamic_range = [median_score - max_diff, median_score + max_diff]

        fig = px.treemap(
            x, path=["Market", "Sector", "Display Name"], values="Prospect Size", color="Prospect",
            color_continuous_scale=COLOR_SCALE, 
            range_color=dynamic_range, 
            custom_data=["Prospect", "3M Return", "1M Return", "Action"]
        )
        fig.update_layout(height=700, margin=dict(t=10,l=10,r=10,b=10), coloraxis_showscale=True)
        fig.update_traces(
            textinfo="label",
            hovertemplate=(
                "<b>%{label}</b><br>Score: %{customdata[0]}<br>"
                "3M Return: %{customdata[1]:.1f}%<br>1M Return: %{customdata[2]:.1f}%<br>"
                "%{customdata[3]}<extra></extra>"
            )
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"📌 Box Size = Prospect Score · Color Range: Auto-adjusted based on median score ({median_score:.1f} pts) - Top 50% Red, Bottom 50% Blue")
        
        st.divider()
        st.markdown("### 🖱️ Stock Quick View")
        sel_quick = st.selectbox("Select a Ticker from the map to see instant details:", ["(None Selected)"] + df.Ticker.tolist())
        
        if sel_quick != "(None Selected)":
            r_quick = df[df.Ticker == sel_quick].iloc[0]
            
            reasons = []
            if r_quick["Trend Score"] >= 70: reasons.append("✅ **Trend Bullish:** Breaking above 20/60/120-day moving averages with strong upward momentum.")
            elif r_quick["Trend Score"] >= 35: reasons.append("⚠️ **Trend Neutral:** Recovering short-term MAs but needs confirmation for a solid trend reversal.")
            else: reasons.append("🚨 **Trend Bearish:** Trending below major moving averages.")
            
            if r_quick['3M Return'] > 15: reasons.append(f"✅ **Return Momentum:** Surged {r_quick['3M Return']:.1f}% over the last 3 months, attracting strong capital.")
            elif r_quick['3M Return'] < -10: reasons.append(f"🚨 **Short-term Correction:** Dropped {r_quick['3M Return']:.1f}% over the last 3 months, losing market attention.")
            
            if r_quick["Vol Momentum"] > 20: reasons.append(f"✅ **Volume Spike:** Volume increased by {r_quick['Vol Momentum']:.1f}% compared to average, indicating potential new catalysts.")
            
            st.info("\n\n".join(reasons))
            
            col_chart, col_news = st.columns([2, 1])
            with col_chart:
                st.markdown("**📈 Last 100 Days Price Trend**")
                if isinstance(r_quick["Chart"], pd.DataFrame) and not r_quick["Chart"].empty:
                    st.line_chart(r_quick["Chart"][["Close"]].rename(columns={"Close": "Price ($)"}), use_container_width=True)
            with col_news:
                st.markdown("**📰 Recent News**")
                for i, z in enumerate(news(sel_quick, 5), 1):
                    st.markdown(f"- {z}")
    
    with t2:
        s = df.groupby("Sector").agg(Avg_Score=("Score","mean"), Avg_1M=("1M Return","mean"), Avg_3M=("3M Return","mean"), Avg_1Y=("1Y Return","mean"), Count=("Ticker","count")).reset_index().sort_values("Avg_Score", ascending=False)
        fig = px.bar(s.sort_values("Avg_Score"), x="Avg_Score", y="Sector", orientation="h", text="Avg_Score", color="Avg_Score", color_continuous_scale=COLOR_SCALE, range_color=dynamic_range)
        fig.update_traces(texttemplate='%{text:.1f}')
        fig.update_layout(height=600, coloraxis_showscale=False); st.plotly_chart(fig, use_container_width=True); st.dataframe(s.round(1), use_container_width=True, hide_index=True)
    
    with t3:
        if pf.empty: st.warning("No portfolio data.")
        else:
            ev = pf["Valuation"].sum(); cost = pf["Total Cost"].sum(); pnl = ev - cost
            a, b, c, d = st.columns(4); a.metric("Total Valuation", f"$ {ev:,.2f}"); b.metric("Total Cost", f"$ {cost:,.2f}"); c.metric("Total PnL", f"$ {pnl:,.2f}"); d.metric("Total Return", f"{(ev/cost-1)*100:.2f}%" if cost>0 else "-")
            cols = ["Ticker", "Company", "Quantity", "Avg Price", "Est. Market Price", "Valuation", "Total PnL", "Total Return", "Score", "Action", "3M Return"]
            
            # Formatting to USD Style
            pf_display = pf[cols].copy()
            for col in ["Avg Price", "Est. Market Price", "Valuation", "Total PnL"]:
                pf_display[col] = pf_display[col].apply(lambda x: f"$ {x:,.2f}")
                
            st.dataframe(pf_display, use_container_width=True, hide_index=True)
            st.caption("※ **Est. Market Price**: 60-day moving average price. Compare your 'Avg Price' to see if you bought at a premium or discount.")
    
    with t4:
        sel = st.selectbox("Search Stock Details", df.Ticker.tolist()); r = df[df.Ticker == sel].iloc[0]
        a, b, c, d, e = st.columns(5); a.metric("Score", f"{r['Score']}"); b.metric("Current Price", f"$ {r['Current Price']:,.2f}"); c.metric("1M Return", f"{r['1M Return']:.1f}%"); d.metric("3M Return", f"{r['3M Return']:.1f}%"); e.metric("Action", r["Action"])
        a, b, c, d = st.columns(4); a.metric("1Y Return", f"{r['1Y Return']:.1f}%"); b.metric("Est. Market Price", f"$ {r['Est. Market Price']:,.2f}"); c.metric("Trend Score", f"{r['Trend Score']}/100"); d.metric("Max Drawdown", f"{r['Max Drawdown']:.1f}%")
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
    st.info("👆 Click **Start PRO US Market Analysis** to begin.")