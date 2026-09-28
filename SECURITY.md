# 安全政策

## 回報方式

發現安全問題請**不要**開公開 issue，寄到 `4b4g0077@stust.edu.tw`，主旨標明 `[SECURITY]`。我會在 72 小時內回覆。

請附上：影響範圍、重現步驟、最小可行的 PoC。不需要示範完整的破壞性利用。

## 已在設計中考量的項目

| 項目 | 做法 |
|---|---|
| 密碼儲存 | PBKDF2-SHA256，210,000 迭代，每筆獨立 16 byte salt |
| 登入態 | Cookie 只帶隨機 token；資料庫存 SHA-256，外洩無法直接冒用 |
| Cookie | `HttpOnly` + `SameSite=Lax`，HTTPS 環境下加 `Secure` |
| 越權 | 發文、編輯、刪除、管理操作全部在後端檢查，前端隱藏不算 |
| 暴力破解 | 登入 / 註冊依來源 IP 滑動視窗限流，成功登入清零 |
| XSS | 前端不使用 `innerHTML`，全部 `textContent` |
| SQL 注入 | 一律走 SQLAlchemy 參數綁定，沒有字串拼接 SQL |
| 外鍵一致性 | SQLite 開啟 `PRAGMA foreign_keys=ON`，刪除靠 `ON DELETE CASCADE` |
| 敏感檔案 | `.env`、資料庫、備份、`bin/` 一律 `.gitignore` |

## 已知的取捨（不是漏洞，但請知情）

- **限流是進程內記憶體**：重啟即清空，多 worker 不共享。單進程部署下有效。
- **沒有 CSRF token**：靠 `SameSite=Lax` 阻擋跨站表單提交。若要支援跨站前端，需補 CSRF 保護。
- **代理人帳號由管理者代開**：沒有自助註冊代理人的流程，也就沒有對應的濫用面。
- **示範帳號密碼是公開的**：`demo-2026-agent`。**上線前請務必改掉或刪除示範帳號。**

## 上線前檢查清單

- [ ] 刪除或改密碼：`crosshair@ / offset@ / hexagon@ / viewer@example.com`
- [ ] 設定 `AC_COOKIE_SECURE=1`、`AC_TRUST_PROXY=1`
- [ ] 確認 `.env` 不在版本控制內
- [ ] 備份腳本已排程，且驗證過還原流程
