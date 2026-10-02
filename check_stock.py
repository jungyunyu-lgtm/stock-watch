"""
경북봐야지 상품 품절 해제 감시 → 디스코드 알림

환경변수
  DISCORD_WEBHOOK_URL  디스코드 웹훅 주소 (필수)
  PRODUCT_URL          감시할 상품 페이지 (기본: 23255번 상품)
  SOLDOUT_KEYWORDS     품절로 판단할 문구, 쉼표 구분 (기본: 품절,매진,SOLD OUT,예약마감)
  STATE_FILE           직전 상태 저장 파일 (기본: state.json)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

URL = os.getenv("PRODUCT_URL", "https://www.gb-voyage.com/activity/detail/23255")
WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
KEYWORDS = [k.strip() for k in os.getenv(
    "SOLDOUT_KEYWORDS", "품절,매진,SOLD OUT,예약마감").split(",") if k.strip()]
STATE_FILE = os.getenv("STATE_FILE", "state.json")
KST = timezone(timedelta(hours=9))


def fetch_page():
    """JS 렌더링이 끝난 페이지의 제목과 본문 텍스트를 가져온다."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="ko-KR")
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(3_000)  # 늦게 뜨는 재고 정보 대기
        text = page.inner_text("body")
        title = page.title()
        # 상품명 후보: 가장 먼저 보이는 h1/h2
        for sel in ("h1", "h2"):
            el = page.query_selector(sel)
            if el and el.inner_text().strip():
                title = el.inner_text().strip()
                break
        browser.close()
    return title, text


def send_discord(content):
    if not WEBHOOK:
        print("DISCORD_WEBHOOK_URL 이 없어 알림을 건너뜀:\n" + content)
        return
    data = json.dumps({"content": content}).encode()
    req = urllib.request.Request(
        WEBHOOK, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "stock-watch"})
    urllib.request.urlopen(req, timeout=15)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    title, text = fetch_page()

    if len(text.strip()) < 50:
        print(f"[{now}] 페이지 내용이 비어 있음 — 이번 회차는 판단 보류")
        return

    found = [k for k in KEYWORDS if k.lower() in text.lower()]
    sold_out = bool(found)
    state = load_state()
    was_sold_out = state.get("sold_out", True)

    print(f"[{now}] {title} → {'품절' if sold_out else '구매 가능'} {found or ''}")

    if was_sold_out and not sold_out:
        send_discord(f"🎉 **품절 해제!** {title}\n{URL}\n(확인 시각 {now})")
    elif not was_sold_out and sold_out:
        send_discord(f"😢 다시 품절됐어요: {title}\n{URL}")

    save_state({"sold_out": sold_out, "checked_at": now, "matched": found})


if __name__ == "__main__":
    if "--test" in sys.argv:
        send_discord("✅ 재입고 알림 연결 테스트입니다.")
    else:
        main()
