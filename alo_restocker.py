import os, json, re, time
from datetime import datetime
from pathlib import Path
import requests, json, time, random
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
    """HTML에서 재고 상태 판별 (보강 버전)"""
    targets = [
        f"https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}?variant={VARIANT_ID}",
        f"https://www.aloyoga.com/products/{PRODUCT_HANDLE}?variant={VARIANT_ID}",
    ]

    # 우선 HTML 직접 요청
    for url in targets:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code in (403, 429):
                continue
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ").lower()

            # 1) ld+json 확인
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or "{}")
                except Exception:
                    continue
                arr = data if isinstance(data, list) else [data]
                for d in arr:
                    if isinstance(d, dict):
                        offers = d.get("offers")
                        if isinstance(offers, dict):
                            avail = str(offers.get("availability", "")).lower()
                            if "instock" in avail:
                                return True
                            if "outofstock" in avail:
                                return False

            # 2) 메타 태그
            meta_avail = soup.find("meta", {"property": "og:availability"})
            if meta_avail and meta_avail.get("content"):
                val = meta_avail["content"].lower()
                if "instock" in val:
                    return True
                if "outofstock" in val:
                    return False

            # 3) 버튼 상태
            add_btn = soup.select_one("button.add-to-cart, button.product-form__submit")
            if add_btn:
                btn_text = add_btn.get_text(" ", strip=True).lower()
                if "sold out" in btn_text or "품절" in btn_text:
                    return False
                if not add_btn.has_attr("disabled"):
                    return True

            # 4) 텍스트 신호
            signals_out = ["out of stock", "sold out", "품절", "재고 없음",
                           "unavailable", "currently sold out", "coming soon", "장바구니 불가"]
            if any(sig in text for sig in signals_out):
                return False
            if any(sig in text for sig in ["add to bag", "add to cart", "장바구니 담기"]):
                return True

        except Exception as e:
            print("HTML parse error:", e)

    # 최종 fallback: 프록시 텍스트
    for url in targets:
        proxied = f"https://r.jina.ai/http://{url.replace('https://','')}"
        try:
            r = requests.get(proxied, timeout=20)
            if r.status_code == 200:
                txt = r.text.lower()
                if any(sig in txt for sig in ["out of stock", "sold out", "품절", "재고 없음"]):
                    return False
                if "add to bag" in txt or "add to cart" in txt or "장바구니 담기" in txt:
                    return True
        except Exception as e:
            print("Proxy parse error:", e)

    return None

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

# JSON 엔드포인트 재시도에 백오프 추가
def get_json_with_retries():
    endpoints = [
        f"https://www.aloyoga.com/ko-kr/products/{PRODUCT_HANDLE}.js",
        f"https://www.aloyoga.com/products/{PRODUCT_HANDLE}.js",
    ]
    for url in endpoints:
        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code in (403, 429):
                    time.sleep((2 ** attempt) + random.uniform(0.2, 0.8))
                    continue
                r.raise_for_status()
                return r.json()
            except Exception:
                time.sleep((2 ** attempt) + random.uniform(0.2, 0.8))
    raise RuntimeError("Failed to fetch product JSON")

def main():
    # 연결 테스트 메시지
    # send_telegram("🤖 Alo Restocker Bot 연결 OK!")

    try:
        available, size = check_stock()  # 내부에서 JSON→HTML→프록시 순차 시도
    except Exception as e:
        # 완전 실패 시에도 워크플로우 실패로 두지 말고 경고만 남김
        send_telegram(f"⚠️ 재고 확인 실패(임시): {str(e)[:120]}")
        print("Check failed:", e)
        return  # 정상 종료로 처리

    if available is None:
        # 판단 불가 — 다음 주기에 재시도
        send_telegram("⚠️ 재고 상태 판단 불가(임시). 다음 주기에 재시도합니다.")
        return

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

    state["available"] = available
    save_state(state)

if __name__ == "__main__":
    main()
