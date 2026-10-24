# CLAUDE.md — 建案驗屋與健檢預約管理系統

給 Claude 的專案摘要。先讀這份，再視需要讀程式碼；使用者操作說明在 `README.md`。

## 使用者與協作方式

- 使用者用**繁體中文**溝通；回覆、UI 文字、程式註解都用繁體中文。
- 偏好**一步一步**做：說明要做什麼 → 實作 → 自己測過（測試 + 實際跑）→ 請使用者實測 → 使用者確認後才 **commit**。
- 分支 `develop`（`main` 只有初始 commit）；每個里程碑一個 commit，結尾加 `Co-Authored-By` 行。不 push。
- commit 前檢查不要帶入：`.env`、`backend/data/*`、`backend/storage/*`、`backend/backups/`、`backend/webapp/`、`backend/logs/`、字型檔。

## 業務流程（四階段）與里程碑（全部完成）

| 階段 | 內容 | 里程碑 |
|---|---|---|
| 0 | 登入（手機號碼+密碼、JWT）、人員與細部權限 | M1 |
| 1 建立建案 | 建案、住戶（含 Excel/CSV 匯入匯出、棟別×樓層產生）、健檢日期區間→30 分鐘時段（每格 3 組、屏蔽區段、可關閉單格/整天）、每建案一份檢查清單（從公司範本複製） | M2 |
| 2 邀請預約 | 每戶專屬預約連結（Email/LINE 分享）、屋主網頁選時段/改期/取消、確認信、不超賣 | M3 |
| 3 驗屋 | APP 逐點 合格/不合格/不適用、備註、拍照、屋主 APP 簽名 → 鎖定 | M4 |
| 4 報告 | 預覽報告 PDF → Review OK → 寄送 PDF+感謝信；外部報告 PDF 上傳（≤30MB、上傳後關閉開關）；7/14 天未完成提醒 | M4、M5 |
| 上線 | 每日備份、電腦版由後端提供 `/app`、Windows 開機自動啟動、EAS 打包設定 | M5、M6 |

另有早期的「委託代驗線上授權」（屋主+受託人簽名合成授權書 PDF，`routers/authorizations.py`，用 `scripts/owner_link.py` 產生屋主連結），與 M3 預約流程獨立。

**尚未實作**（資料表已存在）：預約頁 FAQ／附件（`batch_faqs`、`batch_attachments`）、客戶回傳表單（`custom_forms*`、`form_submissions*`）、獨立名額模式（`quota_mode=independent`、`batch_services`，目前只用共用名額）。

## 目錄

```
backend/                FastAPI + SQLAlchemy 2 + SQLite（Python 3.12，venv 在 backend/.venv）
  run.py                同時啟動 0.0.0.0:8000（管理 API＋公開頁＋/app）與 127.0.0.1:8001（只有公開頁，給對外通道）
  app/main.py           管理用 app；lifespan：自動補資料表/欄位、啟動排程；/app 提供電腦版
  app/public_main.py    對外 app：只有 authorizations.public、booking.public
  app/models.py         全部資料表（25 張）
  app/routers/          auth users projects batches checklist booking inspections reports downloads authorizations system
  app/services/         auth(JWT/權限/下載 token) booking slots reports scheduler backup mailer pdf report_pdf
                        inspection_media units_excel signature links security
  app/templates/        sign.html（授權簽名）、book.html（屋主預約頁）—純 HTML+JS，__CONFIG__ 由後端注入
  scripts/              create_demo_booking owner_link show_outbox reset_admin start_server.sh
  tests/                pytest，test_step*.py 依階段；conftest 用暫存 DB、不讀 .env
mobile/                 Expo SDK 58 + expo-router（routes 在 src/app），React 19.3、RN 0.88、TS 6
  src/app/_layout.tsx   AuthProvider；Stack.Protected：登入後 (app)，未登入 login/setup；connect 都可進
  src/app/(app)/(tabs)/ 建案 index、驗屋 inspections、人員 users、我的帳號 account
  src/app/(app)/        project/[id]/…、batch/[id]/{index,invites,settings}、inspection/[bookingId]/{index,sign}、overdue、user/[id]
  src/lib/              api.ts（型別+全部 API，純 TS 可在 node 測）auth.tsx settings.ts files.ts url.ts dates.ts units.ts useLoad.ts labels.ts dialogs.ts
  src/components/       ui.tsx（Screen/Card/Field/Button/Message/ListRow…）overlays.tsx（PromptModal/ActionSheet）pickers.tsx SignaturePad.tsx
  tests/*.test.mjs      node --test（直接 import .ts 純函式）
deploy/windows/         install/uninstall-autostart.ps1（UTF-8 BOM！）
```

## 常用指令

```bash
# 後端
cd backend && source .venv/bin/activate
python run.py [--tunnel]          # --tunnel：Cloudflare 快速通道；使用者已改用 Tailscale Funnel（PUBLIC_BASE_URL）
timeout 300 .venv/bin/python -m pytest -q     # 目前 77 passed
# APP
cd mobile
npm run wifi | npm run 5g [-- --clear]        # Expo 開發伺服器（QR code 用正確 IP）
npx tsc --noEmit && npm test                  # 型別 + 單元測試（12 passed）
npx expo export --platform android --platform ios --output-dir <tmp>   # 打包檢查
npm run build:web                             # 電腦版 → backend/webapp（baseUrl=/app）
npx -y expo-doctor
```

新增 Expo 套件一律用 `npx expo install <pkg>`（SDK 相容版本）；Expo API 以 https://docs.expo.dev 當前文件為準（`mobile/AGENTS.md`）。

## 架構重點與規則

- **權限**：`PERMISSIONS`（models.py）＝ project.manage、batch.manage、booking.view、booking.manage、inspection.edit、report.manage、user.manage；super_admin 全有。後端用 `require_permission` / `require_any_permission`；APP 用 `useAuth().can()`。
- **X-Admin-Key**（`.env` ADMIN_INIT_KEY）只用於 `/init-db`、`/db/status`、`/auth/setup`（建立第一位管理者）。其他一律 JWT。
- **改密碼/停用即踢出**：JWT 帶 `pwd`（密碼雜湊尾碼）。登入失敗 5 次鎖 5 分鐘（記憶體）。
- **下載連結**：瀏覽器/`<Image>` 無法帶 header → `create_download_token(kind,id)` 產生短效 URL，`routers/downloads.py` 依 kind 回檔（units 匯出、photo、inspection_signature、inspection_report、external_report）。只在 8000，不經對外通道。
- **資料庫升級**：沒有 Alembic。新增欄位 → `add_missing_columns()` 啟動時自動 `ALTER TABLE ADD COLUMN`；**新欄位必須 nullable 或有 server_default**（布林用 `server_default=text("1")`）。新資料表由 `create_all` 建立。改型別/約束需自己寫遷移。
- **狀態機**：Booking `booked → completed`（簽名）／`cancelled`；`ACTIVE_STATUSES=(booked, completed)` 佔名額；同戶同批次一筆有效預約（partial unique index）。Inspection `in_progress → signed →（Review OK）approved → sent`；signed 才能 reopen；approved 未寄可 unapprove。報告完成 ＝ 有外部報告或 inspection=sent。
- **不超賣**：`services/booking.book()` 先 insert/flush 再數該格有效預約，超過就 rollback（SQLite 寫入序列化）。
- **檢查清單**：`inspection_categories.project_id` NULL＝公司範本；建案建立時 `copy_template_to_project`；已有結果的檢查點不能刪只能停用；驗屋畫面保留「已停用但有結果」的點。
- **Email**：`SMTP_HOST` 空白時寫入 `storage/outbox/*.eml`（`python -m scripts.show_outbox` 查看）；寄信放 BackgroundTasks、失敗只記 log。
- **排程**：APScheduler（Asia/Taipei），`REMINDER_HOUR`(9) 提醒、`BACKUP_HOUR`(3):30 備份；`run.py` 一個程序兩個 app 共用 lifespan → `start_scheduler` 有旗標只啟動一次。測試設 `SCHEDULER_ENABLED=false`。
- **PDF**：ReportLab + pypdf，字型 `contract_font()`（`PDF_FONT_PATH` → backend/fonts/*.ttf → Windows 標楷體 kaiu.ttf → MSung-Light）。報告用 platypus、`wordWrap='CJK'`；`_p()` 會跳脫 `<>`，要用顏色標記時直接用 `Paragraph`。
- **照片**：EXIF 轉正、長邊 1600、JPEG；簽名由 APP 傳筆畫座標，後端 Pillow 3 倍繪製後縮小成透明 PNG。

## APP 端的坑（都踩過）

- **expo/fetch 是手機上的全域 fetch**，不支援 RN 舊式 `{uri,name,type}` FormData → 手機上傳用 `expo-file-system` 的 `new File(uri).upload(...)`（`lib/files.ts uploadFile`）；網頁用瀏覽器 `File`。
- 路由型別（typedRoutes）在 `expo start` 時產生；新增路由後 tsc 報 Href 錯誤 → 跑一次 `CI=1 timeout 60 npx expo start --port 8099` 或使用者的 Metro 會自動更新。
- 非路由程式不要放在 `src/app/`（不要從 route 檔 export 常數，放 `src/lib`）。
- iOS：關閉 Modal 後立刻開另一個 Modal/Alert 會失敗 → ActionSheet 選項延遲 400ms 執行。標題列半透明 → ScrollView/FlatList 加 `contentInsetAdjustmentBehavior="automatic"`。
- Modal 裡的錯誤要顯示在 Modal 內（顯示在後面頁面會被擋住）。
- 網頁版：需要 `react-native-web`；datetimepicker 沒網頁版 → `pickers.tsx` 用 `createElement('input', {type:'date'})`；`Alert` 改 `window.confirm/prompt`。
- RN 0.88：`StyleSheet.absoluteFillObject` 不存在，用 `absoluteFill`。
- 主機位址：`normalizeBaseUrl` 容忍全形、空白、多餘路徑；Expo Go 由 `Constants.expoConfig.hostUri` 預填；網頁版由後端提供時自動用 `window.location.host`。

## 使用者環境（Windows + WSL2 Ubuntu-24.04）

- WSL **mirrored 網路**；區網 IP `192.168.68.109`、Tailscale `100.76.33.111`；對外固定網址用 Tailscale Funnel（網址在 `.env` 的 PUBLIC_BASE_URL；Funnel 轉發到 8001）。
- **Windows 自己連 192.168.68.109 會逾時**（mirrored 限制）→ 電腦上一律用 `localhost`。
- 防火牆 8000、8081 已開（Windows + Hyper-V 兩道）。
- `~/.bashrc`：venv activate 必須在 nvm 之後，否則再 activate 時 PATH 被還原 → 跑到 Windows 版 npm（`/mnt/c/Program Files/nodejs`）。症狀：UNC 路徑錯誤、ENOTEMPTY。急救：`source ~/.nvm/nvm.sh`。
- cloudflared 在 `~/.local/bin`；Expo 帳號 `service.hopo`，EAS projectId 在 `mobile/app.json`。
- Windows PowerShell 5.1 讀 UTF-8 無 BOM 的 .ps1 會亂碼 → .ps1 存成 UTF-8 BOM。
- 自動模式下下載/執行外部二進位檔會被權限擋 → 給使用者指令自行執行。

## 驗證方式（我自己測試時）

- 後端：pytest；需要真實流程時用 scratchpad 的暫存 DB 起 uvicorn（`APP_ENV_FILE=/nonexistent DATABASE_URL=sqlite:///<tmp> STORAGE_DIR=<tmp> ADMIN_INIT_KEY=k JWT_SECRET_FILE=<tmp> SCHEDULER_ENABLED=false`），**不要動使用者的 `backend/data/inspection.db`**。
- APP 的 API 呼叫：node 直接 `import mobile/src/lib/api.ts` 打暫存後端。
- 畫面：`npx expo export --platform web` → 小型 SPA 靜態伺服器 → scratchpad 裡裝的 `puppeteer-core` + `/usr/bin/google-chrome` headless，localStorage 預設 `server.host`、`auth.token`、`auth.user`。
- PDF：`pypdfium2`（scratchpad venv）轉圖片後目視檢查。
- 手機原生行為（相機、手指簽名、iOS 分享/Modal）無法在這裡測 → 明確告知使用者需實機確認。
