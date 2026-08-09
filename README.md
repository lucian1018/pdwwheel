# 北德文鋁圈型錄

網站使用專案內的本機圖片與 Excel，資料更新不依賴任何外部檔案服務。

## 快速啟動

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

預設網址：`http://127.0.0.1:8000`

> 請使用 `python server.py`；本機圖片 mapping 與 Excel 解析需要後端 API。

## 圖片目錄

商品圖片放在：

```text
public/images/wheels/15/
public/images/wheels/16/
public/images/wheels/17/
public/images/wheels/18/
public/images/wheels/19/
public/images/wheels/20/
public/images/wheels/21/
public/images/wheels/22/
```

系統也會掃描現有型錄使用的 `13/`、`14/`，並允許在尺寸下建立 PCD 子資料夾。

## 圖片 mapping

1. 先限定商品尺寸資料夾。
2. 若圖片放在 `4x100`、`5x112` 等 PCD 子資料夾，會優先比對相同 PCD。
3. 圖片檔名與商品 `name` 或 `model` 正規化比對：
   - 不區分大小寫。
   - 忽略空格、`-`、`_`、括號與副檔名。
   - `BBS RI-A` 可對應 `BBS-RI-A.jpg`。
   - 圖片檔名可在型號後加表面處理，例如 `1663 古銅.jpg`。
4. 表面處理相同時優先。
5. 若舊商品資料已有 `image` 檔名，會作為兼容 fallback。
6. 同分時使用本機修改時間較新的圖片。

新增圖片後無需修改 JavaScript 或 HTML。圖片索引快取為 30 秒；也可請求 `/api/catalog?refresh=1` 立即重建。

## 庫存 Excel

請放在：

```text
data/inventory/
```

- 預設挑選檔名以「台北庫存」開頭且本機修改時間最新的 `.xlsx`。
- Excel 只讀入記憶體，並以 openpyxl `read_only=True` 解析。
- 自動辨識型號／品名、吋數／尺寸、庫存／數量欄位。
- 庫存以「商品型號＋尺寸」合併到型錄商品。
- 沒有 Excel 時 `/api/stock/latest` 回傳 404，但商品型錄仍會正常顯示。

## API

- `GET /api/health`：本機圖片與庫存目錄狀態。
- `GET /api/catalog`：商品、本機圖片 mapping 與庫存合併結果。
- `GET /api/stock/latest`：最新本機庫存 Excel 解析結果。

`data/inventory/`、後端原始碼與專案內其他非公開檔案都不會透過靜態路由提供下載。
