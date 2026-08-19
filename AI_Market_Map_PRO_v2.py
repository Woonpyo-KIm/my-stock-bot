# -*- coding: utf-8 -*-
"""
AI 마켓 맵 PRO
실전 주식 분석용 Streamlit 앱

주요 기능
1) 실행속도 개선
   - FinanceDataReader 지연 import
   - 종목별 주가 데이터 병렬 수집
   - Streamlit cache 사용
   - 분석 대상 기본 30종목으로 조정 가능

2) 종목별 투자점수 개선
   - 5Y / 1Y / 3M / 1M 모멘텀
   - 52주 고점 대비 위치
   - 변동성
   - 거래량
   - 시가총액
   - 시장(KOSPI/KOSDAQ) 대비 상대강도
   - 섹터 분류

3) 보유종목
   - 종목명 / 수량 / 평균매수가 입력
   - 현재가 / 평가금액 / 수익률 / 손익
   - 포트폴리오 점수

4) 매도 / 보유 / 추가매수 의견
   - 점수 + 수익률 + 추세 + 위험도 기반 규칙 엔진
   - 투자자문이 아닌 분석 참고용

5) AI 시장 전망
   - KOSPI / KOSDAQ 추세
   - 시장 breadth
   - 상위 종목 모멘텀
   - 변동성
   - 섹터별 강도
   를 결합한 "AI 스타일" 시장 진단

주의:
- 본 앱은 자동매매/투자자문 서비스가 아닙니다.
- 데이터 지연/오류가 있을 수 있으므로 실제 주문 전 원자료를 확인하세요.
"""

import datetime
import html
import math
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


# ============================================================
# 0. PAGE
# ============================================================
st.set_page_config(
    page_title="AI 마켓 맵 PRO",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.35rem;
        font-weight: 850;
        text-align: center;
        background: linear-gradient(45deg, #ff4e50, #1a5293);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
        padding-top: 0.5rem;
    }
    .sub-title {
        text-align: center;
        color: #666;
        font-size: 0.95rem;
        margin-bottom: 1.0rem;
    }
    .small-note {
        color: #777;
        font-size: 0.82rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 1. SECTOR
# ============================================================
SECTORS = {
    "⚡ AI/반도체": [
        "AI", "반도체", "HBM", "테스", "에스에이엠티",
        "SK하이닉스", "삼성전자", "한미반도체",
    ],
    "🤖 로봇/자동화": [
        "로봇", "자동화", "스마트팩토리",
        "두산로보틱스", "레인보우로보틱스",
    ],
    "🚢 조선/방산": [
        "조선", "방산", "수주", "한화오션",
        "HD현대", "한국항공우주",
    ],
    "🧬 바이오/제약": [
        "바이오", "신약", "제약", "삼성바이오로직스",
        "셀트리온", "유한양행",
    ],
    "🚗 자동차/부품": [
        "자동차", "현대차", "기아", "현대모비스", "만도",
    ],
    "💰 금융/지주사": [
        "금융", "은행", "지주", "배당",
        "KB금융", "신한지주", "하나금융지주",
    ],
    "🔋 2차전지/배터리": [
        "배터리", "2차전지", "에코프로",
        "LG에너지솔루션", "포스코퓨처엠",
    ],
    "📱 통신/네트워크": [
        "통신", "SK텔레콤", "KT", "LG유플러스",
    ],
    "🎬 엔터/게임": [
        "엔터", "게임", "콘텐츠", "하이브",
        "엔씨소프트", "카카오",
    ],
    "🛒 유통/소비재": [
        "유통", "쇼핑", "화장품", "이마트",
        "신세계", "아모레퍼시픽",
    ],
    "🏗️ 건설/부동산": [
        "건설", "부동산", "건축", "현대건설",
        "GS건설", "대우건설",
    ],
    "🧪 철강/화학": [
        "철강", "화학", "석유", "포스코홀딩스",
        "LG화학", "S-Oil",
    ],
}


# ============================================================
# 2. FDR
# ============================================================
@st.cache_resource(show_spinner=False)
def get_fdr():
    try:
        import FinanceDataReader as fdr
        return fdr, None
    except Exception as e:
        return None, e


# ============================================================
# 3. HELPERS
# ============================================================
def safe_num(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def classify_sector(name):
    name = str(name).strip()
    for sector, keywords in SECTORS.items():
        if any(k in name for k in keywords):
            return sector
    return "기타 우량주"


def clamp(x, low=0, high=100):
    return max(low, min(high, x))


def pct_change(series, periods):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= periods or s.iloc[-periods - 1] == 0:
        return None
    return (s.iloc[-1] / s.iloc[-periods - 1] - 1) * 100


def calc_max_drawdown(close):
    s = pd.to_numeric(close, errors="coerce").dropna()
    if s.empty:
        return 0.0
    peak = s.cummax()
    dd = s / peak - 1
    return abs(float(dd.min()) * 100)


def calc_volatility(close, annualize=True):
    s = pd.to_numeric(close, errors="coerce").dropna()
    if len(s) < 20:
        return 0.0
    ret = s.pct_change().dropna()
    vol = ret.std()
    if annualize:
        vol *= math.sqrt(252)
    return float(vol * 100)


def market_label(code):
    code = str(code)
    # FDR KRX listing usually has Market column, but this fallback is useful.
    return ""


# ============================================================
# 4. KRX
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_krx():
    fdr, err = get_fdr()
    if fdr is None:
        raise RuntimeError(
            f"FinanceDataReader import 실패: {err}\n"
            "requirements.txt에는 finance-datareader가 필요합니다."
        )

    df = fdr.StockListing("KRX")
    if df is None or df.empty:
        raise RuntimeError("KRX 종목 데이터를 가져오지 못했습니다.")

    df = df.copy()

    for col in ["Code", "Name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    if "Marcap" not in df.columns:
        raise RuntimeError(f"Marcap 컬럼이 없습니다. 현재 컬럼: {list(df.columns)}")

    df["Marcap"] = pd.to_numeric(df["Marcap"], errors="coerce")
    df = df.dropna(subset=["Marcap"])

    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_candidates(limit):
    df = load_krx()
    return (
        df[df["Marcap"] >= 500_000_000_000]
        .sort_values("Marcap", ascending=False)
        .head(int(limit))
        .copy()
    )


# ============================================================
# 5. PRICE DATA
# ============================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_price_history(code):
    fdr, err = get_fdr()
    if fdr is None:
        return pd.DataFrame(), str(err)

    end = datetime.date.today()
    start = end - datetime.timedelta(days=365 * 5)

    try:
        df = fdr.DataReader(str(code), start, end)
        if df is None or df.empty:
            return pd.DataFrame(), "주가 데이터 없음"

        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        if "Close" not in df.columns:
            return pd.DataFrame(), f"Close 컬럼 없음: {list(df.columns)}"

        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


def analyze_price(df, benchmark_df=None):
    if df is None or df.empty or "Close" not in df.columns:
        return {
            "current": 0.0,
            "r5y": 0.0,
            "r1y": 0.0,
            "r3m": 0.0,
            "r1m": 0.0,
            "high52": 0.0,
            "drawdown": 0.0,
            "volatility": 0.0,
            "avg_volume": 0.0,
            "volume_ratio": 1.0,
            "relative_1y": 0.0,
        }

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    volume = (
        pd.to_numeric(df["Volume"], errors="coerce").dropna()
        if "Volume" in df.columns
        else pd.Series(dtype=float)
    )

    current = float(close.iloc[-1])

    def ret_days(days):
        target = df.index[-1] - pd.Timedelta(days=days)
        sub = close[close.index >= target]
        if len(sub) < 2 or sub.iloc[0] == 0:
            return 0.0
        return float((current / sub.iloc[0] - 1) * 100)

    r5y = (
        (current / float(close.iloc[0]) - 1) * 100
        if close.iloc[0] > 0 else 0.0
    )

    r1y = ret_days(365)
    r3m = ret_days(90)
    r1m = ret_days(30)

    one_year = close[close.index >= close.index[-1] - pd.Timedelta(days=365)]
    high52 = float(one_year.max()) if not one_year.empty else current
    high52_position = (current / high52 * 100) if high52 > 0 else 0.0

    recent = close.tail(252)
    drawdown = calc_max_drawdown(recent)
    volatility = calc_volatility(recent)

    avg_volume = float(volume.tail(60).mean()) if not volume.empty else 0.0
    last_volume = float(volume.iloc[-1]) if not volume.empty else avg_volume
    volume_ratio = (
        last_volume / avg_volume
        if avg_volume > 0 else 1.0
    )

    relative_1y = 0.0
    if benchmark_df is not None and not benchmark_df.empty:
        b = pd.to_numeric(benchmark_df["Close"], errors="coerce").dropna()
        if len(b) >= 2:
            b_current = float(b.iloc[-1])
            b_start = b[b.index >= b.index[-1] - pd.Timedelta(days=365)]
            if not b_start.empty and float(b_start.iloc[0]) > 0:
                b_r1y = (b_current / float(b_start.iloc[0]) - 1) * 100
                relative_1y = r1y - b_r1y

    return {
        "current": current,
        "r5y": float(r5y),
        "r1y": float(r1y),
        "r3m": float(r3m),
        "r1m": float(r1m),
        "high52": float(high52_position),
        "drawdown": float(drawdown),
        "volatility": float(volatility),
        "avg_volume": avg_volume,
        "volume_ratio": float(volume_ratio),
        "relative_1y": float(relative_1y),
    }


# ============================================================
# 6. SCORE ENGINE
# ============================================================
def score_stock(metrics, marcap):
    """
    100점 체계
    - 장기 추세 20
    - 1년 추세 20
    - 3개월/1개월 모멘텀 20
    - 52주 고점 위치 10
    - 상대강도 15
    - 거래량/수급 proxy 5
    - 위험도 10
    """
    r5y = metrics["r5y"]
    r1y = metrics["r1y"]
    r3m = metrics["r3m"]
    r1m = metrics["r1m"]
    high52 = metrics["high52"]
    relative = metrics["relative_1y"]
    volume_ratio = metrics["volume_ratio"]
    volatility = metrics["volatility"]

    long_score = clamp(50 + r5y / 5, 0, 100)
    year_score = clamp(50 + r1y * 1.2, 0, 100)
    momentum_score = clamp(50 + r3m * 1.5 + r1m * 0.7, 0, 100)
    high_score = clamp(high52, 0, 100)
    relative_score = clamp(50 + relative * 1.5, 0, 100)
    volume_score = clamp(50 + (volume_ratio - 1) * 20, 0, 100)

    # 변동성 15% 이하를 비교적 안정적 구간으로 보고 점수 조정
    risk_score = clamp(100 - max(0, volatility - 15) * 3, 0, 100)
    risk_score -= min(metrics["drawdown"] * 0.35, 30)
    risk_score = clamp(risk_score, 0, 100)

    score = (
        long_score * 0.20
        + year_score * 0.20
        + momentum_score * 0.20
        + high_score * 0.10
        + relative_score * 0.15
        + volume_score * 0.05
        + risk_score * 0.10
    )

    # 시총은 품질 보조지표로 소폭 사용
    if marcap >= 10_000_000_000_000:
        score += 2
    elif marcap < 500_000_000_000:
        score -= 2

    return int(round(clamp(score)))


def decision(score, r1y, r3m, drawdown, profit=None):
    """
    점수 + 추세 + 위험 + 보유 수익률로 행동 의견 생성
    """
    if score >= 80 and r3m > 0:
        action = "🟢 적극 보유/추가매수"
        strength = "강한 긍정"
    elif score >= 70:
        action = "🟢 보유"
        strength = "긍정"
    elif score >= 55:
        action = "🟡 관망/분할매수"
        strength = "중립"
    elif score >= 40:
        action = "🟠 비중축소 검토"
        strength = "주의"
    else:
        action = "🔴 매도/교체 검토"
        strength = "부정"

    # 급락/과대손실 상황에서는 무조건 매도를 권하지 않음
    if drawdown >= 35 and score >= 55:
        action = "🟡 보유 + 위험관리"
        strength = "고변동 주의"

    # 보유종목에서 큰 수익이 발생했으나 단기 모멘텀이 꺾인 경우
    if profit is not None and profit >= 40 and r3m < -10:
        action = "🟠 일부 차익실현 검토"
        strength = "고수익/모멘텀 둔화"

    return action, strength


# ============================================================
# 7. PARALLEL ANALYSIS
# ============================================================
def analyze_universe(candidates):
    # benchmark
    kospi, _ = get_price_history("KS11")
    kosdaq, _ = get_price_history("KQ11")

    benchmark = kospi if not kospi.empty else kosdaq

    records = []

    def worker(row):
        code = str(row["Code"])
        name = str(row["Name"])
        marcap = safe_num(row["Marcap"])
        volume = safe_num(row["Volume"]) if "Volume" in row.index else 0.0

        df, err = get_price_history(code)
        metrics = analyze_price(df, benchmark)
        score = score_stock(metrics, marcap)

        action, strength = decision(
            score,
            metrics["r1y"],
            metrics["r3m"],
            metrics["drawdown"],
        )

        return {
            "종목명": name,
            "종목코드": code,
            "섹터": classify_sector(name),
            "점수": score,
            "의견": action,
            "판정": strength,
            "거래량": volume,
            "시가총액": marcap,
            "현재가": metrics["current"],
            "5년성장": metrics["r5y"],
            "1년성장": metrics["r1y"],
            "3개월성장": metrics["r3m"],
            "1개월성장": metrics["r1m"],
            "52주고점위치": metrics["high52"],
            "상대강도": metrics["relative_1y"],
            "변동성": metrics["volatility"],
            "최대낙폭": metrics["drawdown"],
            "거래량비율": metrics["volume_ratio"],
            "차트": df,
            "데이터오류": err,
        }

    rows = [row for _, row in candidates.iterrows()]

    max_workers = min(8, max(2, len(rows)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, row) for row in rows]
        for future in as_completed(futures):
            try:
                records.append(future.result())
            except Exception as e:
                records.append({
                    "종목명": "분석오류",
                    "종목코드": "",
                    "섹터": "기타 우량주",
                    "점수": 0,
                    "의견": "데이터 오류",
                    "판정": "오류",
                    "거래량": 0,
                    "시가총액": 0,
                    "현재가": 0,
                    "5년성장": 0,
                    "1년성장": 0,
                    "3개월성장": 0,
                    "1개월성장": 0,
                    "52주고점위치": 0,
                    "상대강도": 0,
                    "변동성": 0,
                    "최대낙폭": 0,
                    "거래량비율": 1,
                    "차트": pd.DataFrame(),
                    "데이터오류": str(e),
                })

    return pd.DataFrame(records), kospi, kosdaq


# ============================================================
# 8. MARKET OUTLOOK
# ============================================================
def market_return(df, days):
    if df is None or df.empty or "Close" not in df.columns:
        return 0.0
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(s) < 2:
        return 0.0
    target = s.index[-1] - pd.Timedelta(days=days)
    sub = s[s.index >= target]
    if len(sub) < 2 or sub.iloc[0] == 0:
        return 0.0
    return float((s.iloc[-1] / sub.iloc[0] - 1) * 100)


def market_outlook(kospi, kosdaq, result_df):
    k1 = market_return(kospi, 365)
    k3 = market_return(kospi, 90)
    q1 = market_return(kosdaq, 365)
    q3 = market_return(kosdaq, 90)

    valid = result_df[result_df["종목명"] != "분석오류"].copy()

    if valid.empty:
        breadth = 50
        avg_score = 50
        hot_ratio = 0
    else:
        breadth = float((valid["3개월성장"] > 0).mean() * 100)
        avg_score = float(valid["점수"].mean())
        hot_ratio = float((valid["점수"] >= 70).mean() * 100)

    score = 50
    score += max(-15, min(15, k1 * 0.5))
    score += max(-10, min(10, k3 * 0.8))
    score += max(-10, min(10, q3 * 0.5))
    score += (breadth - 50) * 0.20
    score += (avg_score - 50) * 0.25
    score = int(round(clamp(score)))

    if score >= 75:
        regime = "🟢 강세"
        message = "시장 추세와 종목 모멘텀이 동시에 양호합니다."
    elif score >= 60:
        regime = "🟢 완만한 강세"
        message = "상승 추세가 우세하지만 종목별 차별화가 필요합니다."
    elif score >= 45:
        regime = "🟡 중립/혼조"
        message = "시장 방향성이 뚜렷하지 않아 분할 접근이 유리합니다."
    elif score >= 30:
        regime = "🟠 약세"
        message = "추세가 약해 현금비중과 손실관리가 중요합니다."
    else:
        regime = "🔴 강한 약세"
        message = "하락 위험이 높은 구간으로 공격적인 추격매수를 피하는 편이 좋습니다."

    return {
        "score": score,
        "regime": regime,
        "message": message,
        "kospi_1y": k1,
        "kospi_3m": k3,
        "kosdaq_1y": q1,
        "kosdaq_3m": q3,
        "breadth": breadth,
        "avg_score": avg_score,
        "hot_ratio": hot_ratio,
    }


# ============================================================
# 9. NEWS
# ============================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_news(name, limit=5):
    result = []
    try:
        q = requests.utils.quote(f"{name} 주식")
        url = (
            "https://news.google.com/rss/search"
            f"?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        )
        r = requests.get(
            url,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                if title is not None and title.text:
                    result.append({
                        "title": title.text.strip(),
                        "link": link.text.strip() if link is not None and link.text else "",
                    })
                if len(result) >= limit:
                    break
    except Exception:
        pass

    return result


# ============================================================
# 10. UI HEADER
# ============================================================
st.markdown(
    '<p class="main-title">AI 마켓 맵 PRO</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="sub-title">'
    "시장 흐름 → 종목 점수 → 보유종목 진단 → 매수/보유/매도 의견"
    "</p>",
    unsafe_allow_html=True,
)


# ============================================================
# 11. SIDEBAR
# ============================================================
with st.sidebar:
    st.header("⚙️ 분석 설정")

    universe_limit = st.slider(
        "시장 분석 종목 수",
        min_value=10,
        max_value=60,
        value=30,
        step=5,
        help="많을수록 분석 시간이 증가합니다.",
    )

    run_analysis = st.button(
        "🚀 전체 시장 분석 실행",
        type="primary",
        use_container_width=True,
    )

    st.divider()

    st.markdown("### 📌 점수 구성")
    st.caption(
        "장기추세 20% · 1년추세 20% · "
        "단기모멘텀 20% · 고점위치 10% · "
        "상대강도 15% · 거래량 5% · 위험도 10%"
    )

    st.divider()
    st.caption(
        "※ 본 프로그램은 투자자문/매매지시가 아닌 "
        "데이터 기반 분석 도구입니다."
    )


# ============================================================
# 12. PORTFOLIO INPUT
# ============================================================
st.markdown("### 💼 내 보유종목")

st.caption(
    "종목명, 보유수량, 평균매수가를 입력하세요. "
    "수량/매수가는 선택 입력이며 비워도 시장 분석은 가능합니다."
)

if "portfolio_editor" not in st.session_state:
    st.session_state["portfolio_editor"] = pd.DataFrame({
        "종목명": [
            "두산로보틱스",
            "한화오션",
            "테스",
            "에스에이엠티",
        ],
        "보유수량": [0, 0, 0, 0],
        "평균매수가": [0, 0, 0, 0],
    })

portfolio_input = st.data_editor(
    st.session_state["portfolio_editor"],
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "종목명": st.column_config.TextColumn("종목명"),
        "보유수량": st.column_config.NumberColumn(
            "보유수량",
            min_value=0,
            step=1,
        ),
        "평균매수가": st.column_config.NumberColumn(
            "평균매수가",
            min_value=0,
            step=100,
            format="%.0f",
        ),
    },
    key="portfolio_editor_widget",
)


# ============================================================
# 13. RUN
# ============================================================
if run_analysis:
    fdr, fdr_error = get_fdr()

    if fdr is None:
        st.error("❌ FinanceDataReader를 불러오지 못했습니다.")
        st.code(str(fdr_error))
        st.code("python -m pip install -U finance-datareader")
        st.stop()

    try:
        with st.spinner("KRX 종목 목록을 불러오는 중..."):
            candidates = load_candidates(universe_limit)

        with st.spinner(
            f"📡 {len(candidates)}개 종목의 5년 데이터를 병렬 분석 중..."
        ):
            result_df, kospi, kosdaq = analyze_universe(candidates)

        result_df = result_df.sort_values(
            ["점수", "시가총액"],
            ascending=[False, False],
        ).reset_index(drop=True)

        outlook = market_outlook(
            kospi,
            kosdaq,
            result_df,
        )

        # portfolio analysis
        krx = load_krx()
        portfolio_records = []

        for _, p in portfolio_input.iterrows():
            name = str(p.get("종목명", "")).strip()
            qty = safe_num(p.get("보유수량", 0))
            avg_price = safe_num(p.get("평균매수가", 0))

            if not name or name == "nan":
                continue

            info = krx[
                krx["Name"].astype(str).str.strip() == name
            ]

            if info.empty:
                portfolio_records.append({
                    "종목명": name,
                    "보유수량": qty,
                    "평균매수가": avg_price,
                    "현재가": 0,
                    "평가금액": 0,
                    "손익": 0,
                    "수익률": 0,
                    "점수": 0,
                    "의견": "종목을 찾지 못함",
                    "차트": pd.DataFrame(),
                })
                continue

            row = info.iloc[0]
            code = str(row["Code"]).strip()
            marcap = safe_num(row["Marcap"])

            df_price, err = get_price_history(code)
            metrics = analyze_price(df_price, kospi)
            score = score_stock(metrics, marcap)

            current = metrics["current"]
            profit = (
                ((current / avg_price) - 1) * 100
                if avg_price > 0 and current > 0
                else 0
            )

            action, strength = decision(
                score,
                metrics["r1y"],
                metrics["r3m"],
                metrics["drawdown"],
                profit if avg_price > 0 else None,
            )

            eval_value = current * qty
            pnl = (current - avg_price) * qty if avg_price > 0 else 0

            portfolio_records.append({
                "종목명": name,
                "종목코드": code,
                "보유수량": qty,
                "평균매수가": avg_price,
                "현재가": current,
                "평가금액": eval_value,
                "손익": pnl,
                "수익률": profit,
                "점수": score,
                "의견": action,
                "판정": strength,
                "1년성장": metrics["r1y"],
                "3개월성장": metrics["r3m"],
                "1개월성장": metrics["r1m"],
                "52주고점위치": metrics["high52"],
                "상대강도": metrics["relative_1y"],
                "변동성": metrics["volatility"],
                "최대낙폭": metrics["drawdown"],
                "차트": df_price,
                "데이터오류": err,
            })

        portfolio_df = pd.DataFrame(portfolio_records)

        st.session_state["result_df"] = result_df
        st.session_state["kospi"] = kospi
        st.session_state["kosdaq"] = kosdaq
        st.session_state["outlook"] = outlook
        st.session_state["portfolio_df"] = portfolio_df
        st.session_state["analysis_done"] = True

        st.success(
            f"✅ 분석 완료: {len(result_df)}개 종목 + "
            f"{len(portfolio_df)}개 보유종목"
        )

    except Exception as e:
        st.error("❌ 분석 중 오류가 발생했습니다.")
        st.exception(e)


# ============================================================
# 14. RESULTS
# ============================================================
if st.session_state.get("analysis_done", False):
    result_df = st.session_state["result_df"]
    kospi = st.session_state["kospi"]
    kosdaq = st.session_state["kosdaq"]
    outlook = st.session_state["outlook"]
    portfolio_df = st.session_state["portfolio_df"]

    tabs = st.tabs([
        "🤖 AI 시장 전망",
        "🗺️ 시장 맵",
        "🏆 종목 랭킹",
        "💼 내 포트폴리오",
        "🔍 종목 상세",
        "📰 뉴스",
    ])

    # --------------------------------------------------------
    # AI OUTLOOK
    # --------------------------------------------------------
    with tabs[0]:
        st.markdown("## 🤖 AI 시장 전망")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("시장 종합점수", f"{outlook['score']}/100")
        c2.metric("KOSPI 3개월", f"{outlook['kospi_3m']:+.2f}%")
        c3.metric("KOSDAQ 3개월", f"{outlook['kosdaq_3m']:+.2f}%")
        c4.metric("상승 종목 비율", f"{outlook['breadth']:.1f}%")

        st.markdown(
            f"### 현재 시장 국면: {outlook['regime']}"
        )
        st.info(outlook["message"])

        st.markdown("### 📊 시장 진단 근거")

        reasons = []

        if outlook["kospi_3m"] > 5:
            reasons.append("KOSPI 3개월 추세가 강한 상승")
        elif outlook["kospi_3m"] < -5:
            reasons.append("KOSPI 3개월 추세가 약한 하락")
        else:
            reasons.append("KOSPI 3개월 추세는 혼조")

        if outlook["breadth"] >= 60:
            reasons.append("분석 대상 종목 중 상승 종목 비율 양호")
        elif outlook["breadth"] <= 40:
            reasons.append("시장 내부 상승 폭이 좁음")

        if outlook["avg_score"] >= 65:
            reasons.append("상위 종목의 추세 점수 양호")
        elif outlook["avg_score"] < 50:
            reasons.append("상위 종목의 추세 점수가 낮음")

        for r in reasons:
            st.markdown(f"- {r}")

        st.markdown("### 🧭 시장 대응전략")
        if outlook["score"] >= 70:
            st.success(
                "강세장 대응: 추세가 강한 섹터 중심으로 접근하되 "
                "급등 종목 추격매수는 피하고 분할매수를 우선하세요."
            )
        elif outlook["score"] >= 55:
            st.info(
                "중립 이상: 시장 전체를 사기보다 점수 70점 이상 "
                "종목과 강한 섹터를 선별하는 전략이 유리합니다."
            )
        elif outlook["score"] >= 40:
            st.warning(
                "혼조장: 현금비중을 확보하고 조정 시 분할 접근을 "
                "우선하는 전략이 적절합니다."
            )
        else:
            st.error(
                "약세장: 공격적인 추가매수보다 손실관리와 "
                "현금확보를 우선하는 것이 좋습니다."
            )

    # --------------------------------------------------------
    # MARKET MAP
    # --------------------------------------------------------
    with tabs[1]:
        st.markdown("## 🗺️ 시장 전체 Treemap")

        tree = result_df.copy()
        tree = tree[tree["종목명"] != "분석오류"]

        if not tree.empty:
            tree["전체시장"] = "KOSPI / KOSDAQ"
            tree["크기"] = tree["시가총액"].clip(lower=1)

            fig = px.treemap(
                tree,
                path=["전체시장", "섹터", "종목명"],
                values="크기",
                color="점수",
                color_continuous_scale=[
                    "#0b486b",
                    "#3b8d99",
                    "#cccccc",
                    "#f56217",
                    "#ff0000",
                ],
                range_color=[30, 85],
            )
            fig.update_layout(
                height=750,
                margin=dict(t=10, l=10, r=10, b=10),
                coloraxis_showscale=False,
            )
            fig.update_traces(
                textinfo="label",
                hovertemplate=(
                    "<b>%{label}</b>"
                    "<br>시가총액: %{value:,.0f}"
                    "<br>점수: %{color:.0f}"
                    "<extra></extra>"
                ),
            )
            st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------------------------
    # RANKING
    # --------------------------------------------------------
    with tabs[2]:
        st.markdown("## 🏆 종목 랭킹")

        display_cols = [
            "종목명", "섹터", "점수", "의견",
            "현재가", "1년성장", "3개월성장",
            "1개월성장", "52주고점위치",
            "상대강도", "변동성", "최대낙폭",
        ]

        rank_view = result_df[display_cols].copy()

        st.dataframe(
            rank_view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "점수": st.column_config.ProgressColumn(
                    "점수",
                    min_value=0,
                    max_value=100,
                    format="%d",
                ),
                "현재가": st.column_config.NumberColumn(
                    "현재가", format="%,.0f"
                ),
                "1년성장": st.column_config.NumberColumn(
                    "1년", format="%+.2f%%"
                ),
                "3개월성장": st.column_config.NumberColumn(
                    "3개월", format="%+.2f%%"
                ),
                "1개월성장": st.column_config.NumberColumn(
                    "1개월", format="%+.2f%%"
                ),
                "52주고점위치": st.column_config.NumberColumn(
                    "52주 고점 위치", format="%.1f%%"
                ),
                "상대강도": st.column_config.NumberColumn(
                    "시장 대비", format="%+.2f%%"
                ),
                "변동성": st.column_config.NumberColumn(
                    "변동성", format="%.1f%%"
                ),
                "최대낙폭": st.column_config.NumberColumn(
                    "최대낙폭", format="%.1f%%"
                ),
            },
        )

        st.markdown("### 🔥 상위 10종목")
        top10 = result_df.head(10)[
            ["종목명", "섹터", "점수", "의견", "1년성장", "3개월성장"]
        ]
        st.dataframe(
            top10,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # PORTFOLIO
    # --------------------------------------------------------
    with tabs[3]:
        st.markdown("## 💼 내 포트폴리오 진단")

        if portfolio_df.empty:
            st.info(
                "상단에서 종목명과 보유수량/평균매수가를 입력하고 "
                "분석을 다시 실행하세요."
            )
        else:
            valid = portfolio_df[portfolio_df["현재가"] > 0].copy()

            total_value = float(valid["평가금액"].sum()) if not valid.empty else 0
            total_pnl = float(valid["손익"].sum()) if not valid.empty else 0
            total_cost = (
                float((valid["평균매수가"] * valid["보유수량"]).sum())
                if not valid.empty else 0
            )
            total_return = (
                total_pnl / total_cost * 100
                if total_cost > 0 else 0
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 평가금액", f"{total_value:,.0f}원")
            c2.metric("총 손익", f"{total_pnl:+,.0f}원")
            c3.metric("총 수익률", f"{total_return:+.2f}%")
            c4.metric(
                "평균 종목점수",
                f"{valid['점수'].mean():.1f}" if not valid.empty else "-",
            )

            pcols = [
                "종목명", "보유수량", "평균매수가", "현재가",
                "평가금액", "손익", "수익률",
                "점수", "의견", "판정",
            ]

            st.dataframe(
                portfolio_df[pcols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "평균매수가": st.column_config.NumberColumn(
                        "평균매수가", format="%,.0f원"
                    ),
                    "현재가": st.column_config.NumberColumn(
                        "현재가", format="%,.0f원"
                    ),
                    "평가금액": st.column_config.NumberColumn(
                        "평가금액", format="%,.0f원"
                    ),
                    "손익": st.column_config.NumberColumn(
                        "손익", format="%+.0f원"
                    ),
                    "수익률": st.column_config.NumberColumn(
                        "수익률", format="%+.2f%%"
                    ),
                    "점수": st.column_config.ProgressColumn(
                        "점수", min_value=0, max_value=100
                    ),
                },
            )

            st.markdown("### 🎯 종목별 행동 의견")

            for _, row in portfolio_df.iterrows():
                if row["현재가"] <= 0:
                    continue

                if str(row["의견"]).startswith("🟢"):
                    st.success(
                        f"**{row['종목명']}** → {row['의견']} "
                        f"(점수 {row['점수']}, 수익률 {row['수익률']:+.2f}%)"
                    )
                elif str(row["의견"]).startswith("🔴"):
                    st.error(
                        f"**{row['종목명']}** → {row['의견']} "
                        f"(점수 {row['점수']}, 수익률 {row['수익률']:+.2f}%)"
                    )
                else:
                    st.warning(
                        f"**{row['종목명']}** → {row['의견']} "
                        f"(점수 {row['점수']}, 수익률 {row['수익률']:+.2f}%)"
                    )

    # --------------------------------------------------------
    # DETAIL
    # --------------------------------------------------------
    with tabs[4]:
        st.markdown("## 🔍 종목 상세 분석")

        names = result_df["종목명"].tolist()
        selected = st.selectbox(
            "분석할 종목",
            names,
        )

        row = result_df[result_df["종목명"] == selected].iloc[0]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("종합점수", f"{row['점수']}/100")
        c2.metric("1년 수익률", f"{row['1년성장']:+.2f}%")
        c3.metric("3개월", f"{row['3개월성장']:+.2f}%")
        c4.metric("시장 대비", f"{row['상대강도']:+.2f}%")
        c5.metric("변동성", f"{row['변동성']:.1f}%")

        st.markdown(
            f"### {row['종목명']} · {row['섹터']}"
        )
        st.info(
            f"현재 판단: **{row['의견']}** / "
            f"{row['판정']}"
        )

        chart = row["차트"]

        if isinstance(chart, pd.DataFrame) and not chart.empty:
            close = chart["Close"].dropna()

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=close.index,
                    y=close.values,
                    mode="lines",
                    name="종가",
                )
            )
            fig.update_layout(
                height=450,
                margin=dict(t=20, l=10, r=10, b=10),
                xaxis_title="",
                yaxis_title="가격",
            )
            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        metrics_table = pd.DataFrame({
            "지표": [
                "5년 수익률",
                "1년 수익률",
                "3개월 수익률",
                "1개월 수익률",
                "52주 고점 대비 위치",
                "시장 대비 상대강도",
                "연환산 변동성",
                "최대낙폭",
                "최근 거래량 / 60일 평균",
            ],
            "값": [
                f"{row['5년성장']:+.2f}%",
                f"{row['1년성장']:+.2f}%",
                f"{row['3개월성장']:+.2f}%",
                f"{row['1개월성장']:+.2f}%",
                f"{row['52주고점위치']:.1f}%",
                f"{row['상대강도']:+.2f}%",
                f"{row['변동성']:.1f}%",
                f"{row['최대낙폭']:.1f}%",
                f"{row['거래량비율']:.2f}배",
            ],
        })
        st.dataframe(
            metrics_table,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # NEWS
    # --------------------------------------------------------
    with tabs[5]:
        st.markdown("## 📰 종목 뉴스")

        news_name = st.selectbox(
            "뉴스를 볼 종목",
            result_df["종목명"].tolist(),
            key="news_stock",
        )

        news = get_news(news_name, 5)

        if not news:
            st.info("최근 뉴스를 가져오지 못했습니다.")
        else:
            for item in news:
                title = html.escape(item["title"])
                link = item["link"]

                if link:
                    st.markdown(
                        f"- [{title}]({link})"
                    )
                else:
                    st.markdown(f"- {title}")

else:
    st.info(
        "왼쪽 사이드바에서 **시장 분석 종목 수**를 선택하고 "
        "🚀 **전체 시장 분석 실행**을 눌러주세요."
    )

    st.markdown(
        """
        ### 🚀 이번 버전의 핵심 개선

        **① 속도**
        - 종목별 데이터를 병렬 수집
        - 캐시 적용
        - 분석 종목 수 조절

        **② 실제 투자점수**
        - 단순 5년/1년 수익률에서 탈피
        - 1개월/3개월/1년/5년 추세
        - 시장 대비 상대강도
        - 52주 고점 위치
        - 변동성/최대낙폭
        - 거래량 변화

        **③ 보유종목**
        - 보유수량
        - 평균매수가
        - 현재가
        - 평가금액
        - 손익
        - 수익률

        **④ 행동 의견**
        - 🟢 적극 보유/추가매수
        - 🟢 보유
        - 🟡 관망/분할매수
        - 🟠 비중축소 검토
        - 🔴 매도/교체 검토

        **⑤ AI 시장 전망**
        - KOSPI/KOSDAQ 추세
        - 시장 내부 상승비율
        - 종목 평균점수
        - 강세 종목 비율
        을 종합해 시장 국면을 판정합니다.
        """
    )
