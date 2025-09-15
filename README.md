# Alo Yoga 재입고 알리미 (Telegram Bot)

Alo Yoga 상품의 특정 색상/사이즈가 **품절 → 재입고** 될 때 텔레그램으로 알림을 주는 파이썬 스크립트입니다.  
Shopify 공개 JSON API(`/products/<handle>.js`)를 이용해 변형(variant)의 `available` 상태를 확인합니다.

---

## 두 가지 실행 방식

### 1) GitHub Actions (추천 · 프라이빗 레포 + Secrets 사용)
- **노트북이 꺼져 있어도** 24/7 주기 실행 가능
- 민감정보(봇 토큰/Chat ID)는 **Settings → Secrets**에 안전하게 보관
- 상태 파일(`.alo_stock_state.json`)을 **레포에 커밋**하여 중복 알림을 방지

### 2) 로컬/서버에서 크론으로 실행
- `env.sh`를 source 한 후 크론에 등록
- (자세한 내용은 이전 README 참조)

---

## GitHub Actions로 설정하기

### 0) 레포 만들기 / 프라이빗 설정
- GitHub에서 새 레포 생성
- **Private** 으로 생성 (Settings → General → Danger Zone에서 Visibility 확인)

### 1) 파일 3개를 레포에 추가
- `alo_restocker.py` (파이썬 스크립트)
- `.github/workflows/alo_checker.yml` (아래 예시 그대로 사용)
- (선택) `README.md`

> 참고: Actions 러너는 매 실행마다 깔끔한 환경에서 시작하므로, **중복 알림 방지**를 위해 `.alo_stock_state.json`을 레포에 커밋/푸시하여 상태를 지속적으로 저장합니다.

### 2) Secrets 등록
레포 → **Settings → Secrets and variables → Actions → New repository secret** 에서 아래 키를 추가합니다.

- `TELEGRAM_BOT_TOKEN` = `123456:ABC-DEF...`
- `TELEGRAM_CHAT_ID` = `987654321`

### 3) 워크플로우 파일 예시 (`.github/workflows/alo_checker.yml`)
```yaml
name: Alo Restock Checker

on:
  schedule:
    - cron: "*/5 * * * *"   # 5분마다 실행
  workflow_dispatch:        # 필요 시 수동 실행

permissions:
  contents: write           # 상태 파일(.alo_stock_state.json) 커밋/푸시를 위해 필요

jobs:
  check-stock:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install requests beautifulsoup4

      - name: Run script
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          PRODUCT_HANDLE: w9536r-seamless-delight-high-neck-bra-white-heather
          VARIANT_ID: 12134556678
        run: |
          python alo_restocker.py

      - name: Commit & push state if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          # 상태 파일이 변경됐으면 커밋
          if [[ -n "$(git status --porcelain .alo_stock_state.json)" ]]; then
            git add .alo_stock_state.json
            git commit -m "chore: update state [skip ci]" || true
            git push
          fi
```

### 4) 동작 방식
- GitHub Actions가 20분마다 실행됩니다.
- 실행 시 동작 순서:
  1. **연결 확인 메시지** (`🤖 Alo Restocker Bot 연결 OK!`) — 매 실행마다 발송됨.
  2. **재고 상태 확인**
     - 최초 실행 시: 현재 상태(품절/재고)를 텔레그램으로 발송합니다.
     - 이후 실행 시: 상태가 **변경된 경우에만** 새로 알림을 발송합니다.
- 따라서, 품절 상태가 계속 유지되면 추가 알림은 오지 않습니다.


## 로컬에서 테스트하고 싶다면 (선택)
로컬에서는 `env.sh`를 사용해 환경변수를 로드한 뒤 스크립트를 실행하세요.

```bash
# env.sh
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="987654321"
export PRODUCT_HANDLE="w9536r-seamless-delight-high-neck-bra-white-heather"
export VARIANT_ID="43774160568500"

# 실행
source env.sh
python3 alo_restocker.py
```

---

## 알림 예시

```
Seamless Delight High Neck Bra
색상/사이즈: White Heather / L
상태: 구매가능 ✅
링크: https://www.aloyoga.com/ko-kr/products/w9536r-seamless-delight-high-neck-bra-white-heather?variant=43774160568500
업데이트: 2025-09-13 10:15
```

---

## 참고
- Shopify 상품 JSON: `/products/<handle>.js` → variants 배열 내 `available: true/false`
- HTML 내 `"Out Of Stock"` 텍스트, 버튼 disabled 속성 등으로 보조 판별
- Actions 실행 주기는 최소 5분 단위 권장
- 매 실행마다 오는 연결 메시지가 불필요하다면, `alo_restocker.py`의 `send_telegram("🤖 Alo Restocker Bot 연결 OK!")` 부분을 주석 처리하면 됩니다.
