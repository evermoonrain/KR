# -*- coding: utf-8 -*-
"""
OMNI KR STOCK SCANNER - 메인 실행 스크립트

실행 흐름:
1. 종목 유니버스 로드 (코스피200 + 코스닥100)
2. yfinance 병렬 다운로드
3. 종목별 9단계 필터 평가 + 점수 산정
4. 탈락 기준 미달 종목 제외, 점수순 정렬
5. 엑셀 리포트 생성
6. 텔레그램 발송 (메시지 + 파일)

사용법:
    python main.py                # 전체 실행 (다운로드+스캔+엑셀+텔레그램)
    python main.py --no-telegram    # 텔레그램 발송 생략 (로컬 테스트용)
    python main.py --refresh-universe  # 종목 리스트 새로 받기 (네이버/KRX)
    python main.py --limit 30       # 테스트용: 종목 수 제한
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

from config.universe import get_universe
from engine.downloader import download_universe
from engine.scoring import evaluate_stock, filter_and_rank
from engine.excel_builder import build_excel_report
from engine import telegram_sender

# yfinance 캐시 오류 방지
os.environ["YFINANCE_CACHE_DIR"] = "/tmp/py-yfinance"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def parse_args():
    p = argparse.ArgumentParser(description="OMNI KR STOCK SCANNER")
    p.add_argument("--no-telegram", action="store_true", help="텔레그램 발송 생략")
    p.add_argument("--refresh-universe", action="store_true", help="종목 유니버스를 새로 받기")
    p.add_argument("--limit", type=int, default=None, help="테스트용 종목 수 제한")
    return p.parse_args()


def run(no_telegram: bool = False, refresh_universe: bool = False, limit: int = None):
    start_time = time.time()
    scan_date = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    logger.info(f"=== OMNI KR STOCK SCANNER 시작: {scan_date} ===")

    # 1. 유니버스 로드
    stocks = get_universe(refresh=refresh_universe)
    if limit and limit > 0:
        stocks = stocks[:limit]
    logger.info(f"스캔 대상 종목 수: {len(stocks)}")

    # 2. 다운로드
    price_data = download_universe(stocks)
    if not price_data:
        logger.error("다운로드된 데이터가 없습니다. 네트워크/티커 설정을 확인하세요.")
        sys.exit(1)

    # 3. 종목별 평가
    stock_map = {s.code: s for s in stocks}
    results = []
    for code, df in price_data.items():
        stock = stock_map.get(code)
        if stock is None:
            continue
        try:
            result = evaluate_stock(stock.code, stock.name, stock.market, stock.ticker, df)
            results.append(result)
        except Exception as e:
            logger.warning(f"[{stock.ticker}] 평가 실패: {e}")

    logger.info(f"평가 완료: {len(results)}개 종목")

    # 4. 필터링 + 정렬
    ranked = filter_and_rank(results)
    logger.info(f"필터 통과 종목 수: {len(ranked)} (탈락 기준 미달 {len(results) - len(ranked)}건 제외)")

    for r in ranked[:10]:
        logger.info(f"  [{r.grade}] {r.name}({r.code}) - {r.total_score}점")

    # 5. 엑셀 생성
    excel_path = build_excel_report(ranked, scan_date)

    # 6. 텔레그램 발송
    if not no_telegram:
        try:
            telegram_sender.notify(ranked, excel_path, scan_date)
        except Exception as e:
            logger.error(f"텔레그램 발송 실패: {e}")
            # 발송 실패해도 엑셀 산출물은 남기고 종료 (CI에서 artifact로 확인 가능)
    else:
        logger.info("--no-telegram 옵션으로 텔레그램 발송 생략")

    elapsed = time.time() - start_time
    logger.info(f"=== 완료 (소요시간 {elapsed:.1f}초) ===")
    return excel_path, ranked


if __name__ == "__main__":
    args = parse_args()
    run(
        no_telegram=args.no_telegram,
        refresh_universe=args.refresh_universe,
        limit=args.limit,
    )
