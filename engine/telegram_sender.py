# -*- coding: utf-8 -*-
"""
텔레그램 발송 모듈
- 요약 메시지(상위 N종목) 전송
- 엑셀 리포트 파일 전송
환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import logging
import os
from datetime import datetime
from typing import List

import requests

from config.settings import TELEGRAM_TOP_N
from engine.scoring import ScanResult

logger = logging.getLogger("telegram")

API_BASE = "https://api.telegram.org/bot{token}"


def _get_credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 설정되지 않았습니다.")
    return token, chat_id


def _escape_md(text: str) -> str:
    chars = r"_*[]()~`>#+-=|{}.!"
    for ch in chars:
        text = text.replace(ch, f"\\{ch}")
    return text

def build_summary_message(results: List[ScanResult], scan_date: str) -> str:
    grade_emoji = {"S": "🟡", "A": "🟢", "B": "🔵", "C": "🟠"}

    lines = []
    lines.append("📊 *OMNI KR STOCK SCANNER*")
    lines.append(f"_{_escape_md(scan_date)}_")
    lines.append("대상: KOSPI200 \\+ KOSDAQ100")
    lines.append("")

    grade_counts = {}
    for r in results:
        grade_counts[r.grade] = grade_counts.get(r.grade, 0) + 1
    dist = "  ".join([f"{g}:{n}" for g, n in sorted(grade_counts.items())])
    lines.append(f"등급분포: {_escape_md(dist)}  \\(총 {len(results)}건\\)")
    lines.append("")
    lines.append(f"🏆 *TOP {min(TELEGRAM_TOP_N, len(results))} 종목*")
    lines.append("")

    for i, r in enumerate(results[:TELEGRAM_TOP_N], start=1):
        emoji = grade_emoji.get(r.grade, "⚪")
        name_esc = _escape_md(r.name)
        market_short = "KP" if r.market == "KOSPI200" else "KQ"
        price_str = _escape_md(f"{r.close:,.0f}")
        score_str = _escape_md(f"{r.total_score:.1f}")
        ticker_esc = _escape_md(r.ticker)
        lines.append(f"{i}\\. {emoji} {name_esc} \\| {ticker_esc} \\| {market_short}")
        lines.append(f"    💰 {price_str}원  \\|  🎯 {score_str}점  \\[{r.grade}\\]")
        lines.append("")

    lines.append("📎 상세 점수표는 첨부 엑셀 파일 참고")
    return "\n".join(lines)

def send_message(text: str, parse_mode: str = "MarkdownV2"):
    token, chat_id = _get_credentials()
    url = API_BASE.format(token=token) + "/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, data=payload, timeout=15)
    if not resp.ok:
        logger.error(f"텔레그램 메시지 전송 실패: {resp.status_code} {resp.text}")
        if parse_mode == "MarkdownV2":
            plain = text.replace("\\", "")
            payload2 = {"chat_id": chat_id, "text": plain, "disable_web_page_preview": True}
            resp2 = requests.post(url, data=payload2, timeout=15)
            if not resp2.ok:
                raise RuntimeError(f"텔레그램 전송 실패(재시도 포함): {resp2.text}")
    resp.raise_for_status()
    logger.info("텔레그램 메시지 전송 완료")


def send_document(filepath: str, caption: str = None):
    token, chat_id = _get_credentials()
    url = API_BASE.format(token=token) + "/sendDocument"
    with open(filepath, "rb") as f:
        files = {"document": (os.path.basename(filepath), f)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        resp = requests.post(url, data=data, files=files, timeout=60)
    if not resp.ok:
        logger.error(f"텔레그램 파일 전송 실패: {resp.status_code} {resp.text}")
    resp.raise_for_status()
    logger.info(f"텔레그램 파일 전송 완료: {filepath}")


def notify(results: List[ScanResult], excel_path: str, scan_date: str = None):
    if scan_date is None:
        scan_date = datetime.now().strftime("%Y-%m-%d %H:%M KST")

    if not results:
        send_message(_escape_md(f"⚠️ {scan_date} 스캔 결과 통과 종목이 없습니다."), parse_mode="MarkdownV2")
        return

    msg = build_summary_message(results, scan_date)
    send_message(msg)
    send_document(excel_path, caption=f"OMNI KR STOCK SCAN {scan_date}")
