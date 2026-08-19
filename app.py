import streamlit as st
import pandas as pd
import requests
import time
import datetime
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET

# -------------------------------------------------------------------
# [1] 웹페이지 디자인 및 테마
# -------------------------------------------------------------------
st.set_page_config(page_title="AI 퀀트 (장기성장형)", page_icon="📈", layout="centered")

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(45deg, #11998e, #38ef7d);
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
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# [2] 백엔드 로직 (5년 장기 빅데이터 분석)
# -------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_universe():
    # KRX 전체 상장사 중 시가총액 1.5조 이상의 초대형/우량주만 선별 (안정성 + 성장성)
    df_krx = fdr.StockListing('KRX')
    blue_chips = df_krx[df_krx['Marcap'] >= 1500000000000].sort_values(by='Marcap', ascending=False)
    # 서버 부하를 막기 위해 최상위 20개 주도주 후보군으로 압축
    candidates = blue_chips.head(20)
    return candidates, df_krx

def get_5y_growth_data(stock_code):
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365 * 5)
    
    try:
        df = fdr.DataReader(stock_code, start_date, end_date)
        if len(df) < 250: # 상장된 지 1년 미만인 경우
            return 0.0, 0.0
            
        current_price = df['Close'].iloc[-1]
        
        # 5년 전 가격 (상장한지 5년이 안되었다면 가장 오래된 가격)
        price_5y_ago = df['Close'].iloc[0]
        return_5y = ((current_price / price_5y_ago) - 1) * 100
        
        # 1년 전 가격 (최근 1년 단기 모멘텀 확인용)
        one_year_ago_date = pd.to_datetime(end_date - datetime.timedelta(days=365))
        df_1y = df.loc[df.index >= one_year_ago_date]
        if not df_1y.empty:
            price_1y_ago = df_1y['Close'].iloc[0]
            return_1y = ((current_price / price_1y_ago) - 1) * 100
        else:
            return_1y = return_5y
            
        return round(return_5y, 2), round(return_1y, 2)
    except:
        return 0.0, 0.0

def get_robust_news(stock_name, limit=3):
    news_list = []
    try:
        url = f"https://news.google.com/rss/search?q={stock_name}+주식+전망+성장&hl=ko&gl=KR&ceid=KR:ko"
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

# 장기 성장/구조적 변화 키워드
POSITIVE_KEYWORDS = ['성장', '전망', '투자', '혁신', '미래', '확대', '수혜', '주도', '인프라', '독점', '흑자전환']
NEGATIVE_KEYWORDS = ['침체', '둔화', '위기', '감소', '축소', '악화', '경고', '리스크']

def evaluate_growth_stock(return_5y, return_1y, news_list):
    score = 50
    reasons = []
    is_triggered = False

    # 5년 장기 추세 평가 (구조적 성장 확인)
    if return_5y > 100: score += 20; reasons.append(f"5년 폭풍성장(+{return_5y}%)")
    elif return_5y > 30: score += 10; reasons.append(f"5년 우상향(+{return_5y}%)")
    elif return_5y < 0: score -= 15; reasons.append(f"장기 하락추세")

    # 1년 단기 모멘텀 (향후 1년 유망성 가늠)
    if return_1y > 20: score += 10; reasons.append(f"1년 추세 강세(+{return_1y}%)")
    elif return_1y < -10: score -= 5; reasons.append(f"최근 1년 부진")

    # 뉴스 평가 (성장 동력 확인)
    pos_cnt = sum(1 for news in news_list if any(p in news for p in POSITIVE_KEYWORDS))
    neg_cnt = sum(1 for news in news_list if any(n in news for n in NEGATIVE_KEYWORDS))

    if pos_cnt > 0: score += (pos_cnt * 10); reasons.append(f"미래성장 호재 {pos_cnt}건")
    if neg_cnt > 0: score -= (neg_cnt * 10); reasons.append(f"업황 리스크 {neg_cnt}건")

    # 메가 트렌드 트리거: 과거 5년 성장 + 최근 1년 모멘텀 유지 + 미래 호재 결합
    if return_5y > 30 and return_1y > 10 and pos_cnt > 0:
        score += 10
        is_triggered = True
        reasons.append("🚀 [향후 1년 유망 주도주]")

    return max(0, min(100, score)), "🔥 메가트렌드" if is_triggered else "관망", ", ".join(reasons)

# -------------------------------------------------------------------
# [3] 프론트엔드 (화면 구성)
# -------------------------------------------------------------------
st.markdown('<p class="main-title">AI 향후 1년 주도섹터 발굴기</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">과거 5년치 데이터를 분석하여 구조적으로 성장할 메가트렌드 기업을 찾습니다</p>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💼 내 포트폴리오 장기 전망 진단")
    user_input = st.text_input(
        "분석할 보유 종목을 쉼표(,)로 입력하세요.", 
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티"
    )

if st.button("🚀 5년 빅데이터 분석 가동", use_container_width=True, type="primary"):
    
    with st.spinner("과거 5년치 시장 데이터 수집 및 향후 1년 주도 섹터 분석 중... (약 20초 소요)"):
        candidates, df_krx = load_universe()
        eval_results = []
        progress_bar = st.progress(0)
        
        # 1. 시장 추천주 평가 (Top 20 우량주)
        for idx, row in enumerate(candidates.iterrows()):
            _, r = row
            code, name, sector = r['Code'], r['Name'], str(r['Sector'])
            if sector == "nan" or not sector: sector = "대형 우량주" # 섹터 정보가 없는 경우 예외처리
                
            return_5y, return_1y = get_5y_growth_data(code)
            news_list = get_robust_news(name)
            score, trigger, summary = evaluate_growth_stock(return_5y, return_1y, news_list)
            
            eval_results.append({
                '종목명': name, '섹터': sector, '종합점수': score, 
                '신호': trigger, '5년성장': return_5y, '1년추세': return_1y,
                '최신뉴스': news_list[0], '상세평가': summary
            })
            progress_bar.progress(int((idx + 1) / len(candidates) * 50))
            
        result_df = pd.DataFrame(eval_results).sort_values(by='종합점수', ascending=False)
        top_pick = result_df.iloc[0]
        top_pick_name, top_pick_score, top_sector = top_pick['종목명'], top_pick['종합점수'], top_pick['섹터']

        # 2. 내 포트폴리오 분석
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        my_results = []
        
        for idx, my_stock in enumerate(my_portfolio):
            stock_info = df_krx[df_krx['Name'] == my_stock]
            if stock_info.empty:
                my_results.append({"종목명": my_stock, "점수": 0, "상태": "데이터 없음", "액션": "종목명 확인 필요", "알림": "error"})
                continue
                
            r = stock_info.iloc[0]
            code, sector = r['Code'], str(r['Sector'])
            if sector == "nan" or not sector: sector = "개별주"
                
            return_5y, return_1y = get_5y_growth_data(code)
            news_list = get_robust_news(my_stock)
            my_score, trigger, summary = evaluate_growth_stock(return_5y, return_1y, news_list)
            
            score_diff = top_pick_score - my_score
            
            if score_diff >= 20: action, msg_type = f"🚨 향후 1년 유망 섹터({top_sector}) 편입 검토", "warning"
            elif score_diff > 0: action, msg_type = "🛡️ 추세 관망 (유지)", "info"
            else: action, msg_type = "👑 강력 보유 (메가트렌드 주도주)", "success"
                
            my_results.append({
                "종목명": my_stock, "섹터": sector, "점수": my_score, "신호": trigger, 
                "5년성장": return_5y, "1년추세": return_1y, "요약": summary, 
                "액션": action, "알림": msg_type, "뉴스": news_list[0]
            })
            progress_bar.progress(50 + int((idx + 1) / len(my_portfolio) * 50))
            
        progress_bar.empty()

    # -------------------------------------------------------------------
    # [4] 결과 출력 화면
    # -------------------------------------------------------------------
    tab1, tab2 = st.tabs(["🚀 향후 1년 유망 섹터 & 대장주", "💼 내 포트폴리오 장기 전망"])
    
    with tab1:
        st.markdown("### 🏆 AI가 포착한 구조적 성장 섹터")
        with st.container(border=True):
            st.markdown(f"#### 주도 섹터: **{top_sector}**")
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.metric("Top Pick 대장주", top_pick_name)
            col2.metric("과거 5년 누적성장률", f"{top_pick['5년성장']}%")
            col3.metric("성장 전망 점수", f"{top_pick_score} 점", top_pick['신호'])
            
            st.markdown("---")
            st.markdown(f"**📰 성장 모멘텀 뉴스:** {top_pick['최신뉴스']}")
            st.markdown(f"**💡 AI 진단 요약:** {top_pick['상세평가']}")
        
        with st.expander("📊 향후 1년 장기투자 유망 후보군 전체 보기"):
            # UI 가독성을 위해 표 데이터 정제
            display_df = result_df[['섹터', '종목명', '종합점수', '5년성장', '상세평가']].copy()
            st.dataframe(display_df.head(7), hide_index=True)

    with tab2:
        st.markdown("### 내 종목의 과거 5년과 미래 1년 진단")
        for res in my_results:
            if res["알림"] == "error":
                st.error(f"❌ {res['종목명']}: 데이터를 찾을 수 없습니다.")
            else:
                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([2, 1, 1])
                    with col_a:
                        st.markdown(f"#### {res['종목명']} ({res['섹터']})")
                        st.caption(res['뉴스'])
                    with col_b:
                        st.write(f"**5년 성장률:** {res['5년성장']}%")
                        st.write(f"**1년 모멘텀:** {res['1년추세']}%")
                    with col_c:
                        st.metric("전망 점수", f"{res['점수']} 점", res['신호'], delta_color="off")
                    
                    if res["알림"] == "warning": st.warning(f"**Action:** {res['액션']}")
                    elif res["알림"] == "info": st.info(f"**Action:** {res['액션']}")
                    else: st.success(f"**Action:** {res['액션']}")
