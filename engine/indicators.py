# -*- coding: utf-8 -*-
"""
기술적 지표 계산 모듈
입력: OHLCV pandas DataFrame (columns: Open, High, Low, Close, Volume)
모든 함수는 원본 df를 변경하지 않고 새 Series/DataFrame을 반환한다.
"""

import numpy as np
import pandas as pd


# ------------------------------------------------------------
# 거래량
# ------------------------------------------------------------
def volume_surge_ratio(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """최근 거래량 / 직전 N일 평균거래량"""
    avg_vol = df["Volume"].rolling(lookback).mean().shift(1)
    return df["Volume"] / avg_vol


# ------------------------------------------------------------
# OBV (On Balance Volume)
# ------------------------------------------------------------
def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["Close"].diff()).fillna(0)
    obv_series = (direction * df["Volume"]).cumsum()
    return obv_series


def obv_slope(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """OBV의 단기 추세 기울기를 선형회귀 계수로 근사"""
    obv_s = obv(df)

    def _slope(window):
        if window.isna().any() or len(window) < 2:
            return np.nan
        x = np.arange(len(window))
        y = window.values
        slope = np.polyfit(x, y, 1)[0]
        return slope

    return obv_s.rolling(lookback).apply(_slope, raw=False)


# ------------------------------------------------------------
# VWAP (일중 VWAP 대신, 스윙용으로 N일 누적 VWAP 근사 사용)
# ------------------------------------------------------------
def vwap(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    pv = typical_price * df["Volume"]
    cum_pv = pv.rolling(lookback).sum()
    cum_vol = df["Volume"].rolling(lookback).sum()
    return cum_pv / cum_vol


# ------------------------------------------------------------
# MFI (Money Flow Index)
# ------------------------------------------------------------
def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    money_flow = typical_price * df["Volume"]

    tp_diff = typical_price.diff()
    pos_flow = money_flow.where(tp_diff > 0, 0.0)
    neg_flow = money_flow.where(tp_diff < 0, 0.0)

    pos_sum = pos_flow.rolling(period).sum()
    neg_sum = neg_flow.rolling(period).sum()

    money_ratio = pos_sum / neg_sum.replace(0, np.nan)
    mfi_series = 100 - (100 / (1 + money_ratio))
    return mfi_series.fillna(50)


# ------------------------------------------------------------
# MACD
# ------------------------------------------------------------
def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ------------------------------------------------------------
# KDJ
# ------------------------------------------------------------
def kdj(df: pd.DataFrame, period: int = 9, k_smooth: int = 3, d_smooth: int = 3):
    low_min = df["Low"].rolling(period).min()
    high_max = df["High"].rolling(period).max()
    rsv = (df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=k_smooth - 1, adjust=False).mean()
    d = k.ewm(com=d_smooth - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


# ------------------------------------------------------------
# RSI
# ------------------------------------------------------------
def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series.fillna(50)


# ------------------------------------------------------------
# ADX
# ------------------------------------------------------------
def adx(df: pd.DataFrame, period: int = 14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx_series = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_series.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


# ------------------------------------------------------------
# 볼린저밴드
# ------------------------------------------------------------
def bollinger_bands(df: pd.DataFrame, period: int = 20, std_mult: float = 2):
    mid = df["Close"].rolling(period).mean()
    std = df["Close"].rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    bandwidth = (upper - lower) / mid.replace(0, np.nan) * 100
    return upper, mid, lower, bandwidth


def compute_all_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """모든 지표를 계산하여 df에 컬럼으로 추가한 새 DataFrame을 반환"""
    out = df.copy()

    out["vol_surge"] = volume_surge_ratio(out, params["volume_lookback"])

    out["obv"] = obv(out)
    out["obv_slope"] = obv_slope(out, params["obv_lookback"])

    out["vwap"] = vwap(out, params["vwap_lookback"])

    out["mfi"] = mfi(out, params["mfi_period"])

    macd_line, signal_line, hist = macd(
        out, params["macd_fast"], params["macd_slow"], params["macd_signal"]
    )
    out["macd"] = macd_line
    out["macd_signal"] = signal_line
    out["macd_hist"] = hist

    k, d, j = kdj(out, params["kdj_period"], params["kdj_k_smooth"], params["kdj_d_smooth"])
    out["kdj_k"] = k
    out["kdj_d"] = d
    out["kdj_j"] = j

    out["rsi"] = rsi(out, params["rsi_period"])

    adx_s, plus_di, minus_di = adx(out, params["adx_period"])
    out["adx"] = adx_s
    out["plus_di"] = plus_di
    out["minus_di"] = minus_di

    bb_up, bb_mid, bb_low, bb_width = bollinger_bands(out, params["bb_period"], params["bb_std"])
    out["bb_upper"] = bb_up
    out["bb_mid"] = bb_mid
    out["bb_lower"] = bb_low
    out["bb_width"] = bb_width

    return out
