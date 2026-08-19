import streamlit as st
import pandas as pd
import requests
import time
import datetime
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET
import plotly.express as px  # 트리맵 시각화를 위한 라이브러리

# -------------------------------------------------------------------
# [1] 웹페이지 기본 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="AI 섹터 히트맵 어드바이저", page_icon="🔥", layout="centered")

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(45deg, #ff4e50, #f9d423);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
        padding-top: 1rem;
    }
    .sub-title {
        text-align: center;
        color: #666;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# [2] 백엔드 데이터 로직
# -------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_universe():
    df_krx = fdr.StockListing('KRX')
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

def get_robust_news(stock_name, limit=2):
    news_list = []
    try:
        url = f"https://news.google.com/rss/search?q={stock_name}+주식+성장&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            for item in root.findall('.//item/title'):
                news_list.append(item.text.replace(' - Yahoo Finance', '').replace(' - Naver', '').strip())
                if len(news_list) >= limit: break
    except: pass
    if not news_list: news_list = ["최근 시장 이슈 관망"]
    while len(news_list) < limit: news_list.append("-")
    return news_list[:limit]

MEGATRENDS = {
    "⚡ AI 반도체/인프라": ["AI", "반도체", "HBM", "NPU", "전력", "데이터센터", "메모리", "테스", "에스에이엠티", "SK하이닉스", "삼성전자"],
    "🤖 로보틱스/자동화": ["로봇", "자동화", "스마트팩토리", "휴머노이드", "두산로보틱스", "레인보우로보틱스"],
    "🚢 조선/에너지/지정학": ["조선", "방산", "수주", "원전", "SMR", "한화오션", "HD현대중공업", "HD한국조선해양"],
    "🧬 바이오/헬스케어": ["바이오", "신약", "헬스케어", "의료", "삼성바이오로직스", "셀트리온"],
    "🚀 미래 모빌리티/우주": ["자율주행", "UAM", "우주", "항공", "배터리", "현대차", "기아", "LG에너지솔루션"]
}

def evaluate_stock(stock_name, return_5y, return_1y, news_list):
    score = 50
    matched_sector = "기타 우량주"

    if return_5y > 50: score += 15
    elif return_5y < 0: score -= 10
    if return_1y > 15: score += 10

    search_text = stock_name + " " + " ".join(news_list)
    sector_scores = {sec: 0 for sec in MEGATRENDS}
    
    for sec, keywords in MEGATRENDS.items():
        for kw in keywords:
            if kw in search_text:
                sector_scores[sec] += 1

    best_sec = max(sector_scores, key=sector_scores.get)
    if sector_scores[best_sec] > 0:
        matched_sector = best_sec
        score += 20

    return max(0, min(100, score)), matched_sector

# -------------------------------------------------------------------
# [3] 프론트엔드 UI
# -------------------------------------------------------------------
st.markdown('<p class="main-title">AI 시장 섹터 트리맵 & 리밸런싱</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">네이버 금융 마켓 스타일의 직관적인 섹터 맵핑 및 진단</p>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💼 내 포트폴리오 입력")
    user_input = st.text_input(
        "분석할 보유 종목을 쉼표(,)로 구분해 입력해 주세요.", 
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티"
    )

if st.button("🔥 실시간 섹터 맵 & 퀀트 분석 가동", use_container_width=True, type="primary"):
    
    with st.spinner("섹터별 모멘텀 계산 및 트리맵 렌더링 중..."):
        candidates, df_krx = load_universe()
        
        # 1. 시장 추천주 평가
        eval_results = []
        for idx, row in enumerate(candidates.iterrows()):
            _, r = row
            code, name = r['Code'], r['Name']
            r5y, r1y = get_5y_growth_data(code)
            news = get_robust_news(name)
            score, sector = evaluate_stock(name, r5y, r1y, news)
            
            eval_results.append({
                '종목명': name, '섹터': sector, '점수': score, 
                '5년성장': r5y, '1년성장': r1y, '뉴스': news[0], '타입': '시장후보'
            })
            
        result_df = pd.DataFrame(eval_results).sort_values(by='점수', ascending=False)
        top_pick = result_df.iloc[0]

        # 2. 내 종목 분석
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        my_results = []
        
        for my_stock in my_portfolio:
            stock_info = df_krx[df_krx['Name'] == my_stock]
            if stock_info.empty:
                my_results.append({"종목명": my_stock, "섹터": "기타", "점수": 0, "알림": "error", "타입": "내종목"})
                continue
                
            code = stock_info.iloc[0]['Code']
            r5y, r1y = get_5y_growth_data(code)
            news = get_robust_news(my_stock)
            my_score, sector = evaluate_stock(my_stock, r5y, r1y, news)
            
            diff = top_pick['점수'] - my_score
            if diff >= 20: action, msg_type = f"🚨 1등주({top_pick['종목명']})로 교체 검토", "warning"
            elif diff > 0: action, msg_type = "🛡️ 보유 유지 (상위권)", "info"
            else: action, msg_type = "👑 강력 보유", "success"
                
            my_results.append({
                "종목명": my_stock, "섹터": sector, "점수": my_score, 
                "5년성장": r5y, "액션": action, "알림": msg_type, "뉴스": news[0], "타입": "내종목"
            })

    # -------------------------------------------------------------------
    # [4] 트리맵(Treemap) 시각화 데이터 병합
    # -------------------------------------------------------------------
    # 시장 후보군과 내 종목을 하나로 합쳐서 지도에 그리기 위함
    treemap_data = []
    
    # 1등 픽과 내 종목은 특별한 아이콘(👑, 📌)을 붙여서 지도에서 직관적으로 보이게 함
    for res in eval_results:
        display_name = f"👑 {res['종목명']}" if res['종목명'] == top_pick['종목명'] else res['종목명']
        treemap_data.append({'섹터': res['섹터'], '표시명': display_name, '점수': res['점수'], '크기': 1})
        
    for res in my_results:
        if res['알림'] != 'error':
            # 내 종목이 시장 후보군(위)에 이미 있었는지 중복 체크 후 병합
            if not any(res['종목명'] in d['표시명'] for d in treemap_data):
                treemap_data.append({'섹터': res['섹터'], '표시명': f"📌 {res['종목명']}", '점수': res['점수'], '크기': 1})
            else:
                # 이미 있다면 내 종목 마크만 업데이트
                for d in treemap_data:
                    if res['종목명'] in d['표시명']:
                        d['표시명'] = f"📌👑 {res['종목명']}" if "👑" in d['표시명'] else f"📌 {res['종목명']}"

    df_tree = pd.DataFrame(treemap_data)
    # 루트 노드(시장 전체) 설정
    df_tree['전체시장'] = "🇰🇷 전체 시장 (AI 메가트렌드)"

    # -------------------------------------------------------------------
    # [5] 화면 탭 구성
    # -------------------------------------------------------------------
    tab_map, tab_top, tab_my = st.tabs(["🔥 섹터 트리맵 (마켓 지형도)", "🏆 AI 추천주 Top 5", "💼 내 포트폴리오 진단"])
    
    # [탭 1] 실시간 섹터 트리맵 (네이버 UI 완벽 복제)
    with tab_map:
        st.markdown("### 📊 실시간 AI 주도 섹터 트리맵")
        st.caption("🔴 빨간색일수록 유망/상승(Hot) 섹터이며, 🔵 파란색일수록 둔화/하락(Cold) 섹터입니다. 박스를 터치해 보세요!")
        
        # Plotly를 이용한 계층형 트리맵 생성
        fig = px.treemap(
            df_tree, 
            path=['전체시장', '섹터', '표시명'], # 계층 구조 (전체 -> 섹터 -> 종목)
            values='크기', # 각 박스의 크기 비중
            color='점수', # 점수에 따른 색상 변화
            color_continuous_scale=['#1a5293', '#4579c6', '#d6dde6', '#f2766f', '#d92c2c'], # 네이버 파란색 -> 빨간색 그라데이션
            range_color=[30, 90] # 점수 범위 고정 (극단적 색상 배정용)
        )
        
        fig.update_layout(
            margin=dict(t=10, l=10, r=10, b=10),
            coloraxis_showscale=False # 지저분한 컬러바 숨김
        )
        # 종목 글씨 크기 및 디자인 세팅
        fig.update_traces(
            textinfo="label+value",
            textfont=dict(size=14, color="white"),
            hoverinfo="label+value"
        )
        
        # 화면에 그래프 출력
        st.plotly_chart(fig, use_container_width=True)
        st.info("**범례:** 👑 AI 1등 추천주 | 📌 내 보유 종목")

    # [탭 2] AI 추천주
    with tab_top:
        st.markdown(f"### 🏆 오늘의 시장 전체 1등: **{top_pick['종목명']}**")
        with st.container(border=True):
            col1, col2 = st.columns([1, 1])
            col1.metric("소속 섹터", top_pick['섹터'])
            col2.metric("AI 종합 점수", f"{top_pick['점수']} 점")
            st.markdown(f"**📰 핵심 뉴스:** {top_pick['뉴스']}")
            
        with st.expander("📊 AI 시장 추천주 Top 5 전체 보기"):
            st.dataframe(result_df[['섹터', '종목명', '점수', '5년성장']].head(5), hide_index=True)

    # [탭 3] 내 포트폴리오
    with tab_my:
        st.markdown("### 💼 내 종목 리밸런싱 판정")
        for res in my_results:
            if res["알림"] == "error":
                st.error(f"❌ {res['종목명']}: 데이터를 찾을 수 없습니다.")
            else:
                with st.container(border=True):
                    col_a, col_b = st.columns([2, 1])
                    with col_a:
                        st.markdown(f"#### {res['종목명']} <small style='font-size:0.8rem; color:#888;'>({res['섹터']})</small>", unsafe_allow_html=True)
                        st.caption(f"뉴스: {res['뉴스']}")
                    with col_b:
                        st.metric("종목 점수", f"{res['점수']} 점", delta_color="off")
                    
                    if res["알림"] == "warning": st.warning(f"**Action:** {res['액션']}")
                    elif res["알림"] == "info": st.info(f"**Action:** {res['액션']}")
                    else: st.success(f"**Action:** {res['액션']}")
