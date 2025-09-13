import os, json, re, time
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PRODUCT_HANDLE = os.getenv("PRODUCT_HANDLE", "w9536r-seamless-delight-high-neck-bra-white-heather")
VARIANT_ID = os.getenv("VARIANT_ID", "43774160568500")

STATE_FILE = Path(".alo_stock_state.json")

# 깃허브 액션 IP 차단 우회용 헤더 (일반 브라우저 흉내)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
BASE_PRODUCT_PAGE = f"https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}?variant={VARIANT_ID}"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko,en;q=0.9",
    "Referer": BASE_PRODUCT_PAGE,
    "Connection": "keep-alive",
}

def send_telegram(msg: str):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "disable_web_page_preview": True},
            timeout=20,
        )
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

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def get_json_with_retries():
    """Shopify .js 공개 JSON을 여러 경로/재시도로 시도"""
    endpoints = [
        f"https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}.js",
        f"https://www.aloyoga.com/products/{PRODUCT_HANDLE}.js",
    ]
    last_err = None
    for url in endpoints:
        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code == 403:
                    # 잠깐 대기 후 재시도
                    time.sleep(1 + attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                time.sleep(1 + attempt)
    raise last_err if last_err else RuntimeError("Failed to fetch product JSON")

def parse_html_fallback():
    """HTML에서 보조 판별 (ld+json의 availability 또는 텍스트 신호)"""
    r = requests.get(BASE_PRODUCT_PAGE, headers=HEADERS, timeout=20)
    if r.status_code == 403:
        # locale 없이도 한 번 더
        alt = f"https://www.aloyoga.com/products/{PRODUCT_HANDLE}?variant={VARIANT_ID}"
        r = requests.get(alt, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ").lower()

    # 1) ld+json에서 "availability"
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        # 단일/리스트 모두 대응
        candidates = data if isinstance(data, list) else [data]
        for d in candidates:
            if isinstance(d, dict) and d.get("@type") in ("Product", "Offer"):
                avail = (d.get("offers") or {}).get("availability") if "offers" in d else d.get("availability")
                if isinstance(avail, str):
                    if "instock" in avail.lower():
                        return True
                    if "outofstock" in avail.lower():
                        return False

    # 2) 텍스트 신호
    out_signals = ["out of stock", "sold out", "품절", "재고 없음"]
    if any(sig in text for sig in out_signals):
        return False
    # 장바구니 버튼이 보이면 True로 추정 (완벽하진 않지만 보조)
    for btn in soup.find_all(["button", "a"]):
        t = (btn.get_text(strip=True) or "").lower()
        if t in ("add to bag", "add to cart", "장바구니 담기"):
            if btn.has_attr("disabled") or "disabled" in (btn.get("class") or []):
                return False
            return True
    return None  # 판단 불가

def check_stock():
    """우선 .js JSON → 실패 시 HTML 보조"""
    try:
        data = get_json_with_retries()
        variant = next((v for v in data.get("variants", []) if str(v.get("id")) == str(VARIANT_ID)), None)
        if variant is not None:
            return bool(variant.get("available")), variant.get("title") or "L"
    except Exception as e:
        print("JSON check failed, will try HTML fallback:", e)

    html_guess = parse_html_fallback()
    if html_guess is None:
        raise RuntimeError("Unable to determine stock state via HTML fallback")
    return html_guess, "L"

def main():
    # 연결 테스트 메시지(1회)
    send_telegram("🤖 Alo Restocker Bot 연결 OK!")

    available, size = check_stock()

    state = load_state()
    prev = state.get("available")
    if prev != available:
        msg = (
            f"Seamless Delight High Neck Bra\n"
            f"색상/사이즈: White Heather / {size}\n"
            f"상태: {'구매가능 ✅' if available else '품절 ❌'}\n"
            f"링크: {BASE_PRODUCT_PAGE}\n"
            f"업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        send_telegram(msg)

    state["available"] = available
    save_state(state)

if __name__ == "__main__":
    main()
