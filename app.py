import datetime
import xml.etree.ElementTree as ET
import FinanceDataReader as fdr
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ============================================================
# 0. 기본 설정
# ============================================================

st.set_page_config(
    page_title="AI Market Map",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 1. CSS
# ============================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.5rem;
        font-weight: 900;
        text-align: center;
        background: linear-gradient(45deg, #ff4e50, #1a5293);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-title {
        text-align: center;
        color: #777;
        font-size: 1rem;
        margin-bottom: 25px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 2. 제목
# ============================================================

st.markdown(
    '<div class="main-title">🗺️ AI MARKET MAP</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">한국 증시 섹터 흐름 · 종목 모멘텀 · 보유종목 분석</div>',
    unsafe_allow_html=True,
)

# ============================================================
# 3. 섹터 정의
# ============================================================

SECTORS = {
    "⚡ AI/반도체": [
        "삼성전자",
        "SK하이닉스",
        "한미반도체",
        "테스",
        "에스에이엠티",
        "DB하이텍",
        "리노공업",
        "이오테크닉스",
        "HPSP",
        "원익IPS",
        "반도체",
    ],
    "🤖 로봇/자동화": [
        "두산로보틱스",
        "레인보우로보틱스",
        "로보티즈",
        "뉴로메카",
        "에스피지",
        "로봇",
        "자동화",
    ],
    "🚢 조선/방산": [
        "한화오션",
        "HD현대중공업",
        "HD한국조선해양",
        "삼성중공업",
        "한화에어로스페이스",
        "한국항공우주",
        "LIG넥스원",
        "현대로템",
        "조선",
        "방산",
    ],
    "🧬 바이오/제약": [
        "삼성바이오로직스",
        "셀트리온",
        "유한양행",
        "알테오젠",
        "HLB",
        "바이오",
        "제약",
    ],
    "🚗 자동차/부품": [
        "현대차",
        "기아",
        "현대모비스",
        "HL만도",
        "한온시스템",
        "자동차",
    ],
    "💰 금융/지주": [
        "KB금융",
        "신한지주",
        "하나금융지주",
        "우리금융지주",
        "메리츠금융지주",
        "BNK금융지주",
        "금융",
        "은행",
    ],
    "🔋 2차전지": [
        "LG에너지솔루션",
        "삼성SDI",
        "SK이노베이션",
        "POSCO홀딩스",
        "포스코퓨처엠",
        "에코프로",
        "에코프로비엠",
        "배터리",
        "2차전지",
    ],
    "📱 통신/네트워크": ["SK텔레콤", "KT", "LG유플러스", "통신"],
    "🎬 엔터/게임": [
        "하이브",
        "에스엠",
        "JYP",
        "YG",
        "엔씨소프트",
        "카카오게임즈",
        "넷마블",
        "게임",
        "엔터",
    ],
    "🛒 유통/소비재": [
        "이마트",
        "신세계",
        "롯데쇼핑",
        "아모레퍼시픽",
        "LG생활건강",
        "화장품",
        "유통",
    ],
    "🏗️ 건설/부동산": [
        "현대건설",
        "GS건설",
        "대우건설",
        "DL이앤씨",
        "건설",
        "부동산",
    ],
    "🧪 철강/화학": [
        "POSCO홀딩스",
        "포스코인터내셔널",
        "LG화학",
        "롯데케미칼",
        "금호석유",
        "S-Oil",
        "철강",
        "화학",
    ],
}


def classify_sector(stock_name: str) -> str:
    """종목명을 기준으로 섹터를 분류합니다."""
    name = str(stock_name).strip()
    for sector, keywords in SECTORS.items():
        if any(keyword in name for keyword in keywords):
            return sector
    return "기타"


# ============================================================
# 4. KRX 종목 Universe
# ============================================================


@st.cache_data(ttl=3600, show_spinner=False)
def load_universe():
    df = fdr.StockListing("KRX")

    required = ["Code", "Name", "Marcap"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"FinanceDataReader 데이터에 필요한 컬럼이 없습니다: {', '.join(missing)}"
        )

    df = df.copy()
    df["Code"] = df["Code"].astype(str).str.strip()
    df["Name"] = df["Name"].astype(str).str.strip()
    df["Marcap"] = pd.to_numeric(df["Marcap"], errors="coerce")
    df = df.dropna(subset=["Marcap"])
    df = df.sort_values("Marcap", ascending=False)

    candidates = df[df["Marcap"] >= 1_000_000_000_000].head(100).copy()
    return candidates, df


# ============================================================
# 5. 가격 데이터
# ============================================================


@st.cache_data(ttl=1800, show_spinner=False)
def get_price_data(stock_code: str) -> pd.DataFrame:
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365 * 5 + 30)

    try:
        df = fdr.DataReader(stock_code, start_date, end_date)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.sort_index()
        return df
    except Exception:
        return pd.DataFrame()


# ============================================================
# 6. 분석 유틸리티
# ============================================================


def empty_result(stock_code, stock_name, marcap=0, volume=0):
    return {
        "종목명": stock_name,
        "종목코드": stock_code,
        "섹터": classify_sector(stock_name),
        "시가총액": marcap,
        "거래량": volume,
        "현재가": 0,
        "5년수익률": 0,
        "1년수익률": 0,
        "3개월수익률": 0,
        "거래량모멘텀": 0,
        "변동성": 0,
        "추세점수": 0,
        "점수": 0,
        "차트": pd.DataFrame(),
    }


def analyze_stock(stock_code, stock_name, marcap=0, volume=0):
    df = get_price_data(stock_code)

    if df.empty or "Close" not in df.columns:
        return empty_result(stock_code, stock_name, marcap, volume)

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()

    if len(close) < 20:
        result = empty_result(stock_code, stock_name, marcap, volume)
        result["현재가"] = float(close.iloc[-1]) if len(close) else 0
        result["차트"] = df.tail(70)
        return result

    current = float(close.iloc[-1])

    def calc_return(days):
        target_date = close.index[-1] - pd.Timedelta(days=days)
        previous = close[close.index <= target_date]
        if previous.empty:
            return 0.0
        base = float(previous.iloc[-1])
        return ((current / base) - 1) * 100 if base > 0 else 0.0

    return_5y = calc_return(365 * 5)
    return_1y = calc_return(365)
    return_3m = calc_return(90)

    volume_momentum = 0.0
    if "Volume" in df.columns:
        volume_series = pd.to_numeric(df["Volume"], errors="coerce").dropna()
        if len(volume_series) >= 40:
            recent_avg = float(volume_series.tail(20).mean())
            previous_avg = float(volume_series.iloc[-40:-20].mean())
            if previous_avg > 0:
                volume_momentum = ((recent_avg / previous_avg) - 1) * 100

    daily_return = close.pct_change().dropna()
    volatility = (
        float(daily_return.tail(60).std()) * np.sqrt(252) * 100
        if len(daily_return) >= 2
        else 0.0
    )

    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = (
        float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else ma20
    )
    ma120 = (
        float(close.rolling(120).mean().iloc[-1])
        if len(close) >= 120
        else ma60
    )

    trend_score = 0
    if current > ma20:
        trend_score += 35
    if current > ma60:
        trend_score += 35
    if current > ma120:
        trend_score += 30

    score = 50

    if return_5y >= 100:
        score += 15
    elif return_5y >= 50:
        score += 10
    elif return_5y > 0:
        score += 5
    elif return_5y < -30:
        score -= 10

    if return_1y >= 30:
        score += 15
    elif return_1y >= 15:
        score += 10
    elif return_1y > 0:
        score += 5
    elif return_1y < -20:
        score -= 10

    if return_3m >= 20:
        score += 10
    elif return_3m >= 5:
        score += 5
    elif return_3m < -15:
        score -= 10

    if volume_momentum >= 50:
        score += 10
    elif volume_momentum >= 20:
        score += 5
    elif volume_momentum < -30:
        score -= 5

    if trend_score >= 80:
        score += 10
    elif trend_score >= 60:
        score += 5
    elif trend_score < 35:
        score -= 5

    if volatility > 80:
        score -= 5

    score = int(max(0, min(100, score)))

    return {
        "종목명": stock_name,
        "종목코드": stock_code,
        "섹터": classify_sector(stock_name),
        "시가총액": marcap,
        "거래량": volume,
        "현재가": current,
        "5년수익률": round(return_5y, 2),
        "1년수익률": round(return_1y, 2),
        "3개월수익률": round(return_3m, 2),
        "거래량모멘텀": round(volume_momentum, 2),
        "변동성": round(volatility, 2),
        "추세점수": trend_score,
        "점수": score,
        "차트": df.tail(70),
    }


# ============================================================
# 7. 뉴스
# ============================================================


@st.cache_data(ttl=1800, show_spinner=False)
def get_news(stock_name, limit=5):
    news = []

    try:
        url = (
            "https://news.google.com/rss/search?"
            f"q={requests.utils.quote(stock_name + ' 주식')}"
            "&hl=ko&gl=KR&ceid=KR:ko"
        )

        response = requests.get(
            url,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)

        for item in root.findall(".//item"):
            title = item.find("title")
            if title is not None and title.text:
                text = (
                    title.text.replace(" - Yahoo Finance", "")
                    .replace(" - Naver", "")
                    .strip()
                )
                if text and text not in news:
                    news.append(text)

            if len(news) >= limit:
                break

    except Exception:
        pass

    return news[:limit] if news else ["최근 관련 뉴스가 없습니다."]


# ============================================================
# 8. 신호 판정
# ============================================================


def investment_signal(score):
    if score >= 85:
        return "🟢 강한 관심"
    if score >= 75:
        return "🟢 관심"
    if score >= 60:
        return "🟡 보유/관찰"
    if score >= 45:
        return "🟠 관망"
    return "🔴 주의"


# ============================================================
# 9. 사이드바
# ============================================================

with st.sidebar:
    st.header("⚙️ 분석 설정")

    market_size = st.slider(
        "분석 종목 수",
        min_value=20,
        max_value=50,
        value=40,
        step=5,
    )

    min_market_cap = st.number_input(
        "최소 시가총액 (조원)",
        min_value=0.0,
        max_value=100.0,
        value=1.0,
        step=1.0,
    )

    st.divider()
    st.markdown("### 📊 점수 기준")
    st.write(
        "- **100점 만점**\n"
        "- 장기 추세\n"
        "- 1년/3개월 수익률\n"
        "- 거래량 변화\n"
        "- 이동평균 추세\n"
        "- 변동성"
    )

    st.divider()

    if st.button("🔄 데이터 캐시 초기화", use_container_width=True):
        st.cache_data.clear()
        st.session_state.pop("analysis_complete", None)
        st.success("캐시를 초기화했습니다. 다시 분석해 주세요.")

# ============================================================
# 10. 입력
# ============================================================

with st.container(border=True):
    user_input = st.text_input(
        "💼 내 보유 종목",
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티",
        help="종목명을 쉼표로 구분해서 입력하세요.",
    )

run_analysis = st.button(
    "🗺️ 시장 지도 분석 시작",
    use_container_width=True,
    type="primary",
)

# ============================================================
# 11. 분석 실행
# ============================================================

if run_analysis:
    try:
        with st.spinner("KRX 시장 데이터를 불러오는 중입니다..."):
            candidates, krx = load_universe()

        min_cap = min_market_cap * 1_000_000_000_000
        filtered_candidates = (
            candidates[candidates["Marcap"] >= min_cap]
            .head(market_size)
            .copy()
        )

        if filtered_candidates.empty:
            st.error(
                "조건에 맞는 종목이 없습니다. 최소 시가총액을 낮춰보세요."
            )
            st.stop()

        results = []
        progress = st.progress(0.0)
        total = len(filtered_candidates)

        for i, (_, row) in enumerate(filtered_candidates.iterrows()):
            code = str(row["Code"]).strip()
            name = str(row["Name"]).strip()
            marcap = float(row["Marcap"])
            volume = row.get("Volume", 0)

            result = analyze_stock(code, name, marcap, volume)
            result["보유종목"] = False
            results.append(result)

            progress.progress((i + 1) / total)

        progress.empty()

        my_stocks = [x.strip() for x in user_input.split(",") if x.strip()]

        portfolio_results = []
        normalized_names = krx["Name"].astype(str).str.strip()

        for stock_name in my_stocks:
            match = krx[normalized_names == stock_name]

            if match.empty:
                continue

            row = match.iloc[0]
            code = str(row["Code"]).strip()
            marcap = float(row["Marcap"])
            volume = row.get("Volume", 0)

            result = analyze_stock(code, stock_name, marcap, volume)
            result["보유종목"] = True
            portfolio_results.append(result)

        for item in results:
            item["보유종목"] = item["종목명"] in my_stocks

        all_results = results.copy()
        existing_names = {x["종목명"] for x in all_results}

        for item in portfolio_results:
            if item["종목명"] not in existing_names:
                all_results.append(item)

        result_df = pd.DataFrame(all_results)

        if result_df.empty:
            st.error("분석 결과가 없습니다.")
            st.stop()

        result_df = result_df.sort_values("점수", ascending=False).reset_index(
            drop=True
        )

        st.session_state["market_results"] = result_df
        st.session_state["portfolio_results"] = portfolio_results
        st.session_state["analysis_complete"] = True

    except Exception as e:
        st.error("데이터를 불러오는 과정에서 오류가 발생했습니다.")
        st.exception(e)

# ============================================================
# 12. 결과 표시
# ============================================================

if st.session_state.get("analysis_complete", False):
    df = st.session_state["market_results"]
    portfolio = st.session_state["portfolio_results"]

    top_pick = df.iloc[0]

    st.markdown("## 🏆 오늘의 TOP PICK")

    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("종목", top_pick["종목명"])
        c2.metric("섹터", top_pick["섹터"])
        c3.metric("종합점수", f"{top_pick['점수']}점")
        c4.metric("신호", investment_signal(top_pick["점수"]))
        c5.metric("3개월", f"{top_pick['3개월수익률']:.1f}%")

    st.markdown("## 📊 시장 요약")

    avg_score = df["점수"].mean()
    hot_count = len(df[df["점수"] >= 75])
    cold_count = len(df[df["점수"] <= 40])
    avg_3m = df["3개월수익률"].mean()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("평균 종합점수", f"{avg_score:.1f}")
    c2.metric("HOT 종목", f"{hot_count}개")
    c3.metric("COLD 종목", f"{cold_count}개")
    c4.metric("평균 3개월 수익률", f"{avg_3m:.1f}%")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🗺️ 시장 트리맵", "🔥 섹터 분석", "💼 내 보유종목", "🔍 종목 상세"]
    )

    with tab1:
        st.markdown("### 🗺️ 한국 증시 Market Treemap")
        st.caption("상자 크기 = 시가총액 / 색상 = 종합점수")

        tree = df.copy()
        tree["표시명"] = tree.apply(
            lambda x: "📌 " + x["종목명"] if x["보유종목"] else x["종목명"],
            axis=1,
        )
        tree["시장"] = "KOSPI / KOSDAQ"

        fig = px.treemap(
            tree,
            path=["시장", "섹터", "표시명"],
            values="시가총액",
            color="점수",
            color_continuous_scale=[
                "#0b486b",
                "#3b8d99",
                "#cccccc",
                "#f56217",
                "#ff0000",
            ],
            range_color=[30, 90],
        )

        fig.update_layout(
            margin=dict(t=10, l=10, r=10, b=10),
            coloraxis_showscale=True,
            height=700,
        )

        fig.update_traces(
            textinfo="label",
            hovertemplate=(
                "<b>%{label}</b>"
                "<br>시가총액: %{value:,.0f}"
                "<br>점수: %{color}"
                "<extra></extra>"
            ),
        )

        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown("### 🔥 섹터별 강도")

        sector_df = (
            df.groupby("섹터")
            .agg(
                평균점수=("점수", "mean"),
                평균3개월=("3개월수익률", "mean"),
                평균1년=("1년수익률", "mean"),
                종목수=("종목명", "count"),
            )
            .reset_index()
            .sort_values("평균점수", ascending=False)
        )

        sector_df["평균점수"] = sector_df["평균점수"].round(1)
        sector_df["평균3개월"] = sector_df["평균3개월"].round(1)
        sector_df["평균1년"] = sector_df["평균1년"].round(1)

        fig_sector = px.bar(
            sector_df,
            x="평균점수",
            y="섹터",
            orientation="h",
            text="평균점수",
            color="평균점수",
            color_continuous_scale=["#0b486b", "#cccccc", "#ff0000"],
        )

        fig_sector.update_layout(
            height=600,
            yaxis=dict(categoryorder="total ascending"),
            coloraxis_showscale=False,
        )

        st.plotly_chart(fig_sector, use_container_width=True)
        st.dataframe(sector_df, use_container_width=True, hide_index=True)

    with tab3:
        st.markdown("### 💼 내 보유종목 분석")

        if not portfolio:
            st.warning(
                "입력한 종목을 KRX에서 찾지 못했습니다. "
                "종목명을 정확하게 입력해 주세요."
            )
        else:
            portfolio_df = pd.DataFrame(portfolio).copy()
            portfolio_df["신호"] = portfolio_df["점수"].apply(
                investment_signal
            )

            display_columns = [
                "종목명",
                "섹터",
                "점수",
                "신호",
                "5년수익률",
                "1년수익률",
                "3개월수익률",
                "거래량모멘텀",
                "변동성",
            ]

            st.dataframe(
                portfolio_df[display_columns].sort_values(
                    "점수", ascending=False
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### 📈 보유종목 점수")

            chart_port = portfolio_df[["종목명", "점수"]].sort_values(
                "점수"
            )

            fig_port = px.bar(
                chart_port,
                x="점수",
                y="종목명",
                orientation="h",
                text="점수",
                color="점수",
                color_continuous_scale=["#0b486b", "#cccccc", "#ff0000"],
            )

            fig_port.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig_port, use_container_width=True)

    with tab4:
        st.markdown("### 🔍 개별 종목 상세 분석")

        names = df["종목명"].tolist()
        selected = st.selectbox("분석할 종목", names)
        selected_data = df[df["종목명"] == selected].iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("종합점수", f"{selected_data['점수']}점")
        c2.metric("신호", investment_signal(selected_data["점수"]))
        c3.metric("1년 수익률", f"{selected_data['1년수익률']:.2f}%")
        c4.metric("3개월 수익률", f"{selected_data['3개월수익률']:.2f}%")

        st.markdown("### 📊 투자 지표")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("5년 수익률", f"{selected_data['5년수익률']:.2f}%")
        c2.metric("변동성", f"{selected_data['변동성']:.1f}%")
        c3.metric("추세점수", f"{selected_data['추세점수']} / 100")
        c4.metric("거래량 모멘텀", f"{selected_data['거래량모멘텀']:.1f}%")

        st.markdown("### 📈 최근 주가 흐름")

        chart_df = selected_data["차트"]

        if isinstance(chart_df, pd.DataFrame) and not chart_df.empty:
            chart = chart_df[["Close"]].copy()
            chart.columns = ["종가"]
            st.line_chart(chart, use_container_width=True)
        else:
            st.warning("주가 데이터를 불러오지 못했습니다.")

        st.markdown("### 📰 최근 뉴스")

        with st.spinner("최신 뉴스를 불러오는 중..."):
            news = get_news(selected, 5)

        for i, item in enumerate(news, start=1):
            st.markdown(f"**{i}.** {item}")

    st.markdown("## 🏆 전체 종목 순위")

    ranking_columns = [
        "종목명",
        "섹터",
        "점수",
        "5년수익률",
        "1년수익률",
        "3개월수익률",
        "거래량모멘텀",
        "변동성",
    ]

    ranking = df[ranking_columns].copy()
    ranking["신호"] = ranking["점수"].apply(investment_signal)
    ranking.insert(0, "순위", range(1, len(ranking) + 1))

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
    )

    csv_data = ranking.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ 분석 결과 CSV 다운로드",
        data=csv_data,
        file_name=f"market_map_{datetime.date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

else:
    st.info(
        "👆 위의 **「시장 지도 분석 시작」** 버튼을 누르면 "
        "KRX 시가총액 상위 종목을 분석합니다."
    )

    st.markdown(
        """
        ### 📌 이 앱에서 확인할 수 있는 것

        **① 시장 전체 지도**
        - 시가총액 기반 Treemap
        - 종목별 투자점수
        - 섹터별 자금 집중도

        **② 섹터 강도**
        - AI/반도체
        - 조선/방산
        - 로봇
        - 바이오
        - 자동차
        - 2차전지
        - 금융 등

        **③ 내 보유종목**
        - 종합점수
        - 투자 신호
        - 5년/1년/3개월 수익률
        - 거래량 모멘텀
        - 변동성

        **④ 개별 종목**
        - 최근 주가 차트
        - 추세점수
        - 거래량 변화
        - 최신 뉴스
        """
    )
