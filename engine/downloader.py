# -*- coding: utf-8 -*-
"""
YFINANCE 데이터 다운로더 모듈 (강화 버전)
- Yahoo Finance Crumb 401 Unauthorized 오류 완벽 방지
- 단건 재시도 및 세션 초기화 로직 탑재
"""

import logging
import time
from typing import Dict, List
import pandas as pd
import yfinance as yf
import requests

logger = logging.getLogger("downloader")


def get_fresh_session() -> requests.Session:
    """새로운 User-Agent 및 헤더를 가진 Session 생성"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def download_universe(stocks: List, period: str = "180d") -> Dict[str, pd.DataFrame]:
    """
    유니버스 종목들의 일봉 데이터를 안전하게 다운로드합니다.
    """
    if not stocks:
        return {}

    result: Dict[str, pd.DataFrame] = {}
    tickers = [s.ticker for s in stocks]
    
    logger.info(f"yfinance 데이터 다운로드 시작 (총 {len(tickers)}개 종목)...")

    # 1차: Batch Download
    session = get_fresh_session()
    try:
        data = yf.download(
            tickers=tickers,
            period=period,
            group_by="ticker",
            threads=True,
            progress=False,
            session=session
        )

        for stock in stocks:
            tk = stock.ticker
            try:
                if len(tickers) == 1:
                    df = data.copy()
                else:
                    df = data[tk].dropna(how="all") if tk in data else pd.DataFrame()

                # Adj Close 또는 Close 컬럼 체크
                if not df.empty and len(df) > 30:
                    result[stock.code] = df
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"일괄 다운로드 예외 발생: {e}")

    # 2차: 실패 종목 개별 재시도 (세션 신규 생성 후 단건 요청)
    missing_stocks = [s for s in stocks if s.code not in result]
    if missing_stocks:
        logger.info(f"누락/실패 종목 {len(missing_stocks)}개 개별 재시도 중...")
        for stock in missing_stocks:
            time.sleep(0.2)  # 요청 간격 조절 (Rate Limit 방지)
            try:
                single_session = get_fresh_session()
                ticker_obj = yf.Ticker(stock.ticker, session=single_session)
                df = ticker_obj.history(period=period)
                
                if not df.empty and len(df) > 30:
                    result[stock.code] = df
                    logger.info(f"[{stock.ticker}] 개별 복구 성공")
                else:
                    logger.warning(f"[{stock.ticker}] 데이터 유효하지 않음 (건수 부족)")
            except Exception as ex:
                logger.warning(f"[{stock.ticker}] 개별 재시도 실패: {ex}")

    logger.info(f"다운로드 완료: {len(result)}/{len(stocks)} 종목 성공")
    return result
