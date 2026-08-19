import streamlit as st
import pandas as pd
import requests
import time
import datetime
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET

# -------------------------------------------------------------------
# [1] 웹페이지 기본 설정 및 커스텀 CSS (네이버 주식 히트맵 스타일)
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
    .badge-my {
        background-color: #ffd700;
        color: #000;
        padding: 3px 8px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.8rem;
        display: inline-block;
        margin: 2px;
    }
    .badge-top {
        background-color: #ff4757;
        color: #fff;
        padding: 3px 8px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.8rem;
        display: inline-block;
        margin: 2px;
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

# 5대 메가트렌드 섹터 정의
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
st.markdown('<p class="main-title">AI 시장 섹터 히트맵 & 리밸런싱</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">네이버 금융 마켓 스타일로 한눈에 보는 섹터 지수와 내 종목의 위치</p>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💼 내 포트폴리오 입력")
    user_input = st.text_input(
        "분석할 보유 종목을 쉼표(,)로 구분해 입력해 주세요.", 
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티"
    )

if st.button("🔥 실시간 섹터 맵 & 퀀트 분석 가동", use_container_width=True, type="primary"):
    
    with st.spinner("섹터별 모멘텀 계산 및 내 종목 위치 맵핑 중..."):
        candidates, df_krx = load_universe()
        
        # 1. 시장 추천주 계산
        eval_results = []
        for idx, row in enumerate(candidates.iterrows()):
            _, r = row
            code, name = r['Code'], r['Name']
            r5y, r1y = get_5y_growth_data(code)
            news = get_robust_news(name)
            score, sector = evaluate_stock(name, r5y, r1y, news)
            
            eval_results.append({
                '종목명': name, '섹터': sector, '점수': score, 
                '5년성장': r5y, '1년성장': r1y, '뉴스': news[0]
            })
            
        result_df = pd.DataFrame(eval_results).sort_values(by='점수', ascending=False)
        top_pick = result_df.iloc[0]

        # 2. 내 보유 종목 계산
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        my_results = []
        
        for my_stock in my_portfolio:
            stock_info = df_krx[df_krx['Name'] == my_stock]
            if stock_info.empty:
                my_results.append({"종목명": my_stock, "섹터": "기타", "점수": 0, "알림": "error"})
                continue
                
            code = stock_info.iloc[0]['Code']
            r5y, r1y = get_5y_growth_data(code)
            news = get_robust_news(my_stock)
            my_score, sector = evaluate_stock(my_stock, r5y, r1y, news)
            
            diff = top_pick['점수'] - my_score
            if diff >= 20: action, msg_type = f"🚨 1등주({top_pick['종목명']})로 교체 검토", "warning"
            elif diff > 0: action, msg_type = "🛡️ 보유 유지 (상위권 보유 중)", "info"
            else: action, msg_type = "👑 강력 보유 (시장의 최우수 종목)", "success"
                
            my_results.append({
                "종목명": my_stock, "섹터": sector, "점수": my_score, 
                "5년성장": r5y, "액션": action, "알림": msg_type, "뉴스": news[0]
            })

        # -------------------------------------------------------------------
        # 3. 섹터 점수 집계 (히트맵 색상 판정용)
        # -------------------------------------------------------------------
        sector_summary = {}
        for sec in MEGATRENDS.keys():
            # 추천주 + 내 종목 포함 해당 섹터의 평균 점수 계산
            sec_stocks = [r for r in eval_results + my_results if r['섹터'] == sec]
            avg_score = sum([s['점수'] for s in sec_stocks]) / len(sec_stocks) if sec_stocks else 40.0
            
            # 내 종목 위치 추출
            my_in_sec = [m['종목명'] for m in my_results if m['섹터'] == sec]
            # 추천 1위 위치 추출
            top_in_sec = [top_pick['종목명']] if top_pick['섹터'] == sec else []
            
            sector_summary[sec] = {
                "score": round(avg_score, 1),
                "my_stocks": my_in_sec,
                "top_stock": top_in_sec
            }

        # 점수 순으로 섹터 정렬 (가장 높을수록 핫한 섹터)
        sorted_sectors = sorted(sector_summary.items(), key=lambda x: x[1]['score'], reverse=True)

    # -------------------------------------------------------------------
    # [4] 결과 출력 화면 (탭 분리)
    # -------------------------------------------------------------------
    tab_map, tab_top, tab_my = st.tabs(["🔥 섹터 히트맵 (마켓 지형도)", "🏆 AI 추천주 Top 5", "💼 내 포트폴리오 진단"])
    
    # [탭 1] 실시간 섹터 히트맵 화면
    with tab_map:
        st.markdown("### 📊 실시간 AI 주도 섹터 지형도")
        st.caption("🔴 빨간색일수록 현재 시장의 강력한 주도 섹터이며, 🔵 파란색일수록 둔화된 섹터입니다.")
        
        # 5개 섹터를 점수순에 따라 색상 매핑
        colors = [
            {"bg": "#ff3333", "txt": "#ffffff", "label": "🔥 최강 주도 섹터"},
            {"bg": "#ff7733", "txt": "#ffffff", "label": "☀️ 상승 우세 섹터"},
            {"bg": "#6c757d", "txt": "#ffffff", "label": "➖ 중립 섹터"},
            {"bg": "#3385ff", "txt": "#ffffff", "label": "❄️ 하락 조정 섹터"},
            {"bg": "#004080", "txt": "#ffffff", "label": "🧊 침체/약세 섹터"}
        ]
        
        for rank, (sec_name, sec_data) in enumerate(sorted_sectors):
            color = colors[rank] if rank < len(colors) else colors[-1]
            
            # HTML 카드로 네이버 주식 마켓 느낌 구현
            card_html = f"""
            <div style="background-color: {color['bg']}; color: {color['txt']}; padding: 15px; border-radius: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 1.1rem; font-weight: bold;">{rank+1}. {sec_name}</span>
                    <span style="font-size: 0.9rem; background: rgba(0,0,0,0.2); padding: 2px 8px; border-radius: 8px;">{color['label']} | 평균 {sec_data['score']}점</span>
                </div>
            """
            
            # 내 종목 / AI 1등 픽 위치 뱃지 표시
            badges = ""
            if sec_data['top_stock']:
                for ts in sec_data['top_stock']:
                    badges += f"<span class='badge-top'>👑 AI 1등 추천: {ts}</span> "
            if sec_data['my_stocks']:
                for ms in sec_data['my_stocks']:
                    badges += f"<span class='badge-my'>📌 내 보유 종목: {ms}</span> "
            
            if not badges:
                badges = "<span style='font-size: 0.8rem; opacity: 0.8;'>이 섹터에는 현재 보유/추천 종목이 없습니다.</span>"
                
            card_html += f"<div style='margin-top: 10px;'>{badges}</div></div>"
            st.markdown(card_html, unsafe_allow_html=True)

    # [탭 2] AI 추천주 Top 5
    with tab_top:
        st.markdown(f"### 🏆 오늘의 시장 전체 1등: **{top_pick['종목명']}**")
        with st.container(border=True):
            col1, col2 = st.columns([1, 1])
            col1.metric("소속 섹터", top_pick['섹터'])
            col2.metric("AI 종합 점수", f"{top_pick['점수']} 점")
            st.markdown(f"**📰 핵심 뉴스:** {top_pick['뉴스']}")
            
        with st.expander("📊 AI 시장 추천주 Top 5 전체 보기"):
            st.dataframe(result_df[['섹터', '종목명', '점수', '5년성장']].head(5), hide_index=True)

    # [탭 3] 내 포트폴리오 진단
    with tab_my:
        st.markdown("### 💼 내 종목 섹터 위치 및 리밸런싱 판정")
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
