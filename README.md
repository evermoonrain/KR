# OMNI KR STOCK SCANNER

코스피200 + 코스닥100 종목을 대상으로 9단계 필터 파이프라인과 가중치 기반 스코어링으로
상승 모멘텀 초입 종목을 발굴하는 시스템.

## 구조

```
kr_scanner/
├── config/
│   ├── settings.py        # 가중치, 필터 파라미터, 등급 컷오프
│   ├── universe.py        # 코스피200/코스닥100 종목 리스트 관리
│   └── universe_cache.csv # (자동생성) 종목 캐시
├── engine/
│   ├── indicators.py      # 거래량/OBV/VWAP/MFI/MACD/KDJ/RSI/ADX/볼린저밴드 계산
│   ├── scoring.py         # 9단계 필터 + 가중치 스코어링
│   ├── downloader.py      # yfinance 병렬 다운로더
│   ├── excel_builder.py   # 엑셀 리포트 생성
│   └── telegram_sender.py # 텔레그램 발송
├── main.py                 # 메인 실행 스크립트
├── requirements.txt
└── .github/workflows/scan.yml  # GitHub Actions 자동 실행
```

## 점수 체계

| 지표 | 가중치 |
|---|---|
| 거래량 | 30% |
| OBV | 25% |
| VWAP | 15% |
| KDJ | 10% |
| MACD | 8% |
| MFI | 5% |
| RSI | 3% |
| ADX | 2% |
| 볼린저밴드 | 2% |

필터 파이프라인 순서: 거래량 → OBV → VWAP → MFI → MACD → KDJ → RSI → ADX → 볼린저밴드

각 단계는 이진 통과/실패가 아니라 0~1 사이의 강도 점수로 평가되며,
`가중치 × 강도점수`를 모두 합산해 100점 만점 총점을 계산합니다.

## 등급 기준

| 등급 | 점수 |
|---|---|
| S | 85점 이상 |
| A | 70~84점 |
| B | 55~69점 |
| C | 40~54점 |
| 탈락 | 40점 미만 (리포트에서 제외) |

등급 컷오프와 가중치는 `config/settings.py`에서 조정 가능합니다.

## 로컬 실행

```bash
pip install -r requirements.txt

# 텔레그램 없이 테스트 (종목 20개만)
python main.py --no-telegram --limit 20

# 전체 실행
export TELEGRAM_BOT_TOKEN=xxxx
export TELEGRAM_CHAT_ID=xxxx
python main.py
```

## 종목 유니버스 갱신

`yfinance`는 지수 구성종목 API를 제공하지 않으므로,
KRX 정보데이터시스템에서 동적으로 받아오거나 `config/universe_cache.csv`를 직접 관리해야 합니다.

```bash
python main.py --refresh-universe --no-telegram --limit 5  # 캐시 갱신만 확인하고 싶을 때
```

`universe_cache.csv` 형식:
```csv
code,name,market
005930,삼성전자,KOSPI200
247540,에코프로비엠,KOSDAQ100
```

KRX 동적 조회가 실패하면 `config/universe.py`의 `FALLBACK_TICKERS`(대형주 위주 안전망)를 사용합니다.
운영 환경에서는 정확도를 위해 캐시 파일을 분기마다(코스피200/코스닥100 정기변경 시점) 직접 갱신하는 것을 권장합니다.

## GitHub Actions 설정

1. 저장소 Settings → Secrets and variables → Actions에서 등록:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
2. `.github/workflows/scan.yml`의 cron 스케줄은 KST 09:30 / 12:00 / 14:30 / 16:00 (평일)로 기본 설정되어 있습니다.
   GitHub Actions cron은 UTC 기준이며 한국은 DST가 없어 오프셋이 항상 +9시간 고정입니다.
3. Actions 탭에서 "Run workflow"로 수동 실행도 가능합니다 (limit, no_telegram 입력 가능).

## 주의사항

- yfinance 무료 데이터는 약간의 지연(15~20분) 및 간헐적 결측이 있을 수 있습니다.
- 코스닥100은 KRX 공개 API에서 정확히 100종목 단위로 분리되지 않는 경우가 있어,
  동적 조회 실패 시 캐시/폴백 리스트로 대체됩니다. 운영 정확도를 높이려면
  코스닥100 공식 구성종목을 캐시 CSV에 직접 반영하는 것을 권장합니다.
- 본 시스템은 투자 참고용 스코어링 도구이며, 투자 권유나 매매 신호가 아닙니다.
