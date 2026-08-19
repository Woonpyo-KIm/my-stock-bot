import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO v3", page_icon="🗺️", layout="wide")

SECTORS={
"⚡ AI/반도체":["삼성전자","SK하이닉스","한미반도체","테스","에스에이엠티","DB하이텍","리노공업","이오테크닉스","HPSP","원익IPS","반도체"],
"🤖 로봇/자동화":["두산로보틱스","레인보우로보틱스","로보티즈","뉴로메카","에스피지","로봇","자동화"],
"🚢 조선/방산":["한화오션","HD현대중공업","HD한국조선해양","삼성중공업","한화에어로스페이스","한국항공우주","LIG넥스원","현대로템","조선","방산"],
"🧬 바이오/제약":["삼성바이오로직스","셀트리온","유한양행","알테오젠","HLB","바이오","제약"],
"🚗 자동차/부품":["현대차","기아","현대모비스","HL만도","한온시스템","자동차"],
"💰 금융/지주":["KB금융","신한지주","하나금융지주","우리금융지주","메리츠금융지주","BNK금융지주","금융","은행"],
"🔋 2차전지":["LG에너지솔루션","삼성SDI","SK이노베이션","POSCO홀딩스","포스코퓨처엠","에코프로","에코프로비엠","배터리","2차전지"],
"📱 통신/네트워크":["SK텔레콤","KT","LG유플러스","통신"],
"🎬 엔터/게임":["하이브","에스엠","JYP","YG","엔씨소프트","카카오게임즈","넷마블","게임","엔터"],
"🛒 유통/소비재":["이마트","신세계","롯데쇼핑","아모레퍼시픽","LG생활건강","화장품","유통"],
"🏗️ 건설/부동산":["현대건설","GS건설","대우건설","DL이앤씨","건설","부동산"],
"🧪 철강/화학":["POSCO홀딩스","포스코인터내셔널","LG화학","롯데케미칼","금호석유","S-Oil","철강","화학"]}

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
    x=get_price(code); base={"종목명":name,"종목코드":str(code).zfill(6),"섹터":sector(name),"시가총액":float(marcap or 0),"거래량":float(volume or 0),"차트":x.tail(100)}
    if x.empty:return {**base,"현재가":0,"5년수익률":0,"1년수익률":0,"3개월수익률":0,"1개월수익률":0,"거래량모멘텀":0,"변동성":0,"최대낙폭":0,"추세점수":0,"점수":0,"판단":"⚪ 데이터 부족"}
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
    action="🟢 적극 보유 / 추가매수" if score>=82 and r3>5 and r1m>0 else "🟢 보유" if score>=72 and r3>=0 else "🟡 관망 / 분할매수" if score>=62 else "🟠 비중축소 검토" if score>=48 else "🔴 매도 / 교체 검토"
    return {**base,"현재가":cur,"5년수익률":round(r5,2),"1년수익률":round(r1,2),"3개월수익률":round(r3,2),"1개월수익률":round(r1m,2),"거래량모멘텀":round(vm,2),"변동성":round(vol,2),"최대낙폭":round(dd,2),"추세점수":int(trend),"점수":score,"판단":action}

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
    return out or ["최근 관련 뉴스를 불러오지 못했습니다."]

NAME_TO_CODE={n:c for c,n,_ in FALLBACK}
def parse_portfolio(text):
    out=[]
    for z in str(text).split(","):
        p=[a.strip() for a in z.strip().split(":")]
        if not p or not p[0]:continue
        try:q=float(p[1].replace(",","")) if len(p)>1 else 0
        except:q=0
        try:a=float(p[2].replace(",","")) if len(p)>2 else 0
        except:a=0
        out.append({"종목명":p[0],"수량":q,"평균매수가":a})
    return out

def resolve(name,u):
    m=u[u.Name.astype(str).str.strip()==name.strip()]
    if not m.empty:
        r=m.iloc[0];return str(r.Code).zfill(6),float(r.Marcap or 0),float(r.Volume or 0)
    return (NAME_TO_CODE[name.strip()],0,0) if name.strip() in NAME_TO_CODE else (None,0,0)

def outlook(df):
    a=df.점수.mean(); r3=df["3개월수익률"].mean(); r1=df["1개월수익률"].mean()
    hot=(df.점수>=75).mean()*100; pos=(df["3개월수익률"]>0).mean()*100
    p=sum([a>=70,r3>5,r1>2,hot>=30,pos>=60])-sum([a<50,r3<-5,r1<-2,hot<10,pos<40])
    label="🟢 강한 상승 국면" if p>=4 else "🟢 완만한 상승 국면" if p>=2 else "🔴 강한 약세 국면" if p<=-4 else "🟠 약세/방어 국면" if p<=-2 else "🟡 중립/혼조 국면"
    return label,f"평균점수 {a:.1f}, 평균 3개월 {r3:.1f}%, 평균 1개월 {r1:.1f}%, HOT 비중 {hot:.1f}%, 3개월 상승종목 비중 {pos:.1f}%를 종합한 기술적 판단입니다."

st.markdown("<h1 style='text-align:center'>🗺️ AI MARKET MAP PRO v4.1</h1>",unsafe_allow_html=True)
st.caption("KRX 장애 대응 · 섹터 유망도 · 종목 유망도 · 직관적인 포트폴리오 입력 · 보유손익 · 매수/보유/추가매수/매도 의견 · AI 시장전망")

with st.sidebar:
    st.header("⚙️ 분석 설정")
    n=st.slider("분석 종목 수",20,50,30,5)
    workers=st.slider("동시 요청 수",2,8,5)
    cap=st.number_input("최소 시가총액(조원)",0.0,100.0,1.0,1.0)
    if st.button("🔄 캐시 초기화",use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ============================================================
# 💼 직관적인 포트폴리오 입력 테이블
# ============================================================
if "portfolio_editor" not in st.session_state:
    st.session_state["portfolio_editor"] = pd.DataFrame({
        "종목명": ["두산로보틱스", "한화오션", "테스", "에스에이엠티"],
        "평균매수가": [0, 0, 0, 0],
        "보유수량": [0, 0, 0, 0],
    })

with st.container(border=True):
    st.markdown("### 💼 내 포트폴리오 입력")
    st.caption("종목명, 평균매수가, 보유수량만 입력하세요. 현재가는 시장 데이터를 이용해 자동 조회합니다.")

    portfolio_input = st.data_editor(
        st.session_state["portfolio_editor"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="portfolio_editor_widget",
        column_config={
            "종목명": st.column_config.TextColumn(
                "📌 종목명",
                help="예: 두산로보틱스",
            ),
            "평균매수가": st.column_config.NumberColumn(
                "💰 평균매수가(원)",
                min_value=0,
                step=100,
                format="%,.0f원",
            ),
            "보유수량": st.column_config.NumberColumn(
                "📦 보유수량(주)",
                min_value=0,
                step=1,
                format="%,.0f주",
            ),
        },
    )
    st.session_state["portfolio_editor"] = portfolio_input.copy()

    st.info("💡 행 추가는 표 아래의 **+** 버튼을 누르세요. 빈 종목명은 자동으로 제외됩니다.")

run=st.button("🗺️ PRO 시장 분석 시작",use_container_width=True,type="primary")

if run:
    u,fallback,errs=load_universe()
    if fallback:
        st.warning("⚠️ KRX 종목목록 조회 실패로 내장 핵심 종목 Universe를 사용합니다. 가격 데이터는 개별 FinanceDataReader 조회를 사용합니다.")
        if errs:
            with st.expander("KRX 오류 상세"): [st.write("-",e) for e in errs]
    c=u[pd.to_numeric(u.Marcap,errors="coerce").fillna(0)>=cap*1e12].head(n)

    # 표 입력값을 분석용 포트폴리오 리스트로 변환
    ps=[]
    for _, row in portfolio_input.iterrows():
        name=str(row.get("종목명", "")).strip()
        if not name or name.lower()=="nan":
            continue
        try: qty=float(row.get("보유수량", 0) or 0)
        except Exception: qty=0
        try: avg=float(row.get("평균매수가", 0) or 0)
        except Exception: avg=0
        if qty < 0: qty=0
        if avg < 0: avg=0
        ps.append({"종목명":name,"수량":qty,"평균매수가":avg})

    jobs={}
    for _,r in c.iterrows():jobs[str(r.Code).zfill(6)]=(str(r.Name),float(r.Marcap or 0),float(r.Volume or 0))
    for p in ps:
        code,m,v=resolve(p["종목명"],u)
        if code:jobs[code]=(p["종목명"],m,v)
    results=[]; bar=st.progress(0)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs={ex.submit(analyze,*((code,)+info)):code for code,info in jobs.items()}
        for i,f in enumerate(as_completed(fs),1):
            try:results.append(f.result())
            except Exception:pass
            bar.progress(i/max(1,len(fs)))
    bar.empty(); df=pd.DataFrame(results)
    if df.empty:st.error("가격 데이터를 불러오지 못했습니다.");st.stop()
    p_rows=[]
    for p in ps:
        code,_,_=resolve(p["종목명"],u)
        m=df[df.종목코드==code]
        if m.empty:continue
        r=m.iloc[0].to_dict(); q=p["수량"]; a=p["평균매수가"]; cur=r["현재가"]
        r.update({"수량":q,"평균매수가":a,"평가금액":cur*q,"매입금액":a*q,"평가손익":cur*q-a*q,"수익률":((cur/a-1)*100 if a>0 else np.nan),"보유종목":True})
        p_rows.append(r)
    df["보유종목"]=df.종목명.isin([r["종목명"] for r in p_rows])
    df=df.sort_values(["점수","3개월수익률"],ascending=False).reset_index(drop=True)
    st.session_state.update(market_results=df,portfolio_results=pd.DataFrame(p_rows),analysis_complete=True,fallback_mode=fallback)

if st.session_state.get("analysis_complete"):
    df=st.session_state.market_results; pf=st.session_state.portfolio_results
    ol,why=outlook(df)
    st.markdown("## 🧠 AI 시장 전망")
    a,b,c,d=st.columns(4);a.metric("시장 국면",ol);b.metric("평균점수",f"{df.점수.mean():.1f}");c.metric("평균 3개월",f"{df['3개월수익률'].mean():.1f}%");d.metric("평균 1개월",f"{df['1개월수익률'].mean():.1f}%")
    st.info(why)
    top=df.iloc[0];st.markdown("## 🏆 TOP PICK")
    a,b,c,d,e=st.columns(5);a.metric("종목",top.종목명);b.metric("섹터",top.섹터);c.metric("점수",f"{top.점수}점");d.metric("3개월",f"{top['3개월수익률']:.1f}%");e.metric("판단",top.판단)
    t1,t2,t3,t4,t5=st.tabs(["🗺️ 시장맵","🔥 섹터","💼 포트폴리오","🔍 상세","🏆 순위"])
    with t1:
        # [v3.1] 시장맵의 박스 크기를 시가총액이 아니라 유망도(투자점수)로 표시
        x=df.copy()
        x["시장"]="KOSPI/KOSDAQ"
        x["표시명"]=x.apply(
            lambda r:"📌 "+r.종목명 if r.보유종목 else r.종목명, axis=1
        )
        x["유망도"]=pd.to_numeric(x["점수"],errors="coerce").clip(0,100)
        # 점수 차이가 박스 크기에서 더 잘 보이도록 제곱 스케일 적용
        x["유망도크기"]=(x["유망도"]+1)**2

        fig=px.treemap(
            x,
            path=["시장","섹터","표시명"],
            values="유망도크기",
            color="유망도",
            color_continuous_scale=["#0b486b","#cccccc","#ff0000"],
            range_color=[0,100],
            custom_data=["유망도","3개월수익률","1개월수익률","판단"]
        )
        fig.update_layout(
            height=700,
            margin=dict(t=10,l=10,r=10,b=10),
            coloraxis_showscale=False
        )
        fig.update_traces(
            textinfo="label",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "유망도: %{customdata[0]}점<br>"
                "3개월 수익률: %{customdata[1]:.1f}%<br>"
                "1개월 수익률: %{customdata[2]:.1f}%<br>"
                "%{customdata[3]}<extra></extra>"
            )
        )
        st.plotly_chart(fig,use_container_width=True)
        st.caption(
            "📌 박스 크기 = 유망도(투자점수) · 색상 = 유망도 · "
            "시가총액은 더 이상 시장맵 크기에 영향을 주지 않습니다."
        )
    with t2:
        st.markdown("### 🔥 섹터 투자지도")
        st.caption("섹터 자체의 유망도와 섹터 내 종목 유망도를 2단계로 평가합니다.")

        # 섹터별 기초 통계
        sector_df = (
            df.groupby("섹터")
              .agg(
                  base_score=("점수", "mean"),
                  avg_3m=("3개월수익률", "mean"),
                  avg_1m=("1개월수익률", "mean"),
                  avg_1y=("1년수익률", "mean"),
                  stock_count=("종목명", "count"),
                  rising_ratio=("3개월수익률", lambda x: (x > 0).mean() * 100),
                  high_score_ratio=("점수", lambda x: (x >= 75).mean() * 100),
              )
              .reset_index()
        )

        # 섹터 유망도:
        # 종목 점수 45% + 3개월 추세 20% + 1개월 추세 15%
        # + 상승 종목 확산 10% + 고득점 종목 확산 10%
        sector_df["섹터유망도"] = (
            sector_df["base_score"] * 0.45
            + sector_df["avg_3m"].clip(-30, 50).add(30).div(80).mul(100) * 0.20
            + sector_df["avg_1m"].clip(-20, 30).add(20).div(50).mul(100) * 0.15
            + sector_df["rising_ratio"] * 0.10
            + sector_df["high_score_ratio"] * 0.10
        ).clip(0, 100).round(1)

        def sector_action(v):
            if v >= 82:
                return "🟢 최우선 관심"
            if v >= 72:
                return "🟢 비중확대 관심"
            if v >= 62:
                return "🟡 관망 / 분할접근"
            if v >= 50:
                return "🟠 비중축소 검토"
            return "🔴 회피 / 교체 검토"

        sector_df["의견"] = sector_df["섹터유망도"].apply(sector_action)
        sector_df = sector_df.sort_values("섹터유망도", ascending=False).reset_index(drop=True)

        best = sector_df.iloc[0]
        worst = sector_df.iloc[-1]

        a, b, c, d = st.columns(4)
        a.metric("🥇 최선호 섹터", best["섹터"], f'{best["섹터유망도"]:.1f}점')
        b.metric("📈 최선호 3개월", f'{best["avg_3m"]:.1f}%')
        c.metric("⚠️ 최약 섹터", worst["섹터"], f'{worst["섹터유망도"]:.1f}점')
        d.metric("🔥 고득점 종목 비율", f'{best["high_score_ratio"]:.0f}%')

        # 섹터 투자지도: 박스 크기 = 섹터 유망도
        sector_plot = sector_df.copy()
        sector_plot["시장"] = "전체시장"
        sector_plot["유망도크기"] = (sector_plot["섹터유망도"] + 1) ** 2

        fig_sector = px.treemap(
            sector_plot,
            path=["시장", "섹터"],
            values="유망도크기",
            color="섹터유망도",
            color_continuous_scale=["#0b486b", "#cccccc", "#ff0000"],
            range_color=[0, 100],
            custom_data=[
                "섹터유망도", "avg_3m", "avg_1m",
                "rising_ratio", "high_score_ratio", "의견"
            ]
        )
        fig_sector.update_layout(
            height=600,
            margin=dict(t=10, l=10, r=10, b=10),
            coloraxis_showscale=False
        )
        fig_sector.update_traces(
            textinfo="label",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "섹터 유망도: %{customdata[0]:.1f}점<br>"
                "평균 3개월: %{customdata[1]:.1f}%<br>"
                "평균 1개월: %{customdata[2]:.1f}%<br>"
                "상승 종목 비율: %{customdata[3]:.1f}%<br>"
                "75점 이상 비율: %{customdata[4]:.1f}%<br>"
                "%{customdata[5]}<extra></extra>"
            )
        )
        st.plotly_chart(fig_sector, use_container_width=True)

        # 섹터 강도 순위
        fig_bar = px.bar(
            sector_df.sort_values("섹터유망도"),
            x="섹터유망도",
            y="섹터",
            orientation="h",
            text="섹터유망도",
            color="섹터유망도",
            color_continuous_scale=["#0b486b", "#cccccc", "#ff0000"],
            range_color=[0, 100]
        )
        fig_bar.update_layout(height=650, coloraxis_showscale=False)
        st.plotly_chart(fig_bar, use_container_width=True)

        st.dataframe(
            sector_df[
                [
                    "섹터", "섹터유망도", "의견",
                    "avg_3m", "avg_1m", "avg_1y",
                    "rising_ratio", "high_score_ratio", "stock_count"
                ]
            ].rename(
                columns={
                    "avg_3m": "평균3개월",
                    "avg_1m": "평균1개월",
                    "avg_1y": "평균1년",
                    "rising_ratio": "상승종목비율",
                    "high_score_ratio": "75점이상비율",
                    "stock_count": "종목수",
                }
            ).round(1),
            use_container_width=True,
            hide_index=True
        )

        selected_sector = st.selectbox(
            "🔎 상세 분석할 섹터",
            sector_df["섹터"].tolist(),
            index=0
        )

        sector_stocks = df[df["섹터"] == selected_sector].sort_values(
            ["점수", "3개월수익률"], ascending=False
        ).head(10)

        st.markdown(f"#### 🏆 {selected_sector} 내 유망 종목 TOP 10")
        st.dataframe(
            sector_stocks[
                [
                    "종목명", "점수", "판단", "현재가",
                    "1개월수익률", "3개월수익률",
                    "1년수익률", "최대낙폭"
                ]
            ].round(2),
            use_container_width=True,
            hide_index=True
        )
    with t3:
        st.markdown("### 💼 내 포트폴리오 현황")
        st.caption("위 입력표의 평균매수가·수량을 기준으로 현재가, 평가금액, 손익을 자동 계산합니다.")
        if pf.empty:st.warning("보유종목이 없습니다. 위 입력표에 종목을 추가하고 분석을 실행하세요.")
        else:
            ev=pf.평가금액.sum();cost=pf.매입금액.sum();pnl=ev-cost
            a,b,c,d=st.columns(4);a.metric("평가금액",f"{ev:,.0f}원");b.metric("매입금액",f"{cost:,.0f}원");c.metric("평가손익",f"{pnl:,.0f}원");d.metric("총수익률",f"{(ev/cost-1)*100:.2f}%" if cost>0 else "-")
            cols=["종목명","현재가","수량","평균매수가","평가금액","평가손익","수익률","점수","판단","3개월수익률","1개월수익률","최대낙폭"]
            st.dataframe(pf[cols].round(2),use_container_width=True,hide_index=True)
    with t4:
        sel=st.selectbox("종목",df.종목명.tolist());r=df[df.종목명==sel].iloc[0]
        a,b,c,d,e=st.columns(5);a.metric("점수",f"{r.점수}");b.metric("현재가",f"{r.현재가:,.0f}원");c.metric("1개월",f"{r['1개월수익률']:.1f}%");d.metric("3개월",f"{r['3개월수익률']:.1f}%");e.metric("판단",r.판단)
        a,b,c,d=st.columns(4);a.metric("1년",f"{r['1년수익률']:.1f}%");b.metric("5년",f"{r['5년수익률']:.1f}%");c.metric("추세",f"{r.추세점수}/100");d.metric("최대낙폭",f"{r.최대낙폭:.1f}%")
        if isinstance(r.차트,pd.DataFrame) and not r.차트.empty:st.line_chart(r.차트[["Close"]].rename(columns={"Close":"종가"}),use_container_width=True)
        st.markdown("### 📰 최근 뉴스")
        for i,z in enumerate(news(sel,5),1):st.markdown(f"**{i}.** {z}")
    with t5:
        cols=["종목명","섹터","점수","판단","현재가","5년수익률","1년수익률","3개월수익률","1개월수익률","거래량모멘텀","변동성","최대낙폭","추세점수"]
        q=df[cols].copy();q.insert(0,"순위",range(1,len(q)+1));st.dataframe(q,use_container_width=True,hide_index=True)
else:
    st.info("👆 **PRO 시장 분석 시작**을 누르세요.")
    st.markdown("### v3 핵심 개선\n- KRX `StockListing()` 실패 시 KOSPI/KOSDAQ 재시도 후 static fallback\n- 병렬 가격조회 + cache로 실행속도 개선\n- 종목명:수량:평균매수가 입력 및 실제 손익 계산\n- 투자점수와 매수/보유/추가매수/매도 의견\n- 기술지표 기반 시장 국면 전망\n\n⚠️ 기술적 참고용 분석이며 투자수익을 보장하지 않습니다.")
