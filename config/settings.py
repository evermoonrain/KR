# -*- coding: utf-8 -*-
"""
KR STOCK SCANNER - 설정 모듈
지표 가중치, 필터 기준값, 등급 컷오프를 한곳에서 관리한다.
"""

# ============================================================
# 1. 지표별 가중치 (총합 100)
# ============================================================
WEIGHTS = {
    "volume":   30,   # 거래량
    "obv":      25,   # OBV (On Balance Volume)
    "vwap":     15,   # VWAP
    "kdj":      10,   # KDJ
    "macd":      8,   # MACD
    "mfi":       5,   # MFI
    "rsi":       3,   # RSI
    "adx":       2,   # ADX
    "bb":        2,   # 볼린저밴드
}
assert sum(WEIGHTS.values()) == 100, "가중치 합은 100이어야 합니다."

# ============================================================
# 2. 필터 우선순위 (순차 적용 순서) + 중요도(★) 메타데이터
#    파이프라인: 거래량 → OBV → VWAP → MFI → MACD → KDJ → RSI → ADX → 볼린저
# ============================================================
FILTER_PIPELINE = [
    {"key": "volume", "name": "거래량 증가",     "purpose": "세력 진입 탐지",    "stars": 5},
    {"key": "obv",    "name": "OBV 상승",       "purpose": "자금 유입 확인",    "stars": 5},
    {"key": "vwap",   "name": "VWAP 상회",      "purpose": "기관 수익권 확인",  "stars": 5},
    {"key": "mfi",    "name": "MFI 상승",       "purpose": "거래대금 유입 확인", "stars": 4},
    {"key": "macd",   "name": "MACD 골든크로스", "purpose": "추세 전환 확인",    "stars": 4},
    {"key": "kdj",    "name": "KDJ 골든크로스",  "purpose": "초기 모멘텀 확인",  "stars": 4},
    {"key": "rsi",    "name": "RSI 상승",       "purpose": "과매도 탈출 확인",  "stars": 3},
    {"key": "adx",    "name": "ADX 상승",       "purpose": "추세 강도 확인",    "stars": 3},
    {"key": "bb",     "name": "볼린저밴드 확장", "purpose": "폭발력 확인",      "stars": 2},
]

# ============================================================
# 3. 지표 파라미터
# ============================================================
PARAMS = {
    "volume_lookback": 20,        # 거래량 평균 비교 기간
    "volume_surge_ratio": 1.5,    # 평균 대비 거래량 급증 기준배수
    "obv_lookback": 20,           # OBV 추세 판단 기간
    "vwap_lookback": 20,          # VWAP 계산용 lookback(일봉 누적 근사)
    "mfi_period": 14,
    "mfi_oversold": 20,
    "mfi_overbought": 80,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "kdj_period": 9,
    "kdj_k_smooth": 3,
    "kdj_d_smooth": 3,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "adx_period": 14,
    "adx_trend_threshold": 25,
    "bb_period": 20,
    "bb_std": 2,
    "price_history_days": 180,    # yfinance 다운로드 기간
}

# ============================================================
# 4. 등급 컷오프 (100점 만점 기준)
# ============================================================
GRADE_CUTOFFS = [
    ("S", 85),
    ("A", 70),
    ("B", 55),
    ("C", 40),
]
MIN_PASS_SCORE = 40  # 이 미만은 탈락 처리 (리포트에서 제외)


def get_grade(score: float) -> str:
    for grade, cutoff in GRADE_CUTOFFS:
        if score >= cutoff:
            return grade
    return "F"  # 탈락


# ============================================================
# 5. 출력/발송 설정
# ============================================================
OUTPUT_DIR = "output"
EXCEL_FILENAME_PREFIX = "KR_STOCK_SCAN"
TELEGRAM_TOP_N = 15        # 텔레그램 메시지에 표시할 상위 종목 수
MAX_WORKERS = 8            # 병렬 다운로드 스레드 수
