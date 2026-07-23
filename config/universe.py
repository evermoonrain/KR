# -*- coding: utf-8 -*-
"""
종목 유니버스 관리 모듈
- 코스피200, 코스닥100 구성종목 관리
- 우선순위:
  1) 로컬 CSV 캐시 (refresh=False 시)
  2) 네이버 금융 API (가장 안정적, 클라우드 IP 차단 없음)
  3) pykrx / KRX Direct HTTP
  4) FALLBACK_TICKERS (최소 안전망)
"""

import os
import csv
import logging
from typing import List
from dataclasses import dataclass
import requests

logger = logging.getLogger("universe")

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(THIS_DIR, "universe_cache.csv")

SUFFIX_KOSPI = ".KS"
SUFFIX_KOSDAQ = ".KQ"


@dataclass
class Stock:
    code: str
    name: str
    market: str  # 'KOSPI200' or 'KOSDAQ100'
    sector: str = ""

    @property
    def ticker(self) -> str:
        market_str = str(self.market).upper()
        suffix = SUFFIX_KOSDAQ if "KOSDAQ" in market_str else SUFFIX_KOSPI
        return f"{self.code}{suffix}"


FALLBACK_TICKERS: List[Stock] = [
    Stock("005930", "삼성전자", "KOSPI200", "전기전자"),
    Stock("000660", "SK하이닉스", "KOSPI200", "전기전자"),
    Stock("373220", "LG에너지솔루션", "KOSPI200", "전기전자"),
    Stock("207940", "삼성바이오로직스", "KOSPI200", "의약품"),
    Stock("005380", "현대차", "KOSPI200", "운수장비"),
    Stock("000270", "기아", "KOSPI200", "운수장비"),
    Stock("068270", "셀트리온", "KOSPI200", "의약품"),
    Stock("005490", "POSCO홀딩스", "KOSPI200", "철강금속"),
    Stock("105560", "KB금융", "KOSPI200", "금융업"),
    Stock("055550", "신한지주", "KOSPI200", "금융업"),
    Stock("035420", "NAVER", "KOSPI200", "서비스업"),
    Stock("035720", "카카오", "KOSPI200", "서비스업"),
    Stock("012330", "현대모비스", "KOSPI200", "운수장비"),
    Stock("051910", "LG화학", "KOSPI200", "화학"),
    Stock("006400", "삼성SDI", "KOSPI200", "전기전자"),
    Stock("028260", "삼성물산", "KOSPI200", "유통업"),
    Stock("066570", "LG전자", "KOSPI200", "전기전자"),
    Stock("003670", "포스코퓨처엠", "KOSPI200", "비금속광물"),
    Stock("096770", "SK이노베이션", "KOSPI200", "화학"),
    Stock("034730", "SK", "KOSPI200", "금융업"),
    Stock("247540", "에코프로비엠", "KOSDAQ100", "일반전기전자"),
    Stock("086520", "에코프로", "KOSDAQ100", "금융"),
    Stock("196170", "알테오젠", "KOSDAQ100", "기타서비스"),
    Stock("028300", "HLB", "KOSDAQ100", "운송장비부품"),
    Stock("403870", "HPSP", "KOSDAQ100", "반도체"),
    Stock("293490", "카카오게임즈", "KOSDAQ100", "디지털컨텐츠"),
    Stock("214150", "클래시스", "KOSDAQ100", "의료정밀기기"),
    Stock("141080", "리가켐바이오", "KOSDAQ100", "기타서비스"),
    Stock("357780", "솔브레인", "KOSDAQ100", "반도체"),
    Stock("263750", "펄어비스", "KOSDAQ100", "디지털컨텐츠"),
]


def _load_from_cache() -> List[Stock]:
    if not os.path.exists(CACHE_PATH):
        return []
    stocks = []
    try:
        with open(CACHE_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("code", "").strip().zfill(6)
                name = row.get("name", "").strip()
                market = row.get("market", "").strip().upper()
                sector = row.get("sector", "").strip()
                if not code:
                    continue
                stocks.append(Stock(code=code, name=name, market=market, sector=sector))
    except Exception as e:
        logger.warning(f"캐시 로드 실패: {e}")
        return []
    return stocks


def _fetch_from_naver() -> List[Stock]:
    """네이버 증권 API를 이용하여 코스피200 / 코스닥100 주요 종목을 가져옵니다."""
    stocks: List[Stock] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # 1. 코스피 200 (KOSPI)
    try:
        url_kospi = "https://finance.naver.com/api/sise/itemList.naver?marketType=KOSPI&pageSize=200"
        res = requests.get(url_kospi, headers=headers, timeout=10)
        data = res.json()
        items = data.get("result", {}).get("itemList", [])
        for item in items:
            code = str(item.get("itemCode", "")).zfill(6)
            name = item.get("itemName", "")
            if code:
                stocks.append(Stock(code=code, name=name, market="KOSPI200", sector=""))
    except Exception as e:
        logger.warning(f"네이버 코스피200 조회 실패: {e}")

    # 2. 코스닥 100 (KOSDAQ 시총 상위 100개)
    try:
        url_kosdaq = "https://finance.naver.com/api/sise/itemList.naver?marketType=KOSDAQ&pageSize=100"
        res = requests.get(url_kosdaq, headers=headers, timeout=10)
        data = res.json()
        items = data.get("result", {}).get("itemList", [])
        for item in items:
            code = str(item.get("itemCode", "")).zfill(6)
            name = item.get("itemName", "")
            if code:
                stocks.append(Stock(code=code, name=name, market="KOSDAQ100", sector=""))
    except Exception as e:
        logger.warning(f"네이버 코스닥100 조회 실패: {e}")

    return stocks


def get_universe(refresh: bool = False) -> List[Stock]:
    if not refresh:
        cached = _load_from_cache()
        if cached:
            logger.info(f"캐시에서 {len(cached)}개 종목 로드")
            return cached

    # 1차 시도: 네이버 금융 API (가장 안정적)
    fetched = _fetch_from_naver()

    if fetched:
        logger.info(f"동적 조회(네이버)로 {len(fetched)}개 종목 로드 완료")
        try:
            save_cache(fetched)
        except Exception as e:
            logger.warning(f"캐시 저장 실패: {e}")
        return fetched

    logger.warning(f"모든 동적 조회 실패 → 폴백 리스트 사용 ({len(FALLBACK_TICKERS)}개)")
    return FALLBACK_TICKERS


def save_cache(stocks: List[Stock]) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["code", "name", "market", "sector"])
        for s in stocks:
            writer.writerow([s.code, s.name, s.market, s.sector])
    logger.info(f"유니버스 캐시 저장 완료: {CACHE_PATH} ({len(stocks)}건)")
