import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO v4.2", page_icon="🗺️", layout="wide")

COLOR_SCALE = [
    [0.0,  "#1e3a8a"],  
    [0.25, "#60a5fa"],  
    [0.50, "#e2e8f0"],  
    [0.75, "#f87171"],  
    [1.0,  "#dc2626"]   
]

SECTORS={
"⚡ AI/Semiconductor":["삼성전자","SK하이닉스","한미반도체","테스","에스에이엠티","DB하이텍","리노공업","이오테크닉스","HPSP","원익IPS","반도체"],
"🤖 Robot/Automation":["두산로보틱스","레인보우로보틱스","로보티즈","뉴로메카","에스피지","로봇","자동화"],
"🚢 Shipbuilding/Defense":["한화오션","HD현대중공업","HD한국조선해양","삼성중공업","한화에어로스페이스","한국항공우주","LIG넥스원","현대로템","조선","방산"],
"🧬 Bio/Pharma":["삼성바이오로직스","셀트리온","유한양행","알테오젠","HLB","바이오","제약"],
"🚗 Auto/Parts":["현대차","기아","현대모비스","HL만도","한온시스템","자동차"],
"💰 Finance/Holding":["KB금융","신한지주","하나금융지주","우리금융지주","메리츠금융지주","BNK금융지주","금융","은행"],
"🔋 EV Battery":["LG에너지솔루션","삼성SDI","SK이노베이션","POSCO홀딩스","포스코퓨처엠","에코프로","에코프로비엠","배터리","2차전지"],
"📱 Telecom/Network":["SK텔레콤","KT","LG유플러스","통신"],
"🎬 Enter/Game":["하이브","에스엠","JYP","YG","엔씨소프트","카카오게임즈","넷마블","게임","엔터"],
"🛒 Retail/Consumer":["이마트","신세계","롯데쇼핑","아모레퍼시픽","LG생활건강","화장품","유통"],
"🏗️ Const/Real Estate":["현대건설","GS건설","대우건설","DL이앤씨","건설","부동산"],
"🧪 Steel/Chemical":["POSCO홀딩스","포스코인터내셔널","LG화학","롯데케미칼","금호석유","S-Oil","철강","화학"]}

FALLBACK=[
("005930","삼성전자",650),("000660","SK하이닉스",300),("373220","LG에너지솔루션",100),
("207940","삼성바이오로직스",90),("005380","현대차",90),("000270","기아",75),
("012450","한화에어로스페이스",65),("042660","한화오션",60),("068270","셀트리온",55),
("105560","KB금융",55),("055550","신한지주",45),("086790","하나금융지주",40),
("035420","NAVER",45),("035720","카카오",30),("006400","삼성SDI",45),
("051910","LG화학",35),("003550","LG",25),("028260","삼성물산",35),
("009150","삼성전기",30),("034730","SK",35),("066570","LG전자",35),
("012330","현대모비스",30),("017670","SK텔레콤",25),("030200","KT",20),
("032640","LG유플러스",15),("096770","SK이노베이션",25),("003670","포스코퓨처엠",30),
("086520","에코프로",25),("247540","에코프로비엠",25),("042700","한미반도체",30),
("403870","HPSP",15),("095610","테스",8),("031330","에스에이엠티",5),
("454910","두산로보틱스",12),("277810","레인보우로보틱스",12),("010140","삼성중공업",25),
("009540","HD한국조선해양",35),("329180","HD현대중공업",45),("047810","한국항공우주",30),
("079550","LIG넥스원",25),("064350","현대로템",25),("028300","HLB",20),
("352820","하이브",20),("041510","에스엠",10),("036570","엔씨소프트",15),
("000720","현대건설",15),("006360","GS건설",10),("010950","S-Oil",20),
("011170","롯데케미칼",12),("004020","현대제철",15),("139480","이마트",8),
("004170","신세계",10),("090430","아모레퍼시픽",12),("000100","유한양행",15)]

def fallback_df():
    return pd.DataFrame([{"Code":c,"Name":n,"Marcap":w*1e12,"Volume":0,"Fallback":True} for c,n,w in FALLBACK])

@st.cache_data(ttl=3600,show_spinner=False)
def load_universe():
    errors=[]; partial=[]
    for market in ["KRX","KOSPI","KOSDAQ"]:
        try:
            x=fdr.StockListing(market)
            if x is None or x.empty: continue
            x=x.copy()
            if "Code" not in x or "Name" not in x: continue
            if "Marcap" not in x: x["Marcap"]=np.nan
            if "Volume" not in x: x["Volume"]=0
            x["Code"]=x["Code"].astype(str).str.zfill(6)
            x["Name"]=x["Name"].astype(str).str.strip()
            x["Marcap"]=pd.to_numeric(x["Marcap"],errors="coerce")
            x["Volume"]=pd.to_numeric(x["Volume"],errors="coerce").fillna(0)
            x["Fallback"]=False
            if market=="KRX":
                return x.drop_duplicates("Code").sort_values("Marcap",ascending=False,na_position="last"),False,errors
            partial.append(x)
        except Exception as e:
            errors.append(f"{market}: {type(e).__name__}: {str(e)[:180]}")
    if partial:
        x=pd.concat(partial,ignore_index=True).drop_duplicates("Code")
        return x.sort_values("Marcap",ascending=False,na_position="last"),False,errors
    return fallback_df(),True,errors

@st.cache_data(ttl=1800,show_spinner=False)
def get_price(code):
    try:
        end=dt.date.today(); start=end-dt.timedelta(days=365*5+45)
        x=fdr.DataReader(str(code).zfill(6),start,end)
        if x is None or x.empty or "Close" not in x: return pd.DataFrame()
        x=x.copy(); x.index=pd.to_datetime(x.index); return x.sort_index()
    except Exception: return pd.DataFrame()

def sector(name):
    for s,ks in SECTORS.items():
        if any(k in str(name) for k in ks): return s
    return "기타"

def ret(close,days):
    if close.empty:return 0.0
    p=close[close.index<=close.index[-1]-pd.Timedelta(days=days)]
    if p.empty:return 0.0
    return (close.iloc[-1]/p.iloc[-1]-1)*100 if p.iloc[-1]>0 else 0.0

def analyze(code,name,marcap=0,volume=0):
    x=get_price(code); base={"Stock Name":name,"Code":str(code).zfill(6),"Sector":sector(name),"Market Cap":float(marcap or 0),"Volume":float(volume or 0),"Chart":x.tail(100)}
    if x.empty:return {**base,"Current Price":0,"5Y Return":0,"1Y Return":0,"3M Return":0,"1M Return":0,"Vol Momentum":0,"Volatility":0,"Max Drawdown":0,"Trend Score":0,"Score":0,"Action":"⚪ Insufficient Data","Est. Market Price":0}
    c=pd.to_numeric(x.Close,errors="coerce").dropna(); cur=float(c.iloc[-1])
    r5,r1,r3,r1m=[ret(c,d) for d in (1825,365,90,30)]
    vm=0
    if "Volume" in x:
        v=pd.to_numeric(x.Volume,errors="coerce").dropna()
        if len(v)>=40 and v.iloc[-40:-20].mean()>0: vm=(v.tail(20).mean()/v.iloc[-40:-20].mean()-1)*100
    ma20=c.rolling(20).mean().iloc[-1]; ma60=c.rolling(60).mean().iloc[-1] if len(c)>=60 else np.nan; ma120=c.rolling(120).mean().iloc[-1] if len(c)>=120 else np.nan
    trend=(35 if cur>ma20 else 0)+(35 if pd.notna(ma60) and cur>ma60 else 0)+(30 if pd.notna(ma120) and cur>ma120 else 0)
    vol=float(c.pct_change().tail(60).std()*np.sqrt(252)*100)
    dd=float((c/c.cummax()-1).min()*100)
    
    est_market_price = float(ma60) if pd.notna(ma60) else cur
    
    score=50
    score += 15 if r5>=100 else 10 if r5>=50 else 5 if r5>0 else -10 if r5<-30 else 0
    score += 20 if r1>=30 else 14 if r1>=15 else 7 if r1>0 else -12 if r1<-20 else 0
    score += 15 if r3>=20 else 10 if r3>=10 else 5 if r3>0 else -10 if r3<-15 else 0
    score += 10 if r1m>=10 else 6 if r1m>=3 else 2 if r1m>0 else -8 if r1m<-10 else 0
    score += 10 if vm>=50 else 6 if vm>=20 else 2 if vm>=0 else -5 if vm<-30 else 0
    score += trend*.20
    if vol>80:score-=5
    if dd<-35:score-=5
    score=int(max(0,min(100,round(score))))
    action="🟢 Strong Hold / Buy More" if score>=82 and r3>5 and r1m>0 else "🟢 Hold" if score>=72 and r3>=0 else "🟡 Watch / Accumulate" if score>=62 else "🟠 Trim Position" if score>=48 else "🔴 Sell / Replace"
    
    return {**base,"Current Price":cur,"5Y Return":round(r5,2),"1Y Return":round(r1,2),"3M Return":round(r3,2),"1M Return":round(r1m,2),"Vol Momentum":round(vm,2),"Volatility":round(vol,2),"Max Drawdown":round(dd,2),"Trend Score":int(trend),"Score":score,"Action":action,"Est. Market Price":round(est_market_price)}

@st.cache_data(ttl=1800,show_spinner=False)
def news(name,limit=5):
    out=[]
    try:
        u="https://news.google.com/rss/search?q="+requests.utils.quote(name+" 주식")+"&hl=ko&gl=KR&ceid=KR:ko"
        r=requests.get(u,timeout=5,headers={"User-Agent":"Mozilla/5.0"})
        root=ET.fromstring(r.content) if r.ok else None
        if root:
            for item in root.findall(".//item"):
                t=item.find("title")
                if t is not None and t.text:
                    z=t.text.replace(" - Yahoo Finance","").replace(" - Naver","").strip()
                    if z not in out:out.append(z)
                if len(out)>=limit:break
    except Exception:pass
    return out or ["Failed to fetch recent news."]

NAME_TO_CODE={n:c for c,n,_ in FALLBACK}

def resolve(name,u):
    m=u[u.Name.astype(str).str.strip()==name.strip()]
    if not m.empty:
        r=m.iloc[0];return str(r.Code).zfill(6),float(r.Marcap or 0),float(r.Volume or 0)
    return (NAME_TO_CODE[name.strip()],0,0) if name.strip() in NAME_TO_CODE else (None,0,0)

def outlook(df):
    a=df["Score"].mean(); r3=df["3M Return"].mean(); r1=df["1M Return"].mean()
    hot=(df["Score"]>=75).mean()*100; pos=(df["3M Return"]>0).mean()*100
    p=sum([a>=70,r3>5,r1>2,hot>=30,pos>=60])-sum([a<50,r3<-5,r1<-2,hot<10,pos<40])
    label="🟢 Strong Bull" if p>=4 else "🟢 Mild Bull" if p>=2 else "🔴 Strong Bear" if p<=-4 else "🟠 Bear/Defensive" if p<=-2 else "🟡 Neutral/Mixed"
    return label,f"Avg Score {a:.1f}, Avg 3M {r3:.1f}%, Avg 1M {r1:.1f}%, HOT ratio {hot:.1f}%, Positive 3M ratio {pos:.1f}%"

st.markdown("<h1 style='text-align:center'>🗺️ AI MARKET MAP PRO v4.2</h1>",unsafe_allow_html=True)
st.caption("🔥 Technical Ranking Screening · Quick View · Auto 50:50 Color Scale · Persistent Portfolio")

with st.sidebar:
    st.header("⚙️ Analysis Settings")
    st.markdown("**🔍 Technical Ranking Screening**")
    
    pool_size = st.slider("Initial Scan Pool (Top Market Cap)", 50, 300, 150, 50)
    n = st.slider("Final Displayed Stocks (Top Score)", 20, 100, 50, 10)
    
    st.divider()
    workers = st.slider("Concurrent Requests (Speed)", 2, 8, 5)
    cap = st.number_input("Min Market Cap (Trillion KRW)", 0.0, 100.0, 1.0, 1.0)
    
    if st.button("🔄 Clear Cache", use_container_width=True):
        st.cache_data.clear(); st.rerun()

if "portfolio_data" not in st.session_state:
    st.session_state.portfolio_data = pd.DataFrame([
        {"Stock Name": "두산로보틱스", "Quantity": 100, "Avg Price": 50000},
        {"Stock Name": "한화오션", "Quantity": 50, "Avg Price": 80000},
        {"Stock Name": "테스", "Quantity": 0, "Avg Price": 0},
        {"Stock Name": "에스에이엠티", "Quantity": 0, "Avg Price": 0}
    ])

with st.form("portfolio_form"):
    st.markdown("### 💼 My Portfolio Input")
    st.caption("Click cells to edit. Add new stocks at the bottom empty row. Navigation won't lose your data.")
    
    edited_df = st.data_editor(
        st.session_state.portfolio_data,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="portfolio_editor_ui"
    )
    
    run = st.form_submit_button("🗺️ Start PRO Market Analysis", use_container_width=True, type="primary")

if run:
    st.session_state.portfolio_data = edited_df.copy()
    ps = edited_df.dropna(subset=["Stock Name"]).to_dict(orient="records")
    ps = [p for p in ps if str(p.get("Stock Name", "")).strip() != ""]

    u, fallback, errs = load_universe()
    if fallback:
        st.warning("⚠️ KRX failed to load. Using built-in fallback universe.")
            
    c = u[pd.to_numeric(u.Marcap, errors="coerce").fillna(0) >= cap*1e12].head(pool_size)
    jobs = {}
    for _, r in c.iterrows():
        jobs[str(r.Code).zfill(6)] = (str(r.Name), float(r.Marcap or 0), float(r.Volume or 0))
        
    for p in ps:
        code, m, v = resolve(p["Stock Name"], u)
        if code: jobs[code] = (p["Stock Name"], m, v)
        
    results = []; bar = st.progress(0)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs = {ex.submit(analyze, *((code,)+info)): code for code, info in jobs.items()}
        for i, f in enumerate(as_completed(fs), 1):
            try: results.append(f.result())
            except Exception: pass
            bar.progress(i / max(1, len(fs)))
    bar.empty(); df = pd.DataFrame(results)
    
    if df.empty: st.error("Failed to load price data."); st.stop()
    
    p_rows = []
    for p in ps:
        code, _, _ = resolve(p["Stock Name"], u)
        m = df[df.Code == code]
        if m.empty: continue
        r = m.iloc[0].to_dict()
        q = float(p.get("Quantity", 0))
        a = float(p.get("Avg Price", 0))
        cur = r["Current Price"]
        r.update({
            "Quantity": q, "Avg Price": a, "Valuation": cur*q, "Total Cost": a*q,
            "Total PnL": cur*q - a*q, "Total Return": ((cur/a - 1)*100 if a>0 else np.nan),
            "Owned": True
        })
        p_rows.append(r)
        
    df["Owned"] = df["Stock Name"].isin([r["Stock Name"] for r in p_rows])
    
    df_others = df[~df["Owned"]].sort_values(["Score", "3M Return"], ascending=False).head(n)
    df_port = df[df["Owned"]]
    
    df = pd.concat([df_port, df_others]).sort_values(["Score", "3M Return"], ascending=False).reset_index(drop=True)
    
    st.session_state.update(market_results=df, portfolio_results=pd.DataFrame(p_rows), analysis_complete=True, fallback_mode=fallback)

if st.session_state.get("analysis_complete"):
    df = st.session_state.market_results; pf = st.session_state.portfolio_results
    ol, why = outlook(df)
    st.markdown("## 🧠 AI Market Outlook")
    a, b, c, d = st.columns(4); a.metric("Market Phase", ol); b.metric("Avg Score", f"{df['Score'].mean():.1f}"); c.metric("Avg 3M Return", f"{df['3M Return'].mean():.1f}%"); d.metric("Avg 1M Return", f"{df['1M Return'].mean():.1f}%")
    st.info(why)
    top = df.iloc[0]; st.markdown("## 🏆 Ranking TOP PICK")
    a, b, c, d, e = st.columns(5); a.metric("Stock", top["Stock Name"]); b.metric("Sector", top["Sector"]); c.metric("Score", f"{top['Score']} pts"); d.metric("3M Return", f"{top['3M Return']:.1f}%"); e.metric("Action", top["Action"])
    t1, t2, t3, t4, t5 = st.tabs(["🗺️ Market Map", "🔥 Sectors", "💼 Portfolio", "🔍 Details", "🏆 Ranking"])
    
    with t1:
        x = df.copy()
        x["Market"] = "KOSPI/KOSDAQ"
        x["Display Name"] = x.apply(lambda r: "📌 "+r["Stock Name"] if r["Owned"] else r["Stock Name"], axis=1)
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
        sel_quick = st.selectbox("Select a stock from the map to see instant details:", ["(None Selected)"] + df["Stock Name"].tolist())
        
        if sel_quick != "(None Selected)":
            r_quick = df[df["Stock Name"] == sel_quick].iloc[0]
            
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
                    st.line_chart(r_quick["Chart"][["Close"]].rename(columns={"Close": "Price"}), use_container_width=True)
            with col_news:
                st.markdown("**📰 Recent News**")
                for i, z in enumerate(news(sel_quick, 5), 1):
                    st.markdown(f"- {z}")
    
    with t2:
        s = df.groupby("Sector").agg(Avg_Score=("Score","mean"), Avg_1M=("1M Return","mean"), Avg_3M=("3M Return","mean"), Avg_1Y=("1Y Return","mean"), Count=("Stock Name","count")).reset_index().sort_values("Avg_Score", ascending=False)
        fig = px.bar(s.sort_values("Avg_Score"), x="Avg_Score", y="Sector", orientation="h", text="Avg_Score", color="Avg_Score", color_continuous_scale=COLOR_SCALE, range_color=dynamic_range)
        fig.update_traces(texttemplate='%{text:.1f}')
        fig.update_layout(height=600, coloraxis_showscale=False); st.plotly_chart(fig, use_container_width=True); st.dataframe(s.round(1), use_container_width=True, hide_index=True)
    
    with t3:
        if pf.empty: st.warning("No portfolio data.")
        else:
            ev = pf["Valuation"].sum(); cost = pf["Total Cost"].sum(); pnl = ev - cost
            a, b, c, d = st.columns(4); a.metric("Total Valuation", f"{ev:,.0f} KRW"); b.metric("Total Cost", f"{cost:,.0f} KRW"); c.metric("Total PnL", f"{pnl:,.0f} KRW"); d.metric("Total Return", f"{(ev/cost-1)*100:.2f}%" if cost>0 else "-")
            cols = ["Stock Name", "Current Price", "Quantity", "Avg Price", "Est. Market Price", "Valuation", "Total PnL", "Total Return", "Score", "Action", "3M Return"]
            st.dataframe(pf[cols].round(2), use_container_width=True, hide_index=True)
            st.caption("※ **Est. Market Price**: 60-day moving average price. Use it to compare your average price with the recent market participants.")
    
    with t4:
        sel = st.selectbox("Search Stock Details", df["Stock Name"].tolist()); r = df[df["Stock Name"]==sel].iloc[0]
        a, b, c, d, e = st.columns(5); a.metric("Score", f"{r['Score']}"); b.metric("Current Price", f"{r['Current Price']:,.0f}"); c.metric("1M Return", f"{r['1M Return']:.1f}%"); d.metric("3M Return", f"{r['3M Return']:.1f}%"); e.metric("Action", r["Action"])
        a, b, c, d = st.columns(4); a.metric("1Y Return", f"{r['1Y Return']:.1f}%"); b.metric("Est. Market Price", f"{r['Est. Market Price']:,.0f}"); c.metric("Trend Score", f"{r['Trend Score']}/100"); d.metric("Max Drawdown", f"{r['Max Drawdown']:.1f}%")
        if isinstance(r["Chart"], pd.DataFrame) and not r["Chart"].empty: st.line_chart(r["Chart"][["Close"]].rename(columns={"Close":"Price"}), use_container_width=True)
        st.markdown("### 📰 Recent News")
        for i, z in enumerate(news(sel, 5), 1): st.markdown(f"**{i}.** {z}")
    
    with t5:
        cols = ["Stock Name", "Sector", "Score", "Action", "Current Price", "Est. Market Price", "5Y Return", "1Y Return", "3M Return", "1M Return", "Vol Momentum", "Max Drawdown"]
        q = df[cols].copy(); q.insert(0, "Rank", range(1, len(q)+1)); st.dataframe(q, use_container_width=True, hide_index=True)
else:
    st.info("👆 Click **Start PRO Market Analysis** to begin.")
