import streamlit as st
import pandas as pd
import requests
import time
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET

# -------------------------------------------------------------------
# [기본 웹페이지 설정] - 스마트폰 화면에 꽉 차게 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="통합 로보어드바이저", page_icon="📈", layout="centered")

# -------------------------------------------------------------------
# [핵심 함수 1] 시장 데이터 로드 (캐시 적용으로 매번 로딩 방지, 속도 향상)
# -------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1시간 동안 데이터 재사용
def load_market_data():
    df_kospi = fdr.StockListing('KOSPI')
    df_kosdaq = fdr.StockListing('KOSDAQ')
    
    # 코스피 1조 이상 / 코스닥 5천억 이상 중 거래량 상위 종목 추출
    kospi_cand = df_kospi[df_kospi['Marcap'] >= 1000000000000].sort_values(by='Volume', ascending=False).head(8)
    kosdaq_cand = df_kosdaq[df_kosdaq['Marcap'] >= 500000000000].sort_values(by='Volume', ascending=False).head(8)
    all_cand = pd.concat([kospi_cand, kosdaq_cand])
    
    df_all = pd.concat([df_kospi, df_kosdaq])
    return all_cand, df_all, df_kospi

# -------------------------------------------------------------------
# [핵심 함수 2] 이중 뉴스 수집 엔진 (Naver API -> Google RSS)
# -------------------------------------------------------------------
def get_robust_news(stock_name, stock_code, limit=3):
    news_list = []
    
    # 1차 시도: 네이버 모바일 API
    try:
        code_str = str(stock_code).zfill(6)
        url = f"https://m.stock.naver.com/api/news/stock/{code_str}?pageSize={limit}&page=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://m.stock.naver.com/"
        }
        res = requests.get(url, headers=headers, timeout=2)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                news_list = [item.get('tit', '제목 없음').strip() for item in data][:limit]
    except:
        pass

    # 2차 시도: 구글 뉴스 RSS 우회
    if not news_list:
        try:
            url = f"https://news.google.com/rss/search?q={stock_name}+주식&hl=ko&gl=KR&ceid=KR:ko"
            res = requests.get(url, timeout=2)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                for item in root.findall('.//item/title'):
                    title = item.text.replace(' - Yahoo Finance', '').replace(' - Naver', '').strip()
                    news_list.append(title)
                    if len(news_list) >= limit: break
        except:
            pass

    if not news_list:
        news_list = ["최신 뉴스 수집 불가"]
        
    while len(news_list) < limit:
        news_list.append("-")
        
    return news_list[:limit]

# -------------------------------------------------------------------
# [핵심 함수 3] 스프링보드 & 트리거 평가 엔진
# -------------------------------------------------------------------
POSITIVE_KEYWORDS = ['수주', '흑자', '급등', '상승', '최고', '유망', '계약', '실적', 'MOU', '서프라이즈', '돌파', '인수', '성장', '호재', '반도체', '장비', '로봇', '조선']
NEGATIVE_KEYWORDS = ['적자', '하락', '급락', '우려', '손실', '소송', '악재', '유상증자', '횡령', '조사', '경고', '하향']

def evaluate_and_trigger(change_ratio, volume, news_list):
    score = 50
    reasons = []
    is_triggered = False

    if change_ratio > 3: score += 15; reasons.append(f"상승세(+{change_ratio:.2f}%)")
    elif change_ratio > 0: score += 5; reasons.append(f"소폭 상승(+{change_ratio:.2f}%)")
    elif change_ratio < -3: score -= 15; reasons.append(f"하락({change_ratio:.2f}%)")

    pos_cnt = sum(1 for news in news_list if any(p in news for p in POSITIVE_KEYWORDS))
    neg_cnt = sum(1 for news in news_list if any(n in news for n in NEGATIVE_KEYWORDS))

    if pos_cnt > 0: score += (pos_cnt * 10); reasons.append(f"호재 {pos_cnt}건")
    if neg_cnt > 0: score -= (neg_cnt * 10); reasons.append(f"주의 {neg_cnt}건")

    if change_ratio >= 2.0 and volume >= 500000:
        score += 15
        reasons.append("🚀 [스프링보드] 발동")
        
    if change_ratio >= 2.0 and volume >= 500000 and pos_cnt >= 1:
        is_triggered = True
        reasons.append("🔥 [강력 매수 트리거]")

    return max(0, min(100, score)), "⚡ 발동" if is_triggered else "대기", ", ".join(reasons)

# -------------------------------------------------------------------
# [UI 구성] 프론트엔드 (스마트폰에 보이는 화면)
# -------------------------------------------------------------------
st.title("🚀 주식 로보어드바이저")
st.markdown("현재 시장의 1등 주도주를 발굴하고, 내 보유 종목과 **교체(SWAP)** 여부를 실시간으로 판정합니다.")

st.divider()

# 사용자 입력창 (모바일에서 터치하기 쉽게)
st.subheader("💼 내 포트폴리오 입력")
user_input = st.text_area(
    "보유 종목을 쉼표(,)로 구분하여 입력하세요.", 
    value="두산로보틱스, 한화오션, 테스, 에스에이엠티",
    height=80
)

# 실행 버튼
if st.button("📊 실시간 분석 시작", use_container_width=True, type="primary"):
    
    with st.spinner("시장 데이터를 분석 중입니다. 잠시만 기다려주세요..."):
        
        # 1. 데이터 로드
        all_cand, df_all, df_kospi = load_market_data()
        
        # 2. 시장 추천주 평가
        eval_results = []
        # 분석 진행 상태바 (모바일 친화적 UI)
        progress_bar = st.progress(0)
        
        for idx, row in enumerate(all_cand.iterrows()):
            _, r = row
            code, name, change, volume = r['Code'], r['Name'], round(r['ChagesRatio'], 2), r['Volume']
            market = "KOSPI" if code in df_kospi['Code'].values else "KOSDAQ"
            
            news_list = get_robust_news(name, code)
            score, trigger, summary = evaluate_and_trigger(change, volume, news_list)
            
            eval_results.append({
                '시장': market, '종목명': name, '종합점수': score, 
                '신호': trigger, '최신뉴스': news_list[0], '상세평가': summary
            })
            progress_bar.progress(int((idx + 1) / len(all_cand) * 50))
            time.sleep(0.05)
            
        result_df = pd.DataFrame(eval_results).sort_values(by='종합점수', ascending=False)
        
        top_pick = result_df.iloc[0]
        top_pick_name, top_pick_score = top_pick['종목명'], top_pick['종합점수']

        # 3. 내 종목 분석
        my_portfolio = [stock.strip() for stock in user_input.split(',')]
        
        my_results = []
        for idx, my_stock in enumerate(my_portfolio):
            stock_info = df_all[df_all['Name'] == my_stock]
            if stock_info.empty:
                my_results.append({"종목명": my_stock, "점수": 0, "상태": "데이터 없음", "액션": "종목명 확인 필요", "알림": "error"})
                continue
                
            r = stock_info.iloc[0]
            code, change, volume = r['Code'], round(r['ChagesRatio'], 2), r['Volume']
            news_list = get_robust_news(my_stock, code)
            my_score, trigger, summary = evaluate_and_trigger(change, volume, news_list)
            
            score_diff = top_pick_score - my_score
            
            if score_diff >= 20:
                action = f"🚨 {top_pick_name}(으)로 종목 교체(SWAP) 검토"
                msg_type = "warning"
            elif score_diff > 0:
                action = "🛡️ 보유 유지 (매매 수수료 고려)"
                msg_type = "info"
            else:
                action = "👑 강력 보유 (시장 1등주보다 우수)"
                msg_type = "success"
                
            my_results.append({
                "종목명": my_stock, "점수": my_score, "신호": trigger, 
                "요약": summary, "액션": action, "알림": msg_type, "뉴스": news_list[0]
            })
            progress_bar.progress(50 + int((idx + 1) / len(my_portfolio) * 50))

        progress_bar.empty() # 로딩바 숨기기

    # ==========================================
    # [결과 화면 출력] 모바일 친화적인 레이아웃 적용
    # ==========================================
    
    st.divider()
    st.subheader(f"🏆 시장 전체 1등 픽: {top_pick_name}")
    st.metric(label="통합 평가 점수", value=f"{top_pick_score} 점", delta=top_pick['신호'], delta_color="normal")
    st.caption(f"**최신뉴스:** {top_pick['최신뉴스']}")
    st.caption(f"**평가요약:** {top_pick['상세평가']}")
    
    # 추천주 Top 5 표
    with st.expander("시장 추천주 Top 5 전체 보기"):
        st.dataframe(result_df[['종목명', '종합점수', '신호', '최신뉴스']], use_container_width=True)
        
    st.divider()
    st.subheader("💼 내 종목 리밸런싱 판정")
    
    # 모바일 카드 형식으로 내 종목 결과 출력
    for res in my_results:
        if res["알림"] == "error":
            st.error(f"❌ {res['종목명']}: 데이터를 찾을 수 없습니다.")
        else:
            with st.container():
                cols = st.columns([2, 1])
                cols[0].markdown(f"#### {res['종목명']} ({res['점수']}점)")
                cols[1].markdown(f"**신호:** {res['신호']}")
                
                st.write(f"**최신뉴스:** {res['뉴스']}")
                st.write(f"**평가요약:** {res['요약']}")
                
                if res["알림"] == "warning":
                    st.warning(f"👉 {res['액션']}")
                elif res["알림"] == "info":
                    st.info(f"👉 {res['액션']}")
                else:
                    st.success(f"👉 {res['액션']}")
            st.write("---") # 항목별 구분선