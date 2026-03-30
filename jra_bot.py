"""
JRA指定席 残席発売 自動申し込みボット
=====================================
対象サイト: https://jra-tickets.jp/

【重要】
このスクリプトのセレクタは実際のHTMLを確認せずに作成しています。
サイトの実際のHTML構造に合わせてセレクタを修正が必要な場合があります。
デバッグ方法はREADME.mdを参照してください。
"""

import asyncio
import time
import sys
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

import config

# ============================================================
# サイトURL
# ============================================================
BASE_URL = "https://jra-tickets.jp/"
LOGIN_URL = "https://my.jra-tickets.jp/login/"

# ============================================================
# ログ出力ヘルパー
# ============================================================
def log(msg: str) -> None:
    print(f"[JRA_BOT] {msg}", flush=True)


# ============================================================
# ステップ1: ログイン
# ============================================================
async def step_login(page: Page) -> bool:
    log(f"ログイン画面を開きます: {LOGIN_URL}")
    try:
        await page.goto(LOGIN_URL, timeout=config.BROWSER_TIMEOUT)
    except Exception as e:
        log(f"サイトへのアクセスに失敗しました: {e}")
        return False

    # --- IDフィールド（会員番号またはメールアドレス）---
    id_selectors = [
        'input[name="mail"]',
        'input[id="loginMail"]',
    ]
    filled_id = False
    for sel in id_selectors:
        try:
            await page.fill(sel, config.USER_ID, timeout=5000)
            log(f"  IDを入力しました (セレクタ: {sel})")
            filled_id = True
            break
        except Exception:
            continue
    if not filled_id:
        log("  [ERROR] IDフィールドが見つかりません。セレクタを確認してください。")
        return False

    # --- パスワードフィールド ---
    pw_selectors = [
        'input[name="confirmation"]',
        'input[id="loginPassword"]',
        'input[type="password"]',
    ]
    filled_pw = False
    for sel in pw_selectors:
        try:
            await page.fill(sel, config.PASSWORD, timeout=5000)
            log(f"  パスワードを入力しました (セレクタ: {sel})")
            filled_pw = True
            break
        except Exception:
            continue
    if not filled_pw:
        log("  [ERROR] パスワードフィールドが見つかりません。セレクタを確認してください。")
        return False

    # --- ログインボタン ---
    login_btn_selectors = [
        'button.btn-login',
        'button.authentication',
        'button:has-text("ログイン")',
        'button[type="submit"]',
        'input[type="submit"]',
        'a:has-text("ログイン")',
        'input[value="ログイン"]',
    ]
    clicked_login = False
    for sel in login_btn_selectors:
        try:
            await page.click(sel, timeout=5000)
            log(f"  ログインボタンをクリックしました (セレクタ: {sel})")
            clicked_login = True
            break
        except Exception:
            continue
    if not clicked_login:
        log("  [ERROR] ログインボタンが見つかりません。セレクタを確認してください。")
        return False

    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
    log("ログイン完了（または遷移完了）")
    return True


# 競馬場名の表示テキストマッピング
RACECOURSE_LABEL_MAP = {
    "東京": "東京競馬場",
    "中山": "中山競馬場",
    "阪神": "阪神競馬場",
    "京都": "京都競馬場",
    "福島": "福島競馬場",
    "新潟": "新潟競馬場",
    "小倉": "小倉競馬場",
    "札幌": "札幌競馬場",
    "函館": "函館競馬場",
}

# ============================================================
# ステップ2: 競馬場・開催日を選択して検索
# ============================================================
async def step_search(page: Page) -> bool:
    log(f"競馬場「{config.RACECOURSE}」、開催日「{config.RACE_DATE}」で検索します")

    # config.RACECOURSEを表示ラベルに変換（例: "東京" → "東京競馬場"）
    racecourse_label = RACECOURSE_LABEL_MAP.get(config.RACECOURSE, config.RACECOURSE)

    # --- 競馬場選択: #dropDownListPlace ---
    # ドロップダウンの全選択肢を取得してログ出力
    try:
        place_options = await page.eval_on_selector_all(
            '#dropDownListPlace option',
            'els => els.map(el => ({value: el.value, text: el.textContent.trim()}))'
        )
        available = [o['text'] for o in place_options if o['value']]
        log(f"  競馬場の選択肢: {available}")
    except Exception:
        available = []

    selected_course = False

    # config指定の競馬場を優先、なければ東京→中山の順で自動選択
    priority = [racecourse_label, config.RACECOURSE, "東京競馬場", "中山競馬場"]
    for label in priority:
        try:
            await page.select_option('#dropDownListPlace', label=label, timeout=3000)
            log(f"  競馬場を選択しました: {label}")
            selected_course = True
            break
        except Exception:
            continue

    if not selected_course and available:
        # それでも選択できなければ最初の選択肢を使用
        try:
            first = next(o for o in place_options if o['value'])
            await page.select_option('#dropDownListPlace', value=first['value'], timeout=3000)
            log(f"  競馬場を自動選択しました（最初の選択肢）: {first['text']}")
            selected_course = True
        except Exception:
            pass

    if not selected_course:
        log("  [ERROR] 競馬場の選択ができませんでした。")
        return False

    # 競馬場選択後、開催日リストが動的更新されるまで待機
    log("  開催日リストの更新を待機中...")
    try:
        await page.wait_for_function(
            "document.querySelector('#dropDownListEventDate') && "
            "document.querySelector('#dropDownListEventDate').options.length > 1",
            timeout=10000
        )
        log("  開催日リストが更新されました")
    except Exception:
        log("  [WARN] 開催日リストの更新を確認できませんでした。そのまま続行します。")

    # --- 開催日選択: #dropDownListEventDate ---
    filled_date = False
    try:
        options = await page.eval_on_selector_all(
            '#dropDownListEventDate option',
            'els => els.map(el => ({value: el.value, text: el.textContent.trim()}))'
        )
        valid_options = [o for o in options if o['value']]
        log(f"  開催日の選択肢: {[o['text'] for o in valid_options]}")

        if config.RACE_DATE:
            # config指定日に一致する選択肢を探す
            matched = next((o for o in valid_options if config.RACE_DATE in o['text'] or o['text'] in config.RACE_DATE), None)
        else:
            matched = None

        if not matched and valid_options:
            # 指定日が見つからなければ最初の選択肢を自動選択
            matched = valid_options[0]
            log(f"  指定日が見つからないため最初の開催日を自動選択します")

        if matched:
            await page.select_option('#dropDownListEventDate', value=matched['value'], timeout=5000)
            log(f"  開催日を選択しました: {matched['text']}")
            filled_date = True
    except Exception as e:
        log(f"  [WARN] 開催日の自動選択に失敗: {e}")

    if not filled_date:
        log("  [WARN] 開催日の選択ができませんでした。手動で確認してください。")

    # --- 検索ボタン: __doPostBack ---
    try:
        await page.evaluate("__doPostBack('ctl00$Main$LinkButtonSearch','')")
        log("  検索ボタンをクリックしました (__doPostBack)")
    except Exception:
        # フォールバック: テキストで探す
        search_btn_selectors = [
            'a[id*="LinkButtonSearch"]',
            'a:has-text("検索")',
            'button:has-text("検索")',
            'input[value="検索"]',
        ]
        clicked_search = False
        for sel in search_btn_selectors:
            try:
                await page.click(sel, timeout=5000)
                log(f"  検索ボタンをクリックしました (セレクタ: {sel})")
                clicked_search = True
                break
            except Exception:
                continue
        if not clicked_search:
            log("  [ERROR] 検索ボタンが見つかりません。")
            return False

    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
    log("検索完了")
    return True


# ============================================================
# ステップ3: 「申し込みへ」ボタンをクリック
# ============================================================
async def step_apply(page: Page) -> bool:
    log("「申し込みへ」ボタンを探します")

    apply_btn_selectors = [
        'a:has-text("申し込みへ")',
        'button:has-text("申し込みへ")',
        'input[value="申し込みへ"]',
        'a:has-text("申込みへ")',
        'button:has-text("申込みへ")',
        'input[value="申込みへ"]',
        # __doPostBack形式のボタン
        'a[href*="__doPostBack"]',
    ]

    clicked = False
    for sel in apply_btn_selectors:
        try:
            await page.click(sel, timeout=5000)
            log(f"  「申し込みへ」ボタンをクリックしました (セレクタ: {sel})")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        # __doPostBack を使ったリンクを JavaScript で直接実行する例
        try:
            # NOTE: 実際のeventtarget値はHTMLを確認して変更が必要です
            await page.evaluate("__doPostBack('btnApply', '')")
            log("  __doPostBack('btnApply', '') を実行しました")
            clicked = True
        except Exception as e:
            log(f"  [ERROR] __doPostBack の実行も失敗: {e}")

    if not clicked:
        log("  [ERROR] 「申し込みへ」ボタンが見つかりません。")
        return False

    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
    return True


# ============================================================
# ステップ4: 注意事項確認ページ
# ============================================================
async def step_agree(page: Page) -> bool:
    log("注意事項確認ページ: チェックボックスにチェックします")

    # --- 確認チェックボックス（Alpine.js x-model="confirmed"）---
    agree_selectors = [
        'input[type="checkbox"][x-model="confirmed"]',
        'input[type="checkbox"]',
    ]
    checked = False
    for sel in agree_selectors:
        try:
            await page.check(sel, timeout=5000)
            log(f"  チェックボックスをチェックしました (セレクタ: {sel})")
            checked = True
            break
        except Exception:
            continue

    if not checked:
        log("  [WARN] チェックボックスが見つかりませんでした。スキップします。")

    # Alpine.jsがクラスを更新するまで少し待機
    await asyncio.sleep(0.5)

    # --- 「次へ進む」ボタン（<p>タグ）---
    next_btn_selectors = [
        'p#js_close_btn',
        'p.btn_03:not(.btn_off)',
        'p:has-text("次へ進む")',
        'button:has-text("次へ進む")',
        'a:has-text("次へ進む")',
        'input[value="次へ進む"]',
    ]
    clicked = False
    for sel in next_btn_selectors:
        try:
            await page.click(sel, timeout=5000)
            log(f"  「次へ進む」をクリックしました (セレクタ: {sel})")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        log("  [ERROR] 「次へ進む」が見つかりません。")
        return False

    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
    return True


# ============================================================
# ステップ5: 指定席選択画面 - 申し込みボタン
# ============================================================
async def step_remaining_seats(page: Page) -> bool:
    log("指定席選択画面: 申し込みボタンを探します")

    remaining_selectors = [
        # 実際のHTMLで確認済み: 「受付中」リンク
        'a:has-text("受付中")',
        'a[href*="SeatKindSelect.aspx"]',
        # 念のため旧テキストも残す
        'a:has-text("残席発売")',
        'button:has-text("残席発売")',
        'a:has-text("残席")',
        'button:has-text("申し込み")',
    ]
    clicked = False
    for sel in remaining_selectors:
        try:
            await page.click(sel, timeout=5000)
            log(f"  申し込みボタンをクリックしました (セレクタ: {sel})")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        log("  [ERROR] 申し込みボタンが見つかりません。")
        return False

    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
    return True


# ============================================================
# ステップ6: 指定席の種類を選択
# ============================================================
async def step_select_seat_type(page: Page) -> bool:
    log(f"席種を優先順位に従って選択します: {config.SEAT_PRIORITY}")

    for seat_name in config.SEAT_PRIORITY:
        seat_selectors = [
            f'a:has-text("{seat_name}")',
            f'button:has-text("{seat_name}")',
            f'input[value="{seat_name}"]',
            f'label:has-text("{seat_name}") input',
            f'td:has-text("{seat_name}") a',
            f'td:has-text("{seat_name}") button',
        ]
        for sel in seat_selectors:
            try:
                element = await page.query_selector(sel)
                if element:
                    await element.click(timeout=5000)
                    log(f"  席種「{seat_name}」を選択しました (セレクタ: {sel})")
                    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
                    return True
            except Exception:
                continue

        log(f"  席種「{seat_name}」は見つかりませんでした。次の候補を試します。")

    log("  [ERROR] 指定した席種がすべて見つかりませんでした。")
    return False


# ============================================================
# ステップ7: 確定ボタンをクリック
# ============================================================
async def step_confirm(page: Page) -> bool:
    log("確定ボタンを探します")

    confirm_selectors = [
        'button:has-text("確定")',
        'input[value="確定"]',
        'a:has-text("確定")',
        'button:has-text("申し込む")',
        'input[value="申し込む"]',
        'button[type="submit"]',
        'input[type="submit"]',
    ]
    clicked = False
    for sel in confirm_selectors:
        try:
            await page.click(sel, timeout=5000)
            log(f"  確定ボタンをクリックしました (セレクタ: {sel})")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        log("  [ERROR] 確定ボタンが見つかりません。")
        return False

    await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
    return True


# ============================================================
# 混雑画面判定
# ============================================================
def is_congestion_page(content: str) -> bool:
    """ページ内容が混雑画面かどうかを判定する"""
    congestion_keywords = [
        "しばらくお待ちください",
        "ただいま混雑しております",
        "アクセスが集中",
        "少々お待ち",
        "混雑",
        "ビジー",
        "busy",
        "please wait",
        "waiting",
    ]
    content_lower = content.lower()
    return any(kw.lower() in content_lower for kw in congestion_keywords)


# ============================================================
# 支払い画面判定
# ============================================================
def is_payment_page(content: str) -> bool:
    """ページ内容が支払い画面かどうかを判定する"""
    payment_keywords = [
        "お支払い",
        "支払い方法",
        "クレジットカード",
        "コンビニ支払い",
        "決済",
        "payment",
    ]
    return any(kw in content for kw in payment_keywords)


# ============================================================
# ステップ8: 混雑画面のリトライ処理
# ============================================================
async def step_wait_for_payment(page: Page) -> bool:
    log("混雑画面のリトライを開始します")
    log(f"  最大 {config.CONGESTION_MAX_RETRY} 回、{config.CONGESTION_RETRY_INTERVAL} 秒間隔でリトライします")

    for attempt in range(1, config.CONGESTION_MAX_RETRY + 1):
        content = await page.content()

        # 支払い画面に到達したか確認
        if is_payment_page(content):
            log(f"  ★ 支払い画面に到達しました！（{attempt}回目）")
            return True

        # 混雑画面かどうか確認
        if is_congestion_page(content):
            log(f"  混雑中... ({attempt}/{config.CONGESTION_MAX_RETRY}) {config.CONGESTION_RETRY_INTERVAL}秒後にリトライ")
            await asyncio.sleep(config.CONGESTION_RETRY_INTERVAL)

            # ページをリロードまたは「更新」ボタンをクリック
            try:
                reload_selectors = [
                    'button:has-text("更新")',
                    'a:has-text("更新")',
                    'button:has-text("再試行")',
                ]
                clicked_reload = False
                for sel in reload_selectors:
                    try:
                        await page.click(sel, timeout=3000)
                        log(f"    更新ボタンをクリックしました (セレクタ: {sel})")
                        clicked_reload = True
                        break
                    except Exception:
                        continue
                if not clicked_reload:
                    await page.reload(timeout=config.BROWSER_TIMEOUT)
                    log("    ページをリロードしました")
                await page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)
            except Exception as e:
                log(f"    リロード中にエラー: {e}")

        else:
            # 混雑画面でも支払い画面でもない場合
            log(f"  ページ状態不明 ({attempt}/{config.CONGESTION_MAX_RETRY}) URL: {page.url}")
            # 支払い画面へ遷移している可能性のある要素を再確認
            content = await page.content()
            if is_payment_page(content):
                log("  ★ 支払い画面に到達しました！")
                return True
            await asyncio.sleep(config.CONGESTION_RETRY_INTERVAL)

    log(f"  [ERROR] 最大リトライ回数 ({config.CONGESTION_MAX_RETRY}回) に達しました。")
    return False


# ============================================================
# ステップ9: 支払い画面到達後の待機
# ============================================================
async def step_payment_reached(page: Page) -> None:
    log("=" * 60)
    log("★★★ 支払い画面に到達しました ★★★")
    log(f"ブラウザをそのまま維持します。{config.PAYMENT_WAIT_SECONDS}秒間手動で操作してください。")
    log(f"現在のURL: {page.url}")
    log("=" * 60)
    await asyncio.sleep(config.PAYMENT_WAIT_SECONDS)
    log("待機時間終了。スクリプトを終了します。")


# ============================================================
# メイン処理
# ============================================================
async def main() -> None:
    log("=" * 60)
    log("JRA指定席 残席発売 自動申し込みボット 起動")
    log(f"  競馬場  : {config.RACECOURSE}")
    log(f"  開催日  : {config.RACE_DATE}")
    log(f"  席種優先: {config.SEAT_PRIORITY}")
    log("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(config.BROWSER_TIMEOUT)

        try:
            # ステップ1: ログイン
            if not await step_login(page):
                log("[ABORT] ログインに失敗しました。スクリプトを終了します。")
                return

            # ステップ2: 競馬場・開催日を選択して検索
            if not await step_search(page):
                log("[ABORT] 検索に失敗しました。スクリプトを終了します。")
                return

            # ステップ3: 「申し込みへ」ボタン
            if not await step_apply(page):
                log("[ABORT] 「申し込みへ」ボタンのクリックに失敗しました。")
                return

            # ステップ4: 注意事項確認
            if not await step_agree(page):
                log("[ABORT] 注意事項確認に失敗しました。")
                return

            # ステップ5: 残席発売申し込みボタン
            if not await step_remaining_seats(page):
                log("[ABORT] 「残席発売」ボタンのクリックに失敗しました。")
                return

            # ステップ6: 席種選択
            if not await step_select_seat_type(page):
                log("[ABORT] 席種の選択に失敗しました。")
                return

            # ステップ7: 確定ボタン
            if not await step_confirm(page):
                log("[ABORT] 確定ボタンのクリックに失敗しました。")
                return

            # ステップ8: 混雑画面リトライ → 支払い画面到達待ち
            # 確定ボタン押下直後に支払い画面になる場合もあるため先に確認
            content = await page.content()
            if is_payment_page(content):
                log("確定後すぐに支払い画面に到達しました。")
            else:
                reached = await step_wait_for_payment(page)
                if not reached:
                    log("[ABORT] 支払い画面への到達に失敗しました。ブラウザを確認してください。")
                    await asyncio.sleep(60)
                    return

            # ステップ9: 支払い画面待機（手動操作へ）
            await step_payment_reached(page)

        except Exception as e:
            log(f"[UNEXPECTED ERROR] 予期せぬエラーが発生しました: {e}")
            log("ブラウザを60秒間維持します。状態を確認してください。")
            await asyncio.sleep(60)
        finally:
            await context.close()
            await browser.close()
            log("ブラウザを閉じました。スクリプト終了。")


if __name__ == "__main__":
    asyncio.run(main())
