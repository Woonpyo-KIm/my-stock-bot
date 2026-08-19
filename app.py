import streamlit as st
import pandas as pd
import requests
import time
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET

# -------------------------------------------------------------------
# [1] 웹페이지 디자인 및 테마 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="AI 퀀트 (안정형)", page_icon="🛡️", layout="centered")

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(45deg, #1e3c72, #2a5298);
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
# [2] 백엔드 로직 (시가총액 중심 + 저변동성 필터링)
# -------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_stable_market_data():
    df_kospi = fdr.StockListing('KOSPI')
    df_kosdaq = fdr.StockListing('KOSDAQ')
    
    # 1. 시가총액 최상위 우량주 추출 (안정성 중심)
    kospi_cand = df_kospi[df_kospi['Marcap'] >= 5000000000000].sort_values(by='Marcap', ascending=False).head(15)
    kosdaq_cand = df_kosdaq[df_kosdaq['Marcap'] >= 1000000000000].sort_values(by='Marcap', ascending=False).head(5)
    all_cand = pd.concat([kospi_cand, kosdaq_cand])
    
    # 2. 극단적 변동성 필터링 (당일 등락률이 ±6%를 넘는 급등락 종목 제외)
    all_cand = all_cand[(all_cand['ChagesRatio'] >= -6.0) & (all_cand['ChagesRatio'] <= 6.0)]
    
    return all_cand, pd.concat([df_kospi, df_kosdaq]), df_kospi

def get_robust_news(stock_name, stock_code, limit=3):
    news_list = []
    try:
        code_str = str(stock_code).zfill(6)
        url = f"https://m.stock.naver.com/api/news/stock/{code_str}?pageSize={limit}&page=1"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=2)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                news_list = [item.get('tit', '제목 없음').strip() for item in data][:limit]
    except: pass

    if not news_list:
        try:
            url = f"https://news.google.com/rss/search?q={stock_name}+주식&hl=ko&gl=KR&ceid=KR:ko"
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

# 안정형/가치주 키워드
POSITIVE_KEYWORDS = ['배당', '자사주', '주주환원', '안정', '수주', '흑자', '실적', '가치', '방어주', '성장', '호재']
NEGATIVE_KEYWORDS = ['적자', '급락', '우려', '손실', '소송', '악재', '유상증자', '횡령', '조사', '경고', '하향', '변동성']

def evaluate_stable_stock(change_ratio, news_list):
    score = 50
    reasons = []
    is_triggered = False

    # 주가 평가: 급등보다는 '완만하고 안정적인 상승'에 최고점 부여
    if 0 < change_ratio <= 3: 
        score += 15; reasons.append(f"안정적 상승(+{change_ratio:.2f}%)")
    elif 3 < change_ratio <= 6: 
        score += 5; reasons.append(f"다소 강한 상승(+{change_ratio:.2f}%)")
    elif change_ratio > 6: 
        score -= 5; reasons.append(f"단기 과열 경고(+{change_ratio:.2f}%)")
    elif change_ratio < 0: 
        score -= 10; reasons.append(f"하락세({change_ratio:.2f}%)")

    # 뉴스 평가
    pos_cnt = sum(1 for news in news_list if any(p in news for p in POSITIVE_KEYWORDS))
    neg_cnt = sum(1 for news in news_list if any(n in news for n in NEGATIVE_KEYWORDS))

    if pos_cnt > 0: score += (pos_cnt * 10); reasons.append(f"호재 {pos_cnt}건")
    if neg_cnt > 0: score -= (neg_cnt * 10); reasons.append(f"리스크 {neg_cnt}건")

    # 가치주 트리거: 주가가 안정적이면서 주주환원/배당 관련 뉴스가 있을 때
    valuable_news = sum(1 for news in news_list if any(w in news for w in ['배당', '자사주', '주주환원', '가치']))
    if (0 <= change_ratio <= 3) and valuable_news > 0:
        score += 15
        is_triggered = True
        reasons.append("🛡️ [안전마진 확보]")

    return max(0, min(100, score)), "🛡️ 안정" if is_triggered else "대기", ", ".join(reasons)

# -------------------------------------------------------------------
# [3] 프론트엔드 (화면 구성)
# -------------------------------------------------------------------
st.markdown('<p class="main-title">AI 퀀트 어드바이저 (안정/우량주)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">변동성을 낮추고 내재가치가 우수한 대형주를 발굴합니다</p>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💼 분석할 포트폴리오 입력")
    user_input = st.text_input(
        "종목명을 쉼표(,)로 구분하여 입력해 주세요.", 
        value="두산로보틱스, 한화오션, 테스, 에스에이엠티"
    )

if st.button("🛡️ 퀀트 분석 시작", use_container_width=True, type="primary"):
    
    with st.spinner("시가총액 최상위 우량주 필터링 및 리스크 검증 중..."):
        all_cand, df_all, df_kospi = load_stable_market_data()
        eval_results = []
        progress_bar = st.progress(0)
        
        # 1. 시장 추천주 평가
        for idx, row in enumerate(all_cand.iterrows()):
            _, r = row
            code, name, change = r['Code'], r['Name'], round(r['ChagesRatio'], 2)
            news_list = get_robust_news(name, code)
            score, trigger, summary = evaluate_stable_stock(change, news_list)
            
            eval_results.append({
                '종목명': name, '종합점수': score, 
                '신호': trigger, '최신뉴스': news_list[0], '상세평가': summary
            })
            progress_bar.progress(int((idx + 1) / len(all_cand) * 50))
            time.sleep(0.05)
            
        result_df = pd.DataFrame(eval_results).sort_values(by='종합점수', ascending=False)
        top_pick = result_df.iloc[0]
        top_pick_name, top_pick_score = top_pick['종목명'], top_pick['종합점수']

        # 2. 내 종목 분석
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        my_results = []
        
        for idx, my_stock in enumerate(my_portfolio):
            stock_info = df_all[df_all['Name'] == my_stock]
            if stock_info.empty:
                my_results.append({"종목명": my_stock, "점수": 0, "상태": "데이터 없음", "액션": "종목명 확인 필요", "알림": "error"})
                continue
                
            r = stock_info.iloc[0]
            code, change = r['Code'], round(r['ChagesRatio'], 2)
            news_list = get_robust_news(my_stock, code)
            my_score, trigger, summary = evaluate_stable_stock(change, news_list)
            
            score_diff = top_pick_score - my_score
            
            if score_diff >= 20: action, msg_type = f"🚨 {top_pick_name} 교체(안정화) 검토", "warning"
            elif score_diff > 0: action, msg_type = "🛡️ 보유 유지 권장", "info"
            else: action, msg_type = "👑 강력 보유 (안정성 우수)", "success"
                
            my_results.append({
                "종목명": my_stock, "점수": my_score, "신호": trigger, 
                "요약": summary, "액션": action, "알림": msg_type, "뉴스": news_list[0]
            })
            progress_bar.progress(50 + int((idx + 1) / len(my_portfolio) * 50))
            
        progress_bar.empty()

    # -------------------------------------------------------------------
    # [4] 결과 출력 (탭을 활용한 레이아웃)
    # -------------------------------------------------------------------
    tab1, tab2 = st.tabs(["🛡️ 최우수 가치주", "💼 내 포트폴리오 진단"])
    
    with tab1:
        st.markdown("### 오늘의 저변동성 우량주 픽")
        with st.container(border=True):
            col1, col2 = st.columns([1, 1])
            col1.metric("종목명", top_pick_name)
            col2.metric("안정성 종합점수", f"{top_pick_score} 점", f"상태: {top_pick['신호']}")
            
            st.markdown("---")
            st.markdown(f"**📰 핵심 뉴스:** {top_pick['최신뉴스']}")
            st.markdown(f"**💡 평가 요약:** {top_pick['상세평가']}")
        
        with st.expander("📊 우량주 후보 Top 5 전체 보기"):
            st.dataframe(result_df[['종목명', '종합점수', '신호', '상세평가']].head(5), hide_index=True)

    with tab2:
        st.markdown("### 내 포트폴리오 안정성 진단")
        for res in my_results:
            if res["알림"] == "error":
                st.error(f"❌ {res['종목명']}: 데이터를 찾을 수 없습니다.")
            else:
                with st.container(border=True):
                    col_a, col_b = st.columns([2, 1])
                    with col_a:
                        st.markdown(f"#### {res['종목명']}")
                        st.caption(res['뉴스'])
                    with col_b:
                        st.metric("안정 점수", f"{res['점수']} 점", res['신호'], delta_color="off")
                    
                    if res["알림"] == "warning": st.warning(f"**Action:** {res['액션']}")
                    elif res["알림"] == "info": st.info(f"**Action:** {res['액션']}")
                    else: st.success(f"**Action:** {res['액션']}")
