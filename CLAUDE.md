# CLAUDE.md — 建案驗屋與健檢預約管理系統

給 Claude 的專案摘要。先讀這份，再視需要讀程式碼；使用者操作說明在 `README.md`。

## 使用者與協作方式

- 使用者用**繁體中文**溝通；回覆、UI 文字、程式註解都用繁體中文。
- 偏好**一步一步**做：說明要做什麼 → 實作 → 自己測過（測試 + 實際跑）→ 請使用者實測 → 使用者確認後才 **commit**。
- 分支 `develop`（`main` 只有初始 commit）；每個里程碑一個 commit，結尾加 `Co-Authored-By` 行。不 push。
- `backend/.env.example` ＝ 實際設定（含 SMTP 密碼、鹽值），使用者決定放進 git（repo 私人）；`./install.sh`（＝`run.py --install`）新環境執行一次會複製成 `.env`。
- `backend/data/inspection.db`（資料庫；`.jwt_secret` 不進 git，新環境自動產生、需重新登入）與 `backend/storage/`（照片、簽名、報告）也放進 git，使用者決定；commit 資料前要先停掉 `run.py`（避免 WAL 未寫回）。
- commit 前檢查不要帶入：`.env`、`*.db-wal`/`*.db-shm`、`backend/backups/`、`backend/webapp/`、`backend/logs/`、字型檔。

## 業務流程（四階段）與里程碑（全部完成）

| 階段 | 內容 | 里程碑 |
|---|---|---|
| 0 | 登入（手機號碼+密碼、JWT）、人員與細部權限 | M1 |
| 1 建立建案 | 建案、住戶（含 Excel/CSV 匯入匯出、棟別×樓層產生）、健檢日期區間→30 分鐘時段（每格 3 組、屏蔽區段、可關閉單格/整天）、每建案一份檢查清單（從公司範本複製） | M2 |
| 2 邀請預約 | 每戶專屬預約連結（Email/LINE 分享）、屋主網頁選時段/改期/取消、確認信、不超賣 | M3 |
| 3 驗屋 | APP 逐點 合格/不合格/不適用、備註、拍照、屋主 APP 簽名 → 鎖定 | M4 |
| 4 報告 | 預覽報告 PDF → Review OK → 寄送 PDF+感謝信；外部報告 PDF 上傳（≤30MB、上傳後關閉開關）；7/14 天未完成提醒 | M4、M5 |
| 上線 | 每日備份、電腦版由後端提供 `/app`、Windows 開機自動啟動、EAS 打包設定 | M5、M6 |
| 之後 | PWA（主畫面圖示 H）；建案內**四階段**：建立系統／預約參觀／預約驗屋／預約健檢；建案儀表板＋主管會議報表（互動 HTML、Excel 原生圖表）；全部資料 Excel/CSV 匯出匯入 | — |

另有早期的「委託代驗線上授權」（屋主+受託人簽名合成授權書 PDF，`routers/authorizations.py`，用 `scripts/owner_link.py` 產生屋主連結），與 M3 預約流程獨立。

**尚未實作**（資料表已存在）：預約頁 FAQ／附件（`batch_faqs`、`batch_attachments`）、客戶回傳表單（`custom_forms*`、`form_submissions*`）、獨立名額模式（`quota_mode=independent`、`batch_services`，目前只用共用名額）。

## 目錄

```
backend/                FastAPI + SQLAlchemy 2 + SQLite（Python 3.12，venv 在 backend/.venv）
  run.py                同時啟動 0.0.0.0:8000（管理 API＋公開頁＋/app）與 127.0.0.1:8001（只有公開頁，給對外通道）
  app/main.py           管理用 app；lifespan：自動補資料表/欄位、啟動排程；/app 提供電腦版
  app/public_main.py    對外 app：只有 authorizations.public、booking.public
  app/models.py         全部資料表（34 張）
  app/routers/          auth users projects batches checklist booking inspections reports downloads authorizations system sheets
  app/services/         auth(JWT/權限/下載 token) booking slots reports scheduler backup mailer pdf report_pdf
                        inspection_media units_excel signature links security
                        dashboard（儀表板數字）project_report（報表 HTML/xlsx）sheets（Excel 匯出匯入框架）sheet_datasets（各資料定義）
  app/templates/        sign.html（授權簽名）、book.html（屋主預約頁）—純 HTML+JS，__CONFIG__ 由後端注入
                        project_report.html（主管會議互動報表，SVG 圖表，__DATA__ 注入、< 已跳脫）
  scripts/              create_demo_booking owner_link show_outbox reset_admin start_server.sh
  tests/                pytest，test_step*.py 依階段；conftest 用暫存 DB、不讀 .env
mobile/                 Expo SDK 58 + expo-router（routes 在 src/app），React 19.3、RN 0.88、TS 6
  src/app/_layout.tsx   AuthProvider；Stack.Protected：登入後 (app)，未登入 login/setup；connect 都可進
  src/app/(app)/index   部門選單（登入後第一頁，標題列是 HOMPRO 圓圈；`lib/departments.ts` 目前只有售服部，其他部門建置好再加）
  src/app/(app)/service/ 售服部底部分頁：建案 index（左案名方塊＋封面照片、右緊湊時間軸 `Timeline compact`；`components/SwipeRow` 往右滑釘選／往左滑備份＋刪除；長按拖曳排序 `components/DragSort` useDragSort，列表用 ScrollView 不用 FlatList）、行程 inspections（上方 `components/TwoWeekCalendar` 兩週日曆，`GET /inspections/schedule/counts`）、HOMPRO（中間凸起圓鈕 `components/Hompro.tsx`，dismissTo('/') 回部門選單）、人員 users、我的帳號 account
  src/app/(app)/        project/[id]/…、batch/[id]/{index,invites,settings}、inspection/[bookingId]/{index,sign}、overdue、user/[id]
  src/lib/              api.ts（型別+全部 API，純 TS 可在 node 測）auth.tsx settings.ts files.ts url.ts dates.ts units.ts useLoad.ts labels.ts dialogs.ts
  src/components/       ui.tsx（Screen/Card/Field/Button/Message/ListRow…）overlays.tsx（PromptModal/ActionSheet）pickers.tsx SignaturePad.tsx
                        charts.tsx（純 View 圖表）ProjectDashboard.tsx SheetTransfer.tsx（useSheetTransfer：Excel 匯出匯入選單＋狀態）
  public/               index.html（PWA 標籤）manifest.json icons/；scripts/make_icons.py 產生全部圖示
  tests/*.test.mjs      node --test（直接 import .ts 純函式）
deploy/windows/         install/uninstall-autostart.ps1（UTF-8 BOM！）
```

## 常用指令

```bash
# 後端
cd backend && source .venv/bin/activate
python3 run.py [--tunnel]         # 不需先 activate，會自動用 .venv；--tunnel：Cloudflare 快速通道；使用者已改用 Tailscale Funnel（PUBLIC_BASE_URL）
timeout 300 .venv/bin/python -m pytest -q     # 目前 112 passed
# APP
cd mobile
npm run wifi | npm run 5g [-- --clear]        # Expo 開發伺服器（QR code 用正確 IP）
npx tsc --noEmit && npm test                  # 型別 + 單元測試（17 passed）
# 不要跑 npx expo lint：專案沒有 ESLint，它會自動安裝並改 package.json
# 不要跑 npx prettier：專案沒有 Prettier，它會下載後用預設（雙引號、80 字）重排整個檔案；本專案是單引號、手工排版
npx expo export --platform android --platform ios --output-dir <tmp>   # 打包檢查
npm run build:web                             # 電腦版 → backend/webapp（baseUrl=/app）
npx -y expo-doctor
```

新增 Expo 套件一律用 `npx expo install <pkg>`（SDK 相容版本）；Expo API 以 https://docs.expo.dev 當前文件為準（`mobile/AGENTS.md`）。

## 架構重點與規則

- **權限**：`PERMISSIONS`（models.py）＝ project.manage、batch.manage、booking.view、booking.manage、inspection.edit、report.manage、user.manage；super_admin 全有。後端用 `require_permission` / `require_any_permission`；APP 用 `useAuth().can()`。
- **X-Admin-Key**（`.env` ADMIN_INIT_KEY）只用於 `/init-db`、`/db/status`、`/auth/setup`（建立第一位管理者）。其他一律 JWT。
- **改密碼/停用即踢出**：JWT 帶 `pwd`（密碼雜湊尾碼）。登入失敗 5 次鎖 5 分鐘（記憶體）。
- **下載連結**：瀏覽器/`<Image>` 無法帶 header → `create_download_token(kind,id)` 產生短效 URL，`routers/downloads.py` 依 kind 回檔（units、project_report、sheet、photo、inspection_signature、inspection_report、external_report）。權限在產生連結時檢查。只在 8000，不經對外通道。
- **資料庫升級**：沒有 Alembic。新增欄位 → `add_missing_columns()` 啟動時自動 `ALTER TABLE ADD COLUMN`；**新欄位必須 nullable 或有 server_default**（布林用 `server_default=text("1")`）。新資料表由 `create_all` 建立。改型別/約束需自己寫遷移。
- **狀態機**：Booking `booked → completed`（簽名）／`cancelled`；`ACTIVE_STATUSES=(booked, completed)` 佔名額；同戶同批次一筆有效預約（partial unique index）。Inspection `in_progress → signed →（Review OK）approved → sent`；signed 才能 reopen；approved 未寄可 unapprove。報告完成 ＝ 有外部報告或 inspection=sent。
- **不超賣**：`services/booking.book()` 先 insert/flush 再數該格有效預約，超過就 rollback（SQLite 寫入序列化）。
- **四階段 / 服務**：`ServiceType` = visit（參觀）/ inspection（驗屋）/ health_check（健檢）；批次各屬一種服務。`CHECKLIST_SERVICES=("inspection","health_check")`。參觀沒有清單、報告、提醒：`POST /bookings/{id}/checkin`（`Booking.checked_in_at`）＝完成。
- **檢查清單**：`inspection_categories.project_id` NULL＝公司範本；建案的清單以 `service_type` 分驗屋／健檢兩份（`ensure_project_checklist(db, project, service)`，舊資料由 `migrate_checklist_services` 補成 inspection）；建案建立時兩份都 `copy_template_to_project`；已有結果的檢查點不能刪只能停用；驗屋畫面保留「已停用但有結果」的點（也保留舊健檢預約在驗屋清單上的結果）。
- **售服七步驟 / 時間軸**：1 新建案 → 2 預約參觀 → 3 預約驗屋 → 4 驗屋 → 5 生產履歷＋住屋手冊 → 6 預約健檢 → 7 健檢。`services/timeline.build_timeline`（用 `dashboard.collect_phases`）算每步 done/active/todo：全部住戶完成，或日期已過且沒有已預約未完成；`GET /projects/timeline`（須在 `/projects/{project_id}` 之前宣告）與 `/projects/{id}/timeline`。APP `components/Timeline.tsx`（標籤上下交錯）＋`lib/timeline.ts`（純計算）。第 5 步＝住屋手冊：全部住戶已寄送＝完成。
- **住屋手冊（步驟 5）**（`services/handbook.py`、`routers/handbook.py`）：建案一份範本 `handbook_sections/fields`（欄位可設建案共用 `default_value`、必填；建案建立時與第一次使用時 `ensure_template` 複製 `DEFAULT_TEMPLATE`＝第 2 版：只有住屋手冊的保固、聯絡資訊，全部選填；`Project.handbook_template_version` 記版本，`migrate_template` 啟動時把第 1 版升級一次）；每戶 `handbook_values` 覆蓋共用值；必填都有內容才能 Review OK。`UnitHandbook` 狀態 draft → approved（鎖定該戶內容與 PDF）→ sent；approved／sent 都可取消確認回 draft。外部 PDF `handbook_attachments`（`unit_id` NULL＝建案共用），合併順序：系統頁 → 共用 → 單戶，各組可上下移。「匯出檔案並寄送至售服」＝合併後 PDF 當附件寄到售服信箱（`settings.service_mailbox`＝MAIL_FROM，可改收件人；>20MB 拒寄），存 `storage/handbooks/`。單戶頁與 PDF 順序：生產履歷紀錄 → 住屋手冊欄位 → 外部 PDF。下載 kind：handbook、handbook_attachment。生產履歷紀錄 `handbook_entries`＋`handbook_photos`（日期＋多張照片＋選填文字，PDF 依日期排在欄位後面，下載 kind handbook_photo）。APP：`project/[id]/{handbooks,handbook-template,handbook/[unitId]/{index,entry}}`、`components/HandbookAttachments.tsx`。
- **預約頁封面照片**：`Project.{visit,inspection,health_check}_cover_path`（驗屋＝預售屋、健檢＝成屋、參觀選填）；`POST/DELETE /projects/{id}/covers/{service}`；APP 用下載 token（kind=project_cover）；屋主頁 `cover_url` → `/api/public/book/{token}/cover?v=檔名`。影像共用 `inspection_media.save_image`。
- **儀表板 / 報表**：`services/dashboard.build_dashboard` 是唯一數字來源（APP 儀表板、HTML、xlsx 共用）；住戶在每個階段的狀態互斥：completed > booked > invited > not_invited。色票經 dataviz 驗證，APP `charts.tsx` 與 `project_report.py` 同一組。
- **Excel 匯出匯入**（`/sheets/{name}/export-link`、`/sheets/{name}/import?dry_run=`；name = projects/checklist/slots/bookings/users/results）：`services/sheets.py` 框架（Col 型別轉換、說明工作表、CSV BOM、Big5）；每種資料在 `sheet_datasets.py` 定義 export_rows/apply/權限/範圍（global、project_service、batch）。規則：關鍵欄位比對、檔案沒有的不刪、任何錯誤整份 rollback、**匯出後原封不動匯回必須零變動**（測試涵蓋全部 xlsx+csv）。住戶仍用較早的 `units_excel.py`。預約匯入不寄信，寫入後才檢查名額；結果匯入只在 inspection in_progress 時能改。
- **Email**：`SMTP_HOST` 空白時寫入 `storage/outbox/*.eml`（`python -m scripts.show_outbox` 查看）；寄信放 BackgroundTasks、失敗只記 log。屋主在預約網頁預約／改期／取消（三種服務）另寄「【副本】」給 `BOOKING_NOTIFY_TO`（空白＝MAIL_FROM，`none` 不寄；`queue_booking_email(notify_staff=True)`，管理端取消不寄副本）。
- **排程**：APScheduler（Asia/Taipei），`REMINDER_HOUR`(9) 提醒、`BACKUP_HOUR`(3):30 備份；`run.py` 一個程序兩個 app 共用 lifespan → `start_scheduler` 有旗標只啟動一次。測試設 `SCHEDULER_ENABLED=false`。
- **PDF**：ReportLab + pypdf，字型 `contract_font()`（`PDF_FONT_PATH` → backend/fonts/*.ttf → Windows 標楷體 kaiu.ttf → MSung-Light）。報告用 platypus、`wordWrap='CJK'`；`_p()` 會跳脫 `<>`，要用顏色標記時直接用 `Paragraph`。
- **照片**：EXIF 轉正、長邊 1600、JPEG；簽名由 APP 傳筆畫座標，後端 Pillow 3 倍繪製後縮小成透明 PNG。

- **配色主題**（`lib/theme.ts`）：暗夜墨綠（預設）／亮色，「我的帳號」切換、每台裝置各自記住（web localStorage `ui.theme`、手機 `Paths.document/ui-theme.txt`）。StyleSheet 在載入時就固定顏色 → 啟動時**同步**讀主題，切換後重新載入（web reload；手機開發版 DevSettings.reload，正式版請使用者重開）。**畫面一律用 `colors.*` 色票，不要寫死色碼**（簽名板用 `colors.signPad`：暗色＝深底淺綠筆跡；已存的簽名圖片固定白底）；儀表板 `ChartCard` 預設顯示表格；圖表色 `colors.chart`（暗色那組已用 dataviz 驗證，底色 #14231e）。`public/index.html` 預設暗色底，亮色由內嵌 script 先換掉避免閃爍。
- **建案頁七步驟**：`StepGroup`＝左邊直式長方形（編號＋直書標題＋狀態：完成實心、進行中外框、未開始灰底），右邊是該步驟的各列；步驟 1 標題為「開案資訊」。長方形內容絕對定位、高度跟右邊方塊對齊，字放不下時依高度縮小。
- **建案備份檔**（`services/project_backup.py`）：`POST /projects/{id}/backup-link`（下載 kind project_backup）→ zip＝manifest.json＋data.json（`SCOPE` 依外鍵順序列出建案底下所有資料表）＋users.json（人員以手機號碼對應）＋files/（所有 *path 欄位的檔案）。`POST /projects/import` 一律建立新建案：重新編號並換外鍵、同名加「（還原）」、檔案放 storage/restored/、檢查清單 code 換成新建案編號、預約 token 沒衝突就沿用（屋主舊連結還能用）。不含：釘選、依建案指定的人員權限。**新增資料表時若屬於建案，要加進 `SCOPE`**（測試 test_step15 會比對）。刪除建案不再擋有預約的（先刪 bookings 再刪建案，避免時段 RESTRICT）。APP：建案列表往左滑「備份／刪除」，右上「匯入匯出」→「從建案備份檔還原」。
- **建案釘選／排序**：`project_pins`、`project_orders`（每人各自）；`GET /projects` 排序＝釘選的在前，各群組內依自己拖曳的 position（沒排過的在群組最前），再依釘選時間、建立時間；`PUT /projects/order`（畫面上由上到下的 id）；釘選／取消釘選時清掉該建案的 position（排到新群組最上面）。
- **ActionSheet** 選項區可捲動（批次設定選單有 9 項，手機放不下曾導致「刪除」點不到）。

## APP 端的坑（都踩過）

- **expo/fetch 是手機上的全域 fetch**，不支援 RN 舊式 `{uri,name,type}` FormData → 手機上傳用 `expo-file-system` 的 `new File(uri).upload(...)`（`lib/files.ts uploadFile`）；網頁用瀏覽器 `File`。
- 路由型別（typedRoutes）在 `expo start` 時產生；新增路由後 tsc 報 Href 錯誤 → 跑一次 `CI=1 timeout 60 npx expo start --port 8099` 或使用者的 Metro 會自動更新。
- 非路由程式不要放在 `src/app/`（不要從 route 檔 export 常數，放 `src/lib`）。
- iOS：關閉 Modal 後立刻開另一個 Modal/Alert 會失敗 → ActionSheet 選項延遲 400ms 執行。標題列半透明 → ScrollView/FlatList 加 `contentInsetAdjustmentBehavior="automatic"`。
- Modal 裡的錯誤要顯示在 Modal 內（顯示在後面頁面會被擋住）。
- **網頁版開新分頁（下載／預覽）**：iPhone Safari 只允許點擊當下 `window.open`，先 await 再開會被擋（電腦 Chrome 不會）→ 一律用 `lib/download.ts openLink(async () => url)`，並在 onPress 第一個 await 前呼叫；ActionSheet 在非 iOS 直接執行選項（不 setTimeout）。
- 網頁版：需要 `react-native-web`；datetimepicker 沒網頁版 → `pickers.tsx` 用 `createElement('input', {type:'date'})`；`Alert` 改 `window.confirm/prompt`。
- RN 0.88：`StyleSheet.absoluteFillObject` 不存在，用 `absoluteFill`。
- **左右滑（SwipeRow）**：只用 PanResponder＋Animated（沒有 gesture-handler 直接相依）。外層要用 `onMoveShouldSetPanResponderCapture` 才搶得過裡面的 Pressable；網頁版滑鼠的 `gestureState.dx` 與放開時座標不可靠 → 自己用 pageX 算、放開用最後位置；網頁版滑鼠拖曳放開後裡面的 Pressable 仍會 onPress → 外層忽略 onOpenChange 後 400ms 內的點擊。測試觸控用 CDP `Input.dispatchTouchEvent`。
- 主機位址：`normalizeBaseUrl` 容忍全形、空白、多餘路徑；Expo Go 由 `Constants.expoConfig.hostUri` 預填；網頁版由後端提供時**一律覆蓋**成目前網址（含 https 協定），不沿用 localStorage 舊值（舊版存錯 http 造成外網連不上）。後端回 `/app` 的 index.html 帶 `Cache-Control: no-cache`。

## 使用者環境（Windows + WSL2 Ubuntu-24.04）

- WSL **mirrored 網路**；區網 IP `192.168.68.109`、Tailscale `100.76.33.111`（機器名 laptop-agv125d3）；對外固定網址用 Tailscale Funnel（網址在 `.env` 的 PUBLIC_BASE_URL；Funnel 轉發到 8001）→ `python run.py` 即可，不需 `--tunnel`。
- **管理 APP 對外（方案 A，使用者選定）**：`run.py` 啟動時 `ensure_admin_funnel` 用 Tailscale Funnel 把 8000 開到 `https://<機器>.ts.net:8443`（`ADMIN_FUNNEL_PORT`，0 關閉；`--bg` 保存，但曾被不明原因重設 → `keep_admin_funnel` 每分鐘檢查補回），手機不必裝 Tailscale，用網頁版 `/app`。WSL 內呼叫 `/mnt/c/Program Files/Tailscale/tailscale.exe`。443 Funnel → 8001（公開頁）不要動。
- 外網保護（`services/network.py`）：有轉發標頭（X-Forwarded-For、Tailscale-Funnel-Request…）或非私有 IP ＝ 外網 → `/docs` `/openapi.json` `/init-db` `/db/status` `/auth/setup` 回 404；登入另有每 IP 15 分鐘 20 次失敗上限（IP 取本機轉發的 X-Forwarded-For）；密碼規則 `schemas.password_problem`（≥8、含英文與數字）。
- 從本機測 Funnel 會被 MagicDNS 導回自己（connection refused）→ 用 dns.google 查公開 IP 再 `curl --resolve` 走真正外網路徑；測試用 port 10000 暫開，測完 `funnel --https=10000 off`。
- 改了後端程式後要重新啟動 `run.py`（沒有自動重載）；APP 遇到後端沒有的 API（FastAPI 英文 `Not Found`）會顯示「後端版本較舊…請重新啟動」。
- 改了 APP 程式後要 `npm run build:web`，否則 /app 還是舊版（曾因舊版把 https 主機改成 http 而連不上）。iPhone 主畫面網頁版會記住加入時的網址。Expo Go 開發仍需區網或手機 Tailscale（8081 不經 Funnel）。
- **Windows 自己連 192.168.68.109 會逾時**（mirrored 限制）→ 電腦上一律用 `localhost`。
- 防火牆 8000、8081 已開（Windows + Hyper-V 兩道）。
- `run.py` 啟動前 `prepare_environment()` 自動補環境：沒有 `.venv` 就建立、requirements.txt 雜湊變了就 pip install、沒有 `.env` 就從 example 複製、沒有 `webapp/` 就 npm ci + build:web（找 nvm 的 npm，避開 /mnt/c）；接著改用旁邊的 `.venv`（`use_project_venv` re-exec），使用者不想在 `.bashrc` 寫死路徑。`~/.bashrc` 結尾 activate 的是另一個專案的 `~/stock/.venv`。venv activate 必須在 nvm 之後，否則再 activate 時 PATH 被還原 → 跑到 Windows 版 npm（`/mnt/c/Program Files/nodejs`）。症狀：UNC 路徑錯誤、ENOTEMPTY。急救：`source ~/.nvm/nvm.sh`。
- cloudflared 在 `~/.local/bin`；Expo 帳號 `service.hopo`，EAS projectId 在 `mobile/app.json`。
- Windows PowerShell 5.1 讀 UTF-8 無 BOM 的 .ps1 會亂碼 → .ps1 存成 UTF-8 BOM。
- 自動模式下下載/執行外部二進位檔會被權限擋 → 給使用者指令自行執行。

## 驗證方式（我自己測試時）

- 後端：pytest；需要真實流程時用 scratchpad 的暫存 DB 起 uvicorn（`APP_ENV_FILE=/nonexistent DATABASE_URL=sqlite:///<tmp> STORAGE_DIR=<tmp> ADMIN_INIT_KEY=k JWT_SECRET_FILE=<tmp> SCHEDULER_ENABLED=false`），**不要動使用者的 `backend/data/inspection.db`**。
- APP 的 API 呼叫：node 直接 `import mobile/src/lib/api.ts` 打暫存後端。
- 畫面：`npx expo export --platform web --output-dir <scratch>`（**不要**輸出到 backend/webapp，使用者的後端正在用）→ 用小 python 包裝把 `app.main.WEBAPP_DIR` 指到 scratch 再起 uvicorn，或小型 SPA 靜態伺服器 → scratchpad 裡裝的 `puppeteer-core` + `/usr/bin/google-chrome` headless，localStorage 預設 `server.host`、`auth.token`、`auth.user`。headless 下 `Linking.openURL` 不會觸發 targetcreated → 改寫 `window.open` 記下網址；檔案選擇用 `page.waitForFileChooser()`，`window.confirm` 用 `page.on('dialog')`。
- PDF：`pypdfium2`（scratchpad venv）轉圖片後目視檢查。
- 手機原生行為（相機、手指簽名、iOS 分享/Modal）無法在這裡測 → 明確告知使用者需實機確認。
