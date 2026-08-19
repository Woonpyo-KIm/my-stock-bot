import streamlit as st
import pandas as pd
import requests
import time
import datetime
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET

# -------------------------------------------------------------------
# [1] 웹페이지 디자인
# -------------------------------------------------------------------
st.set_page_config(page_title="AI 메가트렌드 발굴기", page_icon="🗺️", layout="centered")

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(45deg, #6a11cb, #2575fc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
        padding-top: 1rem;
    }
    .sub-title {
        text-align: center;
        color: #666;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .megatrend-tag {
        display: inline-block;
        padding: 0.2rem 0.5rem;
        border-radius: 5px;
        background-color: #f1f3f5;
        color: #0b486b;
        font-weight: bold;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# [2] 백엔드 로직 (5년 데이터 + 메가트렌드 테마 매칭)
# -------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_universe():
    df_krx = fdr.StockListing('KRX')
    # 시가총액 1.5조 이상 우량주 중 상위 25개 필터링
    blue_chips = df_krx[df_krx['Marcap'] >= 1500000000000].sort_values(by='Marcap', ascending=False)
    candidates = blue_chips.head(25)
    return candidates, df_krx

def get_5y_growth_data(stock_code):
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365 * 5)
    try:
        df = fdr.DataReader(stock_code, start_date, end_date)
        if len(df) < 250: return 0.0, 0.0
        current_price = df['Close'].iloc[-1]
        price_5y_ago = df['Close'].iloc[0]
        return_5y = ((current_price / price_5y_ago) - 1) * 100
        
        df_1y = df.loc[df.index >= pd.to_datetime(end_date - datetime.timedelta(days=365))]
        return_1y = ((current_price / df_1y['Close'].iloc[0]) - 1) * 100 if not df_1y.empty else return_5y
        return round(return_5y, 2), round(return_1y, 2)
    except: return 0.0, 0.0

def get_robust_news(stock_name, limit=3):
    news_list = []
    try:
        url = f"https://news.google.com/rss/search?q={stock_name}+주식+성장+미래&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            for item in root.findall('.//item/title'):
                news_list.append(item.text.replace(' - Yahoo Finance', '').replace(' - Naver', '').strip())
                if len(news_list) >= limit: break
    except: pass
    if not news_list: news_list = ["최신 뉴스 수집 불가"]
    while len(news_list) < limit: news_list.append("-")
    return news_list[:limit]

# 🗺️ [핵심 업데이트] 미래 로드맵 기반 메가트렌드 딕셔너리
MEGATRENDS = {
    "🤖 로보틱스/자동화 (5년 내)": ["로봇", "자동화", "스마트팩토리", "휴머노이드", "AI로봇", "협동로봇"],
    "⚡ AI 인프라/반도체 (1~3년 내)": ["AI", "반도체", "HBM", "NPU", "전력", "데이터센터", "인공지능", "메모리"],
    "🚢 글로벌 인프라/지정학 (1~5년 내)": ["조선", "방산", "수주", "원전", "SMR", "수출", "에너지"],
    "🧬 바이오/헬스케어 (5~10년 내)": ["바이오", "신약", "헬스케어", "의료", "합성생물학"],
    "🚀 미래 모빌리티/우주 (10년 내)": ["자율주행", "UAM", "우주", "항공", "배터리"]
}

def evaluate_megatrend_stock(stock_name, return_5y, return_1y, news_list):
    score = 50
    reasons = []
    matched_trend = "일반 우량주"

    # 1. 5년 & 1년 주가 모멘텀
    if return_5y > 50: score += 15; reasons.append(f"5년 장기우상향(+{return_5y}%)")
    elif return_5y < 0: score -= 10; reasons.append(f"장기 추세 둔화")
    if return_1y > 15: score += 10; reasons.append(f"단기 모멘텀 강세")

    # 2. 미래 메가트렌드 매칭 및 가점
    trend_scores = {trend: 0 for trend in MEGATRENDS}
    
    # 종목명이나 뉴스에 트렌드 키워드가 있는지 검사
    search_text = stock_name + " " + " ".join(news_list)
    
    for trend, keywords in MEGATRENDS.items():
        for kw in keywords:
            if kw in search_text:
                trend_scores[trend] += 1

    # 가장 많이 매칭된 트렌드 찾기
    best_trend = max(trend_scores, key=trend_scores.get)
    if trend_scores[best_trend] > 0:
        matched_trend = best_trend
        score += 20 # 로드맵 트렌드에 속하면 강력한 가점 부여
        reasons.append(f"핵심 트렌드 부합")

    is_triggered = True if matched_trend != "일반 우량주" and return_1y > 0 else False

    return max(0, min(100, score)), matched_trend, "🔥 트렌드 주도" if is_triggered else "관망", ", ".join(reasons)

# -------------------------------------------------------------------
# [3] 프론트엔드 (화면 구성)
# -------------------------------------------------------------------
st.markdown('<p class="main-title">미래 30년 로드맵 투자 지표</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">1~5년 내 세상을 바꿀 메가트렌드 주도주를 포착합니다</p>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💼 내 포트폴리오 트렌드 진단")
    user_input = st.text_input(
        "분석할 보유 종목을 쉼표(,)로 입력하세요.", 
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티"
    )

if st.button("🗺️ 메가트렌드 기반 정밀 분석 시작", use_container_width=True, type="primary"):
    
    with st.spinner("AI 로드맵에 기반한 산업 트렌드와 빅데이터 매칭 중... (약 20초 소요)"):
        candidates, df_krx = load_universe()
        eval_results = []
        progress_bar = st.progress(0)
        
        # 1. 시장 추천주 평가
        for idx, row in enumerate(candidates.iterrows()):
            _, r = row
            code, name = r['Code'], r['Name']
            return_5y, return_1y = get_5y_growth_data(code)
            news_list = get_robust_news(name)
            
            score, trend, trigger, summary = evaluate_megatrend_stock(name, return_5y, return_1y, news_list)
            
            eval_results.append({
                '종목명': name, '트렌드': trend, '종합점수': score, 
                '신호': trigger, '5년성장': return_5y, '최신뉴스': news_list[0], '상세평가': summary
            })
            progress_bar.progress(int((idx + 1) / len(candidates) * 50))
            
        result_df = pd.DataFrame(eval_results).sort_values(by='종합점수', ascending=False)
        top_pick = result_df.iloc[0]
        top_pick_name, top_pick_score, top_trend = top_pick['종목명'], top_pick['종합점수'], top_pick['트렌드']

        # 2. 내 포트폴리오 분석
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        my_results = []
        
        for idx, my_stock in enumerate(my_portfolio):
            stock_info = df_krx[df_krx['Name'] == my_stock]
            if stock_info.empty:
                my_results.append({"종목명": my_stock, "점수": 0, "상태": "데이터 없음", "액션": "종목 확인", "알림": "error"})
                continue
                
            code = stock_info.iloc[0]['Code']
            return_5y, return_1y = get_5y_growth_data(code)
            news_list = get_robust_news(my_stock)
            
            my_score, trend, trigger, summary = evaluate_megatrend_stock(my_stock, return_5y, return_1y, news_list)
            
            score_diff = top_pick_score - my_score
            if score_diff >= 20: action, msg_type = f"🚨 트렌드 주도주({top_trend}) 편입 검토", "warning"
            elif score_diff > 0: action, msg_type = "🛡️ 흐름 관망 (유지)", "info"
            else: action, msg_type = "👑 강력 보유 (미래 주도주 편입 완료)", "success"
                
            my_results.append({
                "종목명": my_stock, "트렌드": trend, "점수": my_score, "신호": trigger, 
                "5년성장": return_5y, "요약": summary, "액션": action, 
                "알림": msg_type, "뉴스": news_list[0]
            })
            progress_bar.progress(50 + int((idx + 1) / len(my_portfolio) * 50))
            
        progress_bar.empty()

    # -------------------------------------------------------------------
    # [4] 결과 출력 화면
    # -------------------------------------------------------------------
    tab1, tab2 = st.tabs(["🚀 시장 주도 테마 & 대장주", "💼 내 포트폴리오 트렌드"])
    
    with tab1:
        st.markdown("### 🏆 AI 로드맵 기반 추천 픽")
        with st.container(border=True):
            st.markdown(f"#### 주도 테마: <span class='megatrend-tag'>{top_trend}</span>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.metric("Top Pick", top_pick_name)
            col2.metric("5년 성장률", f"{top_pick['5년성장']}%")
            col3.metric("트렌드 점수", f"{top_pick_score} 점", top_pick['신호'])
            
            st.markdown("---")
            st.markdown(f"**📰 관련 뉴스:** {top_pick['최신뉴스']}")
            st.markdown(f"**💡 AI 진단:** {top_pick['상세평가']}")
        
        with st.expander("📊 향후 1~5년 주도 후보군 Top 5"):
            display_df = result_df[['트렌드', '종목명', '종합점수', '상세평가']].copy()
            st.dataframe(display_df.head(5), hide_index=True)

    with tab2:
        st.markdown("### 내 종목 메가트렌드 매칭 결과")
        for res in my_results:
            if res["알림"] == "error":
                st.error(f"❌ {res['종목명']}: 데이터를 찾을 수 없습니다.")
            else:
                with st.container(border=True):
                    col_a, col_b = st.columns([2, 1])
                    with col_a:
                        st.markdown(f"#### {res['종목명']}")
                        st.markdown(f"<span class='megatrend-tag'>{res['트렌드']}</span>", unsafe_allow_html=True)
                        st.caption(f"뉴스: {res['뉴스']}")
                    with col_b:
                        st.metric("트렌드 점수", f"{res['점수']} 점", res['신호'], delta_color="off")
                    
                    if res["알림"] == "warning": st.warning(f"**Action:** {res['액션']}")
                    elif res["알림"] == "info": st.info(f"**Action:** {res['액션']}")
                    else: st.success(f"**Action:** {res['액션']}")
