import streamlit as st
import pandas as pd
import numpy as np
import requests, datetime as dt, xml.etree.ElementTree as ET
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import FinanceDataReader as fdr

st.set_page_config(page_title="AI Market Map PRO v4.1", page_icon="🗺️", layout="wide")

# [v4.1] 색상 범위 최적화: range_color [30, 95]에 맞춰 중간값(62.5점)을 회색(중립)으로 배치
COLOR_SCALE = [
    [0.0,  "#1e3a8a"],  # 30점 이하: 짙은 파랑 (매도)
    [0.25, "#60a5fa"],  # ~46점: 연한 파랑 (비중축소)
    [0.50, "#e2e8f0"],  # ~62.5점: 중성 회색 (관망/중립)
    [0.75, "#f87171"],  # ~78점: 연한 빨강 (보유)
    [1.0,  "#dc2626"]   # 95점 이상: 짙은 빨강 (적극매수)
]

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
st.caption("KRX 장애 대응 · 유망도 기반 시장맵(색상 최적화) · 대화형 포트폴리오 테이블 · 매수/매도 의견")

with st.sidebar:
    st.header("⚙️ 분석 설정")
    n=st.slider("분석 종목 수",20,50,30,5)
    workers=st.slider("동시 요청 수",2,8,5)
    cap=st.number_input("최소 시가총액(조원)",0.0,100.0,1.0,1.0)
    if st.button("🔄 캐시 초기화",use_container_width=True):
        st.cache_data.clear(); st.rerun()

if "portfolio_data" not in st.session_state:
    st.session_state.portfolio_data = pd.DataFrame([
        {"종목명": "두산로보틱스", "수량": 100, "평균매수가": 50000},
        {"종목명": "한화오션", "수량": 50, "평균매수가": 80000},
        {"종목명": "테스", "수량": 0, "평균매수가": 0},
        {"종목명": "에스에이엠티", "수량": 0, "평균매수가": 0}
    ])

with st.form("portfolio_form"):
    st.markdown("### 💼 내 포트폴리오 입력")
    st.caption("표 안의 셀을 더블클릭하여 바로 수정하세요. 맨 아래 빈 줄을 클릭하면 새로운 종목을 추가할 수 있습니다.")
    
    edited_df = st.data_editor(
        st.session_state.portfolio_data,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )
    
    run = st.form_submit_button("🗺️ PRO 시장 분석 시작", use_container_width=True, type="primary")

if run:
    st.session_state.portfolio_data = edited_df.copy()
    ps = edited_df.dropna(subset=["종목명"]).to_dict(orient="records")
    ps = [p for p in ps if str(p.get("종목명", "")).strip() != ""]

    u,fallback,errs=load_universe()
    if fallback:
        st.warning("⚠️ KRX 종목목록 조회 실패로 내장 핵심 종목 Universe를 사용합니다. 가격 데이터는 개별 FinanceDataReader 조회를 사용합니다.")
        if errs:
            with st.expander("KRX 오류 상세"): [st.write("-",e) for e in errs]
            
    c=u[pd.to_numeric(u.Marcap,errors="coerce").fillna(0)>=cap*1e12].head(n)
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
        r=m.iloc[0].to_dict()
        q=float(p.get("수량", 0))
        a=float(p.get("평균매수가", 0))
        cur=r["현재가"]
        r.update({
            "수량": q,
            "평균매수가": a,
            "평가금액": cur*q,
            "매입금액": a*q,
            "평가손익": cur*q - a*q,
            "수익률": ((cur/a - 1)*100 if a>0 else np.nan),
            "보유종목": True
        })
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
        x=df.copy()
        x["시장"]="KOSPI/KOSDAQ"
        x["표시명"]=x.apply(lambda r:"📌 "+r.종목명 if r.보유종목 else r.종목명, axis=1)
        x["유망도"]=pd.to_numeric(x["점수"],errors="coerce").clip(0,100)
        x["유망도크기"]=(x["유망도"]+1)**2

        # [v4.1] range_color를 [30, 95]로 좁혀 파란색과 붉은색이 명확히 구분되도록 적용
        fig=px.treemap(
            x, path=["시장","섹터","표시명"], values="유망도크기", color="유망도",
            color_continuous_scale=COLOR_SCALE, range_color=[30, 95],
            custom_data=["유망도","3개월수익률","1개월수익률","판단"]
        )
        fig.update_layout(height=700, margin=dict(t=10,l=10,r=10,b=10), coloraxis_showscale=True)
        fig.update_traces(
            textinfo="label",
            hovertemplate=(
                "<b>%{label}</b><br>유망도: %{customdata[0]}점<br>"
                "3개월 수익률: %{customdata[1]:.1f}%<br>1개월 수익률: %{customdata[2]:.1f}%<br>"
                "%{customdata[3]}<extra></extra>"
            )
        )
        st.plotly_chart(fig,use_container_width=True)
        st.caption("📌 박스 크기 = 유망도(투자점수) · 색상 = 유망도 (파란색: 약세/매도, 회색: 중립, 빨간색: 유망/매수)")
    
    with t2:
        s=df.groupby("섹터").agg(평균점수=("점수","mean"),평균1개월=("1개월수익률","mean"),평균3개월=("3개월수익률","mean"),평균1년=("1년수익률","mean"),종목수=("종목명","count")).reset_index().sort_values("평균점수",ascending=False)
        # [v4.1] 섹터 차트에도 동일한 range_color [30, 95] 적용
        fig=px.bar(s.sort_values("평균점수"), x="평균점수", y="섹터", orientation="h", text="평균점수", color="평균점수", color_continuous_scale=COLOR_SCALE, range_color=[30, 95])
        fig.update_layout(height=600,coloraxis_showscale=False);st.plotly_chart(fig,use_container_width=True);st.dataframe(s.round(1),use_container_width=True,hide_index=True)
    
    with t3:
        if pf.empty:st.warning("보유종목이 없습니다.")
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
    st.markdown("### v4.1 핵심 개선\n- **색상 밸런스 조정**: 판단 기준(62점)을 회색으로 맞추어 빨간색/파란색 비율의 시각적 편향 해결\n- **대화형 입력표 유지**: `st.data_editor` 적용으로 엑셀처럼 쾌적한 포트폴리오 관리 지원\n\n⚠️ 기술적 참고용 분석이며 투자수익을 보장하지 않습니다.")
