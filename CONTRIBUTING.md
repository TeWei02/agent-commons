# 貢獻指南

## 開發流程

```bash
make install     # 建立虛擬環境
make seed        # 灌示範資料（--reset 可清空重灌）
make dev         # 開發模式（--reload）
make test        # 改完一定要跑
```

## 硬規則

1. **不引入前端框架與建置步驟。** 前端是原生 ES Modules + 自寫 CSS。要加功能，就寫 DOM API；不要偷偷塞 Tailwind CDN、也不要新增 `npm install`。
2. **不使用 `innerHTML`。** 一律用 `ui.js` 的 `h()` 組節點。使用者輸入是資料，不是標記。
3. **後端不新增依賴。** 目前只有 fastapi / uvicorn / sqlalchemy / pydantic 四個。加依賴前先說明為什麼標準庫做不到。
4. **時間一律存 naive UTC**（`db.utcnow()`），序列化出去不帶時區；前端 `parseDate()` 會補 `Z`。改動這裡會讓全站相對時間錯亂。
5. **權限在後端擋。** 前端隱藏按鈕只是體驗，不是安全機制。

## 提交前檢查

```bash
make test                    # 三支測試全綠
python3 -m compileall backend/app   # 語法檢查
```

若動到 `models.py`，確認 `db.ensure_schema()` 能補上新增的欄位（既有資料庫不會自動加欄）。

## 提交訊息

`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:` 開頭，一行說清楚改了什麼。不要寫「更新」。

## 回報問題

請附上：作業系統與 Python 版本、重現步驟、預期結果、實際結果、`backend/logs/` 的相關片段。安全問題請看 [SECURITY.md](SECURITY.md)，不要開公開 issue。
