# -*- coding: utf-8 -*-
"""
스코어링 엔진
- 9단계 필터를 순서대로 적용 (거래량→OBV→VWAP→MFI→MACD→KDJ→RSI→ADX→볼린저)
- 각 단계 통과 여부에 따라 가중치 점수를 부여
- 최종 합산 점수로 등급(S/A/B/C/탈락) 산정

각 필터 함수는 (passed: bool, raw_score_0to1: float, detail: str) 를 반환한다.
raw_score_0to1은 "얼마나 강하게 조건을 만족하는가"의 연속값으로,
최종 점수 = WEIGHT[key] * raw_score_0to1 로 계산한다.
(완전 이진(통과/실패)이 아니라 강도 기반으로 점수를 줘야
 '근접 종목'과 '확실한 종목'을 구분할 수 있다.)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from config.settings import WEIGHTS, PARAMS, FILTER_PIPELINE, get_grade, MIN_PASS_SCORE
from engine.indicators import compute_all_indicators

logger = logging.getLogger("scoring")


def _clip01(x: float) -> float:
    if x is None or np.isnan(x):
        return 0.0
    return float(max(0.0, min(1.0, x)))


@dataclass
class StepResult:
    key: str
    name: str
    passed: bool
    raw_score: float   # 0~1
    weighted_score: float
    detail: str


@dataclass
class ScanResult:
    code: str
    name: str
    market: str
    ticker: str
    close: float
    total_score: float
    grade: str
    steps: List[StepResult] = field(default_factory=list)

    def step_dict(self) -> Dict[str, StepResult]:
        return {s.key: s for s in self.steps}


# ------------------------------------------------------------
# 단계별 필터 함수
# 각 함수는 row(마지막 시점) + 직전 비교를 위해 tail DataFrame을 받는다.
# ------------------------------------------------------------

def step_volume(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    ratio = df["vol_surge"].iloc[-1]
    if np.isnan(ratio):
        return False, 0.0, "데이터 부족"
    threshold = params["volume_surge_ratio"]
    passed = ratio >= threshold
    # 1.0배=0점, threshold배=0.6, 3배 이상=1.0 으로 스케일링
    raw = _clip01((ratio - 1.0) / (3.0 - 1.0))
    detail = f"거래량 {ratio:.2f}배 (평균 {params['volume_lookback']}일 대비)"
    return passed, raw, detail


def step_obv(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    slope = df["obv_slope"].iloc[-1]
    if np.isnan(slope):
        return False, 0.0, "데이터 부족"
    passed = slope > 0
    # OBV 기울기를 최근 거래량 스케일로 정규화
    recent_vol_mean = df["Volume"].tail(params["obv_lookback"]).mean()
    norm = slope / recent_vol_mean if recent_vol_mean else 0
    raw = _clip01(norm * 5 + 0.5) if passed else _clip01(0.5 + norm * 5)
    raw = _clip01(raw)
    detail = f"OBV 기울기 {'상승' if passed else '하락'} ({slope:,.0f})"
    return passed, raw, detail


def step_vwap(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    close = df["Close"].iloc[-1]
    vwap_val = df["vwap"].iloc[-1]
    if np.isnan(vwap_val) or vwap_val == 0:
        return False, 0.0, "데이터 부족"
    passed = close > vwap_val
    pct = (close - vwap_val) / vwap_val
    raw = _clip01(0.5 + pct * 10)  # VWAP 대비 +5% 이상이면 만점에 근접
    detail = f"종가 {close:,.0f} vs VWAP {vwap_val:,.0f} ({pct*100:+.1f}%)"
    return passed, raw, detail


def step_mfi(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    mfi_now = df["mfi"].iloc[-1]
    mfi_prev = df["mfi"].iloc[-2] if len(df) > 1 else mfi_now
    if np.isnan(mfi_now):
        return False, 0.0, "데이터 부족"
    passed = mfi_now > mfi_prev and mfi_now < params["mfi_overbought"]
    # 50 기준 상승 추세 + 과매수 직전이 가장 이상적
    raw = _clip01((mfi_now - 30) / (params["mfi_overbought"] - 30))
    detail = f"MFI {mfi_now:.1f} (전일 {mfi_prev:.1f})"
    return passed, raw, detail


def step_macd(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    macd_now = df["macd"].iloc[-1]
    signal_now = df["macd_signal"].iloc[-1]
    macd_prev = df["macd"].iloc[-2] if len(df) > 1 else macd_now
    signal_prev = df["macd_signal"].iloc[-2] if len(df) > 1 else signal_now

    if np.isnan(macd_now) or np.isnan(signal_now):
        return False, 0.0, "데이터 부족"

    golden_cross = (macd_prev <= signal_prev) and (macd_now > signal_now)
    above = macd_now > signal_now
    passed = golden_cross or above

    hist = macd_now - signal_now
    ref = df["Close"].iloc[-1] * 0.02 if df["Close"].iloc[-1] else 1
    raw = _clip01(0.5 + (hist / ref) * 0.5)
    if golden_cross:
        raw = max(raw, 0.8)
    detail = "골든크로스 발생" if golden_cross else ("MACD>Signal 유지" if above else "MACD<Signal")
    return passed, raw, detail


def step_kdj(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    k_now, d_now = df["kdj_k"].iloc[-1], df["kdj_d"].iloc[-1]
    k_prev, d_prev = (df["kdj_k"].iloc[-2], df["kdj_d"].iloc[-2]) if len(df) > 1 else (k_now, d_now)

    if np.isnan(k_now) or np.isnan(d_now):
        return False, 0.0, "데이터 부족"

    golden_cross = (k_prev <= d_prev) and (k_now > d_now)
    above = k_now > d_now
    passed = golden_cross or above

    raw = _clip01((k_now - d_now) / 20 + 0.5)
    if golden_cross:
        raw = max(raw, 0.75)
    detail = "골든크로스 발생" if golden_cross else ("K>D 유지" if above else "K<D")
    return passed, raw, detail


def step_rsi(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    rsi_now = df["rsi"].iloc[-1]
    rsi_prev = df["rsi"].iloc[-2] if len(df) > 1 else rsi_now
    if np.isnan(rsi_now):
        return False, 0.0, "데이터 부족"

    rising = rsi_now > rsi_prev
    escaping_oversold = rsi_prev <= params["rsi_oversold"] < rsi_now
    passed = rising and rsi_now < 75  # 과매수 전 상승만 인정

    raw = _clip01((rsi_now - 30) / 40)
    if escaping_oversold:
        raw = max(raw, 0.7)
    detail = f"RSI {rsi_now:.1f} ({'상승' if rising else '하락'})"
    return passed, raw, detail


def step_adx(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    adx_now = df["adx"].iloc[-1]
    adx_prev = df["adx"].iloc[-2] if len(df) > 1 else adx_now
    if np.isnan(adx_now):
        return False, 0.0, "데이터 부족"

    rising = adx_now > adx_prev
    strong = adx_now >= params["adx_trend_threshold"]
    passed = rising or strong

    raw = _clip01(adx_now / 50)
    if rising and strong:
        raw = max(raw, 0.75)
    detail = f"ADX {adx_now:.1f} ({'상승' if rising else '하락'}, 추세강도 {'강' if strong else '약'})"
    return passed, raw, detail


def step_bb(df: pd.DataFrame, params: dict) -> Tuple[bool, float, str]:
    width_now = df["bb_width"].iloc[-1]
    width_prev = df["bb_width"].iloc[-2] if len(df) > 1 else width_now
    if np.isnan(width_now):
        return False, 0.0, "데이터 부족"

    expanding = width_now > width_prev
    passed = expanding

    width_hist = df["bb_width"].tail(60).dropna()
    pct_rank = (width_hist < width_now).mean() if len(width_hist) > 0 else 0.5
    raw = _clip01(pct_rank)
    detail = f"밴드폭 {width_now:.1f}% ({'확장' if expanding else '수축'})"
    return passed, raw, detail


STEP_FUNCS = {
    "volume": step_volume,
    "obv": step_obv,
    "vwap": step_vwap,
    "mfi": step_mfi,
    "macd": step_macd,
    "kdj": step_kdj,
    "rsi": step_rsi,
    "adx": step_adx,
    "bb": step_bb,
}

# 파이프라인 순서로 정렬된 key 리스트 (거래량→OBV→VWAP→MFI→MACD→KDJ→RSI→ADX→볼린저)
PIPELINE_ORDER = [f["key"] for f in FILTER_PIPELINE]


def evaluate_stock(code: str, name: str, market: str, ticker: str, df: pd.DataFrame) -> ScanResult:
    """단일 종목에 대해 지표 계산 → 9단계 필터 평가 → 점수/등급 산정"""
    df_ind = compute_all_indicators(df, PARAMS)

    steps: List[StepResult] = []
    total_score = 0.0

    name_map = {f["key"]: f["name"] for f in FILTER_PIPELINE}

    for key in PIPELINE_ORDER:
        func = STEP_FUNCS[key]
        try:
            passed, raw, detail = func(df_ind, PARAMS)
        except Exception as e:
            passed, raw, detail = False, 0.0, f"오류: {e}"

        weight = WEIGHTS[key]
        weighted = weight * raw
        total_score += weighted

        steps.append(StepResult(
            key=key,
            name=name_map[key],
            passed=passed,
            raw_score=raw,
            weighted_score=weighted,
            detail=detail,
        ))

    total_score = round(total_score, 2)
    grade = get_grade(total_score)

    close = float(df_ind["Close"].iloc[-1])

    return ScanResult(
        code=code,
        name=name,
        market=market,
        ticker=ticker,
        close=close,
        total_score=total_score,
        grade=grade,
        steps=steps,
    )


def filter_and_rank(results: List[ScanResult]) -> List[ScanResult]:
    """MIN_PASS_SCORE 미만 탈락 처리 후 점수 내림차순 정렬"""
    passed = [r for r in results if r.total_score >= MIN_PASS_SCORE]
    passed.sort(key=lambda r: r.total_score, reverse=True)
    return passed
