import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# 환경변수 불러오기 (GitHub Secrets에서 주입됨)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PRODUCT_HANDLE = os.getenv("PRODUCT_HANDLE")
VARIANT_ID = os.getenv("VARIANT_ID")

STATE_FILE = Path(".alo_stock_state.json")


def send_telegram(msg: str):
    """텔레그램으로 메시지 전송"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("Telegram send error:", e)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def check_stock():
    url = f"https://www.aloyoga.com/products/{PRODUCT_HANDLE}.js"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()

    # 해당 변형 찾기
    variant = next((v for v in data["variants"] if str(v["id"]) == str(VARIANT_ID)), None)
    if not variant:
        raise RuntimeError(f"Variant {VARIANT_ID} not found!")

    return variant["available"], variant["title"]


def main():
    # 1) 실행 시작 시 무조건 "연결 OK" 알림
    send_telegram("🤖 Alo Restocker Bot 연결 OK!")

    # 2) 현재 상태 확인
    available, size = check_stock()
    state = load_state()
    prev = state.get("available")

    if prev != available:
        msg = (
            f"Seamless Delight High Neck Bra\n"
            f"색상/사이즈: White Heather / {size}\n"
            f"상태: {'구매가능 ✅' if available else '품절 ❌'}\n"
            f"링크: https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}?variant={VARIANT_ID}\n"
            f"업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        send_telegram(msg)

    # 3) 상태 저장
    state["available"] = available
    save_state(state)


if __name__ == "__main__":
    main()
