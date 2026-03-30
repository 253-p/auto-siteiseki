# JRA指定席 残席発売 自動申し込みボット

JRA指定席サイト（https://jra-tickets.jp/）の残席発売を自動申し込みするPythonスクリプトです。

---

## 注意事項（必ずお読みください）

- **自分のJRAネット会員アカウントで、自分が使用する席のみを申し込む目的で使用してください。**
- 第三者のなりすましや転売目的での使用は規約違反です。
- サイトのHTML構造が変更された場合、セレクタが動作しなくなる可能性があります。
- このスクリプトの利用は自己責任でお願いします。

---

## セットアップ手順

### 1. Pythonのインストール確認

```cmd
python --version
```

Python 3.8以上が必要です。

### 2. Playwrightのインストール

```cmd
pip install playwright
playwright install chromium
```

### 3. ファイルの配置

以下のファイルを `C:\jra_bot` フォルダに配置します。

```
C:\jra_bot\
  ├── config.py     # 設定ファイル（要編集）
  ├── jra_bot.py    # メインスクリプト
  └── README.md     # このファイル
```

---

## config.pyの設定方法

`config.py` をテキストエディタで開いて以下を編集します。

```python
# アカウント情報
USER_ID = "your_user_id"   # JRAネット会員IDに変更
PASSWORD = "your_password" # パスワードに変更

# 競馬場: "東京" または "中山"
RACECOURSE = "東京"

# 開催日: "YYYY/MM/DD" 形式
RACE_DATE = "2025/04/06"

# 席種の優先順位（上から順に試みます）
SEAT_PRIORITY = [
    "グリーン席",
    "指定席A",
    "指定席B",
]
```

### 設定項目一覧

| 設定項目 | 説明 | デフォルト値 |
|---|---|---|
| `USER_ID` | JRAネット会員ID | `"your_user_id"` |
| `PASSWORD` | パスワード | `"your_password"` |
| `RACECOURSE` | 競馬場（東京 or 中山） | `"東京"` |
| `RACE_DATE` | 開催日（YYYY/MM/DD） | `"2025/01/01"` |
| `SEAT_PRIORITY` | 席種の優先順位リスト | グリーン席他 |
| `CONGESTION_MAX_RETRY` | 混雑時の最大リトライ回数 | `60` |
| `CONGESTION_RETRY_INTERVAL` | リトライ間隔（秒） | `3` |
| `PAYMENT_WAIT_SECONDS` | 支払い画面到達後の待機秒数 | `300` |
| `HEADLESS` | ヘッドレスモード（False=画面表示） | `False` |

---

## 実行方法

コマンドプロンプトを開き、作業フォルダに移動してから実行します。

```cmd
cd C:\jra_bot
python jra_bot.py
```

### 実行の流れ

1. ブラウザが自動で開きます（`HEADLESS = False` の場合）
2. ログイン → 競馬場・開催日検索 → 申し込み → 注意事項確認 → 残席発売選択 → 席種選択 → 確定
3. 混雑画面が出た場合は自動でリトライします（最大60回、3秒間隔）
4. 支払い画面に到達すると、ログに `★★★ 支払い画面に到達しました ★★★` と表示されます
5. その後 **300秒（5分）間ブラウザが維持**されるので、手動でお支払い操作を行ってください

---

## セレクタが合わない場合のデバッグ方法

スクリプトのセレクタはJRAチケットサイトの実際のHTMLを確認せずに作成しているため、
サイトの構造によっては動作しない場合があります。

### ブラウザの開発者ツールでセレクタを確認する手順

1. **ブラウザでサイトを開く**
   - `python jra_bot.py` を実行すると `HEADLESS = False` の場合ブラウザが表示されます
   - または通常のブラウザ（Chrome/Edge）でサイトを直接開きます

2. **開発者ツールを開く**
   - `F12` キーを押すか、右クリック → 「検証」を選択

3. **要素を特定する**
   - 開発者ツールの「Elements」タブで、操作したい要素（ボタン・入力フォームなど）を確認します
   - 画面左上の矢印アイコン（要素ピッカー）をクリック後、画面上のボタン等をクリックすると該当HTMLが選択されます

4. **セレクタを取得する**
   - 該当要素を右クリック → 「Copy」→「Copy selector」でCSSセレクタをコピーできます

5. **config.py または jra_bot.py のセレクタを修正する**

   例えば、ログインIDフィールドが以下のHTMLだった場合：
   ```html
   <input type="text" name="memberId" id="memberId">
   ```
   `jra_bot.py` の `id_selectors` リストに `'input[name="memberId"]'` を追加します。

### よくある問題と対処法

| 症状 | 対処法 |
|---|---|
| IDフィールドが見つからない | `id_selectors` にサイトの実際のname/id属性を追加 |
| 競馬場が選択できない | select/radio のname属性を確認して修正 |
| 「申し込みへ」ボタンが見つからない | `__doPostBack` の引数（eventtarget）をHTMLから確認 |
| 混雑画面でリトライが効かない | `congestion_keywords` リストに表示されているテキストを追加 |
| 支払い画面判定が誤動作する | `payment_keywords` リストを実際のテキストに合わせて修正 |

### `__doPostBack` ボタンの確認方法

ASP.NETサイトでよく使われる `__doPostBack` ボタンのeventtarget値を確認するには：

1. 開発者ツールでボタンのHTMLを確認
2. `href="javascript:__doPostBack('ここの値','')"`  の引数を確認
3. `jra_bot.py` の該当箇所に値を記載

```python
# 例
await page.evaluate("__doPostBack('ctl00$ContentPlaceHolder1$btnApply', '')")
```

---

## ファイル構成

```
C:\jra_bot\
  ├── config.py     # 設定ファイル（ID・パスワード・競馬場・開催日等）
  ├── jra_bot.py    # メインスクリプト（Playwrightで自動操作）
  └── README.md     # このファイル
```

---

## 動作環境

- Windows 10 / 11
- Python 3.8以上（3.14.3で動作確認想定）
- Playwright（`pip install playwright` + `playwright install chromium`）
