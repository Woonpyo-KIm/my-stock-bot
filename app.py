import streamlit as st
import pandas as pd
import requests
import time
import datetime
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET
import plotly.express as px

# -------------------------------------------------------------------
# [1] 웹페이지 기본 설정 및 디자인
# -------------------------------------------------------------------
st.set_page_config(page_title="AI 시장 섹터 맵", page_icon="🗺️", layout="centered")

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(45deg, #ff4e50, #1a5293);
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
# [2] 백엔드 로직 (12대 섹터 및 데이터 수집)
# -------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_universe():
    df_krx = fdr.StockListing('KRX')
    # 다양한 섹터가 잡히도록 시총 상위 40개 우량주로 확대
    candidates = df_krx[df_krx['Marcap'] >= 1000000000000].sort_values(by='Marcap', ascending=False).head(40)
    return candidates, df_krx

def get_growth_and_chart(stock_code):
    end_date = datetime.date.today()
    start_date_5y = end_date - datetime.timedelta(days=365 * 5)
    start_date_3m = end_date - datetime.timedelta(days=90) # 차트용 3개월 데이터
    
    try:
        df = fdr.DataReader(stock_code, start_date_5y, end_date)
        df_3m = df.loc[df.index >= pd.to_datetime(start_date_3m)]
        
        if len(df) < 250: return 0.0, 0.0, df_3m
        
        current_price = df['Close'].iloc[-1]
        price_5y_ago = df['Close'].iloc[0]
        return_5y = ((current_price / price_5y_ago) - 1) * 100
        
        df_1y = df.loc[df.index >= pd.to_datetime(end_date - datetime.timedelta(days=365))]
        return_1y = ((current_price / df_1y['Close'].iloc[0]) - 1) * 100 if not df_1y.empty else return_5y
        
        return round(return_5y, 2), round(return_1y, 2), df_3m
    except: return 0.0, 0.0, pd.DataFrame()

def get_robust_news(stock_name, limit=3):
    news_list = []
    try:
        url = f"https://news.google.com/rss/search?q={stock_name}+주식&hl=ko&gl=KR&ceid=KR:ko"
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

# 💡 [핵심] 유망~침체까지 12개 섹터 총망라
SECTORS = {
    "⚡ AI/반도체": ["AI", "반도체", "HBM", "테스", "에스에이엠티", "SK하이닉스", "삼성전자", "한미반도체"],
    "🤖 로봇/자동화": ["로봇", "자동화", "스마트팩토리", "두산로보틱스", "레인보우로보틱스"],
    "🚢 조선/방산": ["조선", "방산", "수주", "한화오션", "HD현대", "한국항공우주"],
    "🧬 바이오/제약": ["바이오", "신약", "제약", "삼성바이오로직스", "셀트리온", "유한양행"],
    "🚗 자동차/부품": ["자동차", "현대차", "기아", "현대모비스", "만도"],
    "💰 금융/지주사": ["금융", "은행", "지주", "배당", "KB금융", "신한지주", "하나금융지주"],
    "🔋 2차전지/배터리": ["배터리", "2차전지", "에코프로", "LG에너지솔루션", "포스코퓨처엠"],
    "📱 통신/네트워크": ["통신", "SK텔레콤", "KT", "LG유플러스"],
    "🎬 엔터/게임": ["엔터", "게임", "콘텐츠", "하이브", "엔씨소프트", "카카오"],
    "🛒 유통/소비재": ["유통", "쇼핑", "화장품", "이마트", "신세계", "아모레퍼시픽"],
    "🏗️ 건설/부동산": ["건설", "부동산", "건축", "현대건설", "GS건설", "대우건설"],
    "🧪 철강/화학": ["철강", "화학", "석유", "포스코홀딩스", "LG화학", "S-Oil"]
}

def evaluate_stock(stock_name, return_5y, return_1y):
    # 철저히 실제 모멘텀(수익률)을 기반으로 점수를 매겨 빨간색과 파란색을 구분
    score = 50
    matched_sector = "기타 우량주"

    if return_5y > 50: score += 15
    elif return_5y < 0: score -= 15
    if return_1y > 15: score += 15
    elif return_1y < -10: score -= 15

    for sec, keywords in SECTORS.items():
        if any(kw in stock_name for kw in keywords):
            matched_sector = sec
            break

    return max(0, min(100, score)), matched_sector

# -------------------------------------------------------------------
# [3] 프론트엔드 UI
# -------------------------------------------------------------------
st.markdown('<p class="main-title">AI 마켓 맵 & 종목 스캐너</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">12대 섹터의 자금 흐름과 종목별 상세 정보를 확인하세요</p>', unsafe_allow_html=True)

with st.container(border=True):
    user_input = st.text_input(
        "💼 내 보유 종목 (쉼표로 구분)", 
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티"
    )

if st.button("🗺️ 시장 지도 그리기 및 분석 시작", use_container_width=True, type="primary"):
    
    with st.spinner("12대 섹터 데이터 분류 및 트리맵 렌더링 중..."):
        candidates, df_krx = load_universe()
        
        # 1. 시장 추천주 평가
        eval_results = []
        for idx, row in enumerate(candidates.iterrows()):
            _, r = row
            code, name, vol = r['Code'], r['Name'], r['Volume']
            r5y, r1y, df_chart = get_growth_and_chart(code)
            score, sector = evaluate_stock(name, r5y, r1y)
            
            eval_results.append({
                '종목명': name, '종목코드': code, '섹터': sector, '점수': score, 
                '거래량': vol, '5년성장': r5y, '1년성장': r1y, '차트': df_chart
            })
            
        result_df = pd.DataFrame(eval_results).sort_values(by='점수', ascending=False)
        top_pick = result_df.iloc[0]

        # 2. 내 종목 분석
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        my_results = []
        
        for my_stock in my_portfolio:
            stock_info = df_krx[df_krx['Name'] == my_stock]
            if stock_info.empty: continue
                
            code, vol = stock_info.iloc[0]['Code'], stock_info.iloc[0]['Volume']
            r5y, r1y, df_chart = get_growth_and_chart(code)
            my_score, sector = evaluate_stock(my_stock, r5y, r1y)
                
            my_results.append({
                "종목명": my_stock, "종목코드": code, "섹터": sector, "점수": my_score, 
                "거래량": vol, "5년성장": r5y, "차트": df_chart
            })
            
        # 데이터를 세션에 저장 (상세 조회용)
        st.session_state['all_stocks'] = eval_results + my_results

    # -------------------------------------------------------------------
    # [4] 트리맵 시각화 및 상세 분석 화면
    # -------------------------------------------------------------------
    tab_map, tab_detail = st.tabs(["🗺️ 시장 전체 트리맵", "🔍 개별 종목 상세 분석"])
    
    with tab_map:
        st.markdown("### 📊 실시간 한국 증시 섹터 맵")
        st.caption("🔴 유망/상승(Hot) 섹터 ↔ 🔵 소외/하락(Cold) 섹터")
        
        treemap_data = []
        for res in st.session_state['all_stocks']:
            display_name = f"📌 {res['종목명']}" if res['종목명'] in my_portfolio else res['종목명']
            # 중복 추가 방지
            if not any(res['종목명'] in d['표시명'] for d in treemap_data):
                treemap_data.append({'섹터': res['섹터'], '표시명': display_name, '점수': res['점수'], '크기': 1})

        df_tree = pd.DataFrame(treemap_data)
        df_tree['전체시장'] = "KOSPI / KOSDAQ"

        fig = px.treemap(
            df_tree, path=['전체시장', '섹터', '표시명'], values='크기', color='점수',
            color_continuous_scale=['#0b486b', '#3b8d99', '#cccccc', '#f56217', '#ff0000'], # 네이버 파란색~빨간색
            range_color=[30, 85]
        )
        fig.update_layout(margin=dict(t=10, l=10, r=10, b=10), coloraxis_showscale=False)
        fig.update_traces(textinfo="label+value", textfont=dict(size=14, color="white"), hoverinfo="label+value")
        
        st.plotly_chart(fig, use_container_width=True)

    with tab_detail:
        st.markdown("### 📈 종목 상세 정보 조회")
        st.caption("트리맵에서 확인한 종목을 선택하면 차트와 뉴스를 볼 수 있습니다.")
        
        if 'all_stocks' in st.session_state:
            # 셀렉트박스로 종목 검색 및 선택
            stock_names = list(set([s['종목명'] for s in st.session_state['all_stocks']]))
            selected_name = st.selectbox("👉 분석할 종목을 선택하세요:", stock_names)
            
            # 선택된 종목 데이터 필터링
            selected_data = next((item for item in st.session_state['all_stocks'] if item["종목명"] == selected_name), None)
            
            if selected_data:
                # 최신 뉴스 실시간 로드
                with st.spinner("최신 뉴스 수집 중..."):
                    news_list = get_robust_news(selected_name, 3)
                
                with st.container(border=True):
                    col1, col2, col3 = st.columns([1, 1, 1])
                    col1.metric("종목명", selected_name)
                    col2.metric("섹터 / 평가 점수", f"{selected_data['섹터']} ({selected_data['점수']}점)")
                    col3.metric("오늘 거래량", f"{selected_data['거래량']:,} 주")
                    
                    st.markdown("#### 📉 최근 3개월 주가 흐름")
                    if not selected_data['차트'].empty:
                        st.line_chart(selected_data['차트']['Close'], use_container_width=True)
                    else:
                        st.write("차트 데이터를 불러올 수 없습니다.")
                        
                    st.markdown("#### 📰 최신 종목 뉴스")
                    for news in news_list:
                        st.markdown(f"- {news}")
