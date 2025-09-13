from dotenv import load_dotenv
load_dotenv()


import os, sys, json, time, re
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

# ==== 환경변수 ====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # 예: 123456:ABC-DEF...
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")    # 예: 123456789
# 상품 핸들(색상 포함 URL의 slug)과 variant id (L 사이즈)
PRODUCT_HANDLE     = os.getenv("PRODUCT_HANDLE", "w9536r-seamless-delight-high-neck-bra-white-heather")
VARIANT_ID         = int(os.getenv("VARIANT_ID", "43774160568500"))

# 한국어 스토어 경로 사용(ko-kr). 지역 경로가 바뀌어도 .js 엔드포인트는 보통 공통으로 동작.
BASE_PRODUCT_URL = f"https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}"
PRODUCT_JSON_URL = f"https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}.js"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockWatcher/1.0; +https://example.com)"
}

STATE_FILE = ".alo_stock_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_status_via_json():
    """Shopify 공개 JSON에서 variants 배열의 available 확인"""
    r = requests.get(PRODUCT_JSON_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    for v in data.get("variants", []):
        if int(v.get("id")) == VARIANT_ID:
            return bool(v.get("available")), v.get("title"), data.get("title")
    # 못찾으면 None
    return None, None, data.get("title")

def get_status_via_html_fallback():
    """HTML에서 보조 판별: 품절 메시지/버튼 상태 등"""
    r = requests.get(BASE_PRODUCT_URL + f"?variant={VARIANT_ID}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ").lower()
    # 흔한 신호들: "out of stock", "sold out", "재고 없음", 버튼 disabled 등
    out_signals = ["out of stock", "sold out", "품절", "재고 없음"]
    if any(sig in text for sig in out_signals):
        return False
    # Add to Bag 버튼이 disabled로 렌더되면 품절로 간주
    for btn in soup.find_all(["button", "a"]):
        if btn.get_text(strip=True).lower() in ["add to bag", "add to cart", "장바구니 담기"]:
            if btn.has_attr("disabled") or "disabled" in btn.get("class", []):
                return False
            return True
    # 판단 불가 시 None
    return None

def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 환경변수 미설정: 메시지를 보낼 수 없습니다.", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=15).raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}", file=sys.stderr)

def format_msg(available: bool, variant_title: str, product_title: str):
    status = "구매가능 ✅" if available else "품절 ❌"
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return (
        f"<b>{product_title}</b>\n"
        f"색상/사이즈: {variant_title or 'White Heather / L'}\n"
        f"상태: <b>{status}</b>\n"
        f"링크: {BASE_PRODUCT_URL}?variant={VARIANT_ID}\n"
        f"업데이트: {now}"
    )

def main():
    # 1) 1차: JSON으로 확정 판별
    available, variant_title, product_title = None, None, None
    try:
        available, variant_title, product_title = get_status_via_json()
    except Exception as e:
        print(f"JSON 체크 오류: {e}", file=sys.stderr)
    # 2) 2차: HTML 보조 판별
    if available is None:
        try:
            html_check = get_status_via_html_fallback()
            if html_check is not None:
                available = html_check
        except Exception as e:
            print(f"HTML 보조 체크 오류: {e}", file=sys.stderr)
    if available is None:
        print("상태를 확정할 수 없습니다. 다음 실행 때 재시도합니다.", file=sys.stderr)
        return

    state = load_state()
    prev = state.get(str(VARIANT_ID))
    state[str(VARIANT_ID)] = {"available": available, "ts": int(time.time())}
    save_state(state)

    # 상태 변화 시에만 알림
    if prev is None or bool(prev.get("available")) != available:
        msg = format_msg(available, variant_title, product_title or "Seamless Delight High Neck Bra")
        send_telegram(msg)
        print("상태 변화 감지 → 텔레그램 알림 보냄.")
    else:
        print("상태 변화 없음.")

if __name__ == "__main__":
    main()
