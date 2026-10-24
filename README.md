# 建案驗屋與健檢預約管理系統

```
┌────────────┐   Wi-Fi 區網 / Tailscale   ┌─────────────────────────────────────┐
│ 管理員手機  │ ─────────────────────────▶ │ 本地電腦（Windows + WSL2）           │
│ Expo APP   │   http://<IP>:8000         │  FastAPI (0.0.0.0:8000)             │
└────────────┘                            │   └─ SQLite  backend/data/inspection.db │
                                          └─────────────────────────────────────┘
```

| 資料夾 | 內容 |
|---|---|
| `backend/` | FastAPI 後端、資料庫 Schema、測試 |
| `mobile/` | 管理員手機 APP（Expo / React Native） |

---

## ⚡ 快速指令（日常使用）

> 首次安裝請先完成第 1～3 節；5G 連線需先完成第 6 節的 Tailscale 設定。

**終端機 ①：啟動後端**（Wi-Fi 與 5G 都一樣）

```bash
cd ~/stock/nature/nature/backend && source .venv/bin/activate && python run.py            # 只給自己用
cd ~/stock/nature/nature/backend && source .venv/bin/activate && python run.py --tunnel   # 外部的屋主 / 受託人也要能開簽名頁
```

已設定固定網址的 Tailscale Funnel（第 9 節方案 A）時，用 `python run.py` 即可，不需要 `--tunnel`。

**終端機 ②：啟動 APP 開發伺服器**（依手機目前的網路擇一）

| 手機網路 | 指令 | APP「主機位址」填 |
|---|---|---|
| **Wi-Fi**（與電腦同一個網路） | `cd ~/stock/nature/nature/mobile && npm run wifi` | `192.168.68.109:8000` |
| **5G / 4G**（手機需開啟 Tailscale） | `cd ~/stock/nature/nature/mobile && npm run 5g` | `100.76.33.111:8000` |

- 實際 IP 以 `run.py` 和 `npm run wifi / 5g` 啟動時印出的為準。
- 手機開 **Expo Go** 掃描終端機上的 QR code（iPhone 用內建相機掃）。
- 手機換網路後，要在終端機 ② 按 `Ctrl + C`，再用對應的指令重新啟動，然後重新掃 QR code。終端機 ① 的後端不用重啟。

**其他常用指令**

| 用途 | 指令 |
|---|---|
| 停止伺服器 | 在該終端機按 `Ctrl + C` |
| 電腦上看 API 文件 | 瀏覽器開 `http://127.0.0.1:8000/docs` |
| 手機瀏覽器測試連線 | Wi-Fi：`http://192.168.68.109:8000/health`　5G：`http://100.76.33.111:8000/health` |
| 後端測試 | `cd backend && source .venv/bin/activate && pytest -q` |
| 建立示範預約（測簽名流程） | `cd backend && source .venv/bin/activate && python -m scripts.create_demo_booking` |
| 產生屋主連結 | `cd backend && source .venv/bin/activate && python -m scripts.owner_link <預約編號>` |
| 重設管理者密碼（忘記密碼時） | `cd backend && source .venv/bin/activate && python -m scripts.reset_admin <手機號碼>` |
| 查看測試信件（未設定 SMTP 時） | `cd backend && source .venv/bin/activate && python -m scripts.show_outbox` |
| APP 測試 / 型別檢查 | `cd mobile && npm test && npm run typecheck` |
| 查 Tailscale IP | WSL：`ip -4 addr \| grep 'inet 100\.'`　Windows：`tailscale ip -4` |

---

## 1. 首次安裝後端

在 WSL 終端機執行：

```bash
cd ~/stock/nature/nature/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

編輯 `backend/.env`，**一定要改**這兩個值：

| 變數 | 用途 |
|---|---|
| `ADMIN_INIT_KEY` | APP 呼叫管理 API 時帶的金鑰，請改成隨機長字串 |
| `ID_HASH_SALT` | 身分證雜湊用的鹽值，**上線後不可再改**，否則舊資料比對不到 |

隨機字串可以用 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 產生。

---

## 2. WSL2 網路設定（只需做一次）

WSL2 預設使用 NAT，WSL 拿到的是 `172.x.x.x` 內部 IP，手機連不到。改成 **mirrored 模式**後，WSL 會直接共用 Windows 的區網 IP。

1. 建立檔案 `C:\Users\<你的帳號>\.wslconfig`（本機是 `C:\Users\b9211\.wslconfig`），內容：
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
   - 用記事本存檔時，「存檔類型」要選「所有檔案」，避免存成 `.wslconfig.txt`。
   - 也可在 WSL 內直接執行：`printf '[wsl2]\nnetworkingMode=mirrored\n' > /mnt/c/Users/b9211/.wslconfig`
2. 在 Windows PowerShell 執行 `wsl --shutdown`，再重新開啟 WSL / VS Code。
3. 需要 Windows 11 22H2 以上。Windows 10 請改用 `netsh interface portproxy`（見「疑難排解」）。

---

## 3. 開放防火牆（只需做一次）

> ⚠️ 必須用 **系統管理員身分** 開啟 PowerShell，否則會出現「存取被拒 / Windows System Error 5」。
>
> 開法：按 Windows 鍵 → 輸入 `PowerShell` → 右鍵「**以系統管理員身分執行**」→ 按「是」。
> 視窗標題會出現「系統管理員」，提示字元變成 `PS C:\WINDOWS\system32>`。

mirrored 模式下要開 **兩道** 防火牆：一般的 Windows 防火牆，以及 WSL 專用的 Hyper-V 防火牆。

| Port | 用途 |
|---|---|
| 8000 | 後端 API |
| 8081 | Expo 開發伺服器（手機用 Expo Go 載入 APP 時需要，正式打包後不需要） |

```powershell
# 1) Windows 防火牆
New-NetFirewallRule -DisplayName "Inspection API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
New-NetFirewallRule -DisplayName "Expo Metro 8081"     -Direction Inbound -Protocol TCP -LocalPort 8081 -Action Allow

# 2) WSL 的 Hyper-V 防火牆（VMCreatorId 是 WSL 固定值，照抄即可）
New-NetFirewallHyperVRule -Name "WSL-Inspection-8000" -DisplayName "WSL Inspection API 8000" -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8000
New-NetFirewallHyperVRule -Name "WSL-Expo-8081"       -DisplayName "WSL Expo Metro 8081"     -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8081
```

如果跑到某一行出現「已存在」的錯誤，代表之前已經建立過，可以略過。

**確認規則已建立：**

```powershell
Get-NetFirewallRule -DisplayName "Inspection API 8000","Expo Metro 8081" | Select DisplayName, Enabled
Get-NetFirewallHyperVRule -Name "WSL-Inspection-8000","WSL-Expo-8081" | Select Name, Enabled
```

**之後若要移除：**

```powershell
Remove-NetFirewallRule -DisplayName "Inspection API 8000","Expo Metro 8081"
Remove-NetFirewallHyperVRule -Name "WSL-Inspection-8000","WSL-Expo-8081"
```

另外請確認 Wi-Fi 的網路設定檔是「**私人網路**」：設定 → 網路和網際網路 → Wi-Fi → 點選目前的網路 → 網路設定檔類型。

---

## 4. 日常啟動後端

```bash
cd ~/stock/nature/nature/backend
source .venv/bin/activate
python run.py
```

啟動後會印出：

```
  本機 API 文件       ：http://127.0.0.1:8000/docs
  手機 APP（Wi-Fi）   ：http://192.168.68.109:8000
  手機 APP（5G）      ：http://100.76.33.111:8000
  對外公開頁面        ：未開啟（要給外部的人使用時改用 python run.py --tunnel）
```

使用 `python run.py --tunnel` 時，約 5～10 秒後會再顯示對外網址。

若 Tailscale 沒有連線，5G 那行會顯示「未偵測到 Tailscale」。

- 電腦瀏覽器打開 `http://127.0.0.1:8000/docs` 可以直接測試所有 API。
- 停止伺服器：在終端機按 `Ctrl + C`。
- 執行測試：`pytest -q`

---

## 5. 手機連線測試（同一個 Wi-Fi）

1. 手機連到和電腦**同一個 Wi-Fi**（訪客網路通常會隔離裝置，請避免使用）。
2. 手機瀏覽器打開 `http://192.168.68.109:8000/health`（IP 以 `run.py` 印出的為準）。
3. 看到 `{"status":"ok", ...}` 就代表連線成功。

> 電腦的區網 IP 可能因路由器重新分配而改變。建議在路由器的 DHCP 設定中，替這台電腦**保留固定 IP**。

---

## 6. 從外網（手機 4G / 5G 行動網路）連線

### 為什麼切到 5G 就連不到？

`192.168.x.x` 是家裡 / 公司路由器內部的**私有 IP**，只有在同一個區網內才有效。手機切到 5G 後走的是電信業者的網路，網際網路上找不到這個位址，所以一定連不到。這不是程式問題，需要另外建立連線通道。

### 方案比較

| 方案 | 適合對象 | 優點 | 缺點 |
|---|---|---|---|
| **Tailscale（建議）** | 管理員 APP | 免費、免設定路由器、加密、只有你登入的裝置連得到 | 每支手機都要安裝 Tailscale 並登入 |
| Cloudflare Tunnel | 屋主預約頁、受託人簽署連結（步驟三之後） | 任何人都能用網址開啟、自動 HTTPS | 服務會公開在網路上，需要嚴格的驗證機制 |
| 路由器 Port Forwarding | 不建議 | 不需要額外軟體 | 直接暴露電腦；許多 ISP 使用 CGNAT 根本做不到 |

管理員 APP 可以操作整個資料庫，**不應該公開在網際網路上**。建議用 Tailscale 建立私人網路。

### Tailscale 設定步驟

1. **電腦（Windows）**：到 <https://tailscale.com/download/windows> 下載安裝，並登入帳號（可用 Google 帳號）。
2. **手機**：在 App Store / Google Play 安裝「Tailscale」，用**同一個帳號**登入，並開啟連線開關。
3. **查詢電腦的 Tailscale IP**：在 Windows PowerShell（不需要管理員）執行：
   ```powershell
   tailscale ip -4
   ```
   會得到 `100.x.y.z` 這樣的位址。
4. 手機切到 5G，**保持 Tailscale 開啟**，瀏覽器打開 `http://100.x.y.z:8000/health` 測試。
5. 成功後，在 APP 的「主機位址」欄位填入 `http://100.x.y.z:8000`。

**如果第 4 步連不到**（mirrored 模式與 VPN 網卡偶爾不相容），改用 Tailscale 的轉發功能。在 Windows PowerShell 執行：

```powershell
tailscale serve --bg 8000
```

第一次執行時，它會提示你到 Tailscale 管理頁面開啟 HTTPS 憑證功能，照指示操作即可。完成後會顯示一個網址，例如 `https://laptop-agv125d3.xxxx.ts.net`，APP 的主機位址改填這個網址（不用加 `:8000`）。關閉轉發：`tailscale serve --https=443 off`。

> 用 Expo Go 開發時，手機也要能連到電腦的 8081 port。5G 環境下請用 `npm run 5g` 啟動 APP 開發伺服器，它會自動把 QR code 換成 Tailscale IP。

---

## 7. 手機 APP（Expo）

### 首次安裝

```bash
cd ~/stock/nature/nature/mobile
npm install
```

手機安裝 **Expo Go**（App Store / Google Play）。

### 啟動

```bash
cd ~/stock/nature/nature/mobile
npm run wifi     # 手機連 Wi-Fi 時
npm run 5g       # 手機走 5G / 4G（需開 Tailscale）時
```

- 兩個指令都會自動偵測正確的 IP 放進 QR code，並印出 APP 主機位址應填的值。
- 終端機會顯示 QR code。Android 用 Expo Go 掃描；iPhone 用內建相機掃描。
- iPhone 第一次開啟時會詢問「允許尋找區域網路上的裝置」，請選**允許**，否則連不到電腦。
- 如果 Expo Go 顯示 SDK 版本不相容，請到商店把 Expo Go 更新到最新版（本專案為 Expo SDK 58）。

### APP 操作流程

**第一次使用（只需一次）**

1. 開啟 APP 會看到「登入」畫面，點「**變更主機設定**」。
2. 「主機位址」輸入 `run.py` 印出的位址：Wi-Fi 填 `192.168.68.109:8000`，5G 填 `100.76.33.111:8000`（可以省略 `http://`）。
3. 「管理金鑰」輸入 `backend/.env` 裡的 `ADMIN_INIT_KEY`。
4. 按「**連線測試**」，顯示「連線成功」即可；資料庫還沒建立時再按「**初始化資料庫**」（重複按也安全，不會清掉資料）。
5. 回到登入畫面，點「**建立第一位管理者 →**」，輸入姓名、手機號碼、密碼。建立後會自動登入，這個帳號是**最高管理者**。

**之後每次使用**

- 用手機號碼 + 密碼登入。登入狀態會保留 30 天。
- 下方分頁：
  - **建案**：建案列表。
  - **人員**：只有具「人員與權限管理」權限的人看得到；可以新增人員、設定權限、重設密碼、停用帳號。
  - **我的帳號**：修改密碼、主機設定、登出。

**第一階段：建立建案資料**（「建案」分頁 → 右上角「＋ 新增」→ 點進建案）

| 功能 | 說明 |
|---|---|
| 建案基本資料 | 案名、電話、建案地址、社區經理；點右上角「編輯」修改或刪除 |
| 住戶資訊 | 戶別、棟別、樓層、地址、坪數、交屋日期、屋主姓名／電話／Email、備註。「＋ 新增」有三種方式：逐戶填寫、貼上戶別清單（每行一戶）、**依棟別與樓層自動產生**（例如 A～C 棟 × 2～15 樓 × 每層 1～4 號，可選 A-5F-1／A5-1／A棟5樓之1 格式，棟別與樓層會一併填入）。已存在的戶別自動略過；可搜尋戶別、屋主、電話 |
| 住戶 Excel／CSV 匯出與匯入 | 「住戶資訊」右上角選單 →「匯出 Excel（.xlsx）」或「匯出 CSV（純文字）」：會用手機瀏覽器開啟 5 分鐘有效的下載連結，在瀏覽器裡預覽、儲存或分享（沒有住戶時是空白範本）。改好後「從 Excel / CSV 匯入」（CSV 可用 UTF-8 或 Big5、逗號或 Tab 分隔）：以**戶別**比對，已存在的更新、新的新增，Excel 裡沒有的戶別不會被刪除；儲存格留白代表清空該欄。匯入前會先顯示「新增幾戶、更新幾戶」讓你確認；有錯誤時列出列號，整份都不寫入 |
| 健檢日期與時段 | 選日期區間與每天的開始、結束時間，自動產生 30 分鐘一格的時段，每格預設 3 組。可用「＋ 新增屏蔽區段」設定多組每天不開放的時間（例如午休 12:00–13:00），重疊的時段不會產生。點時段可關閉／開放或調整名額，也可整天關閉；右上角「設定」可追加日期、改名、停用、刪除 |
| 檢查項目清單 | 新建案自動帶入公司範本（窗戶、水電、其他）。點類別、項目、檢查點可新增、改名、停用、刪除；只影響這個建案。已有檢查紀錄的項目不能刪除，只能停用 |

已有預約的住戶、健檢日期、建案不能刪除，避免資料遺失。

**第二階段：寄送驗屋邀請、屋主線上預約**（建案 → 健檢日期與時段 → 點一組日期）

1. 右上角「設定 → 預約設定」：填預約說明（會出現在邀請信與預約頁）、開放與截止時間（可留空）。
2. 點「📨 寄送邀請／預約名單」→「寄送邀請給尚未寄送的住戶」：每戶會收到一封含**專屬預約連結**的 Email。
   - 沒有 Email 的住戶：點該戶 →「分享預約連結（LINE / 簡訊）」。
   - 屋主打電話來預約：點該戶 →「開啟預約頁（代為預約）」。
3. 屋主開啟連結 → 選日期與時段（每格最多 3 組，額滿的不能選）→ 確認聯絡資料 → 預約完成，系統自動寄**確認信**。之後可用同一個連結改期或取消，也都會寄通知信。
4. 名單頁可看每戶狀態：尚未寄送／已寄送（屋主是否開啟過）／已預約哪個時段；點時段格子也會顯示預約了哪些戶別。

> 屋主在外網開啟連結，需要對外網址（第 9 節，建議 Tailscale Funnel 固定網址）；真的寄出 Email 需要設定 SMTP（第 8 節），未設定時信件存在 `backend/storage/outbox/`。

**第三階段：驗屋**（下方「驗屋」分頁；需要「填寫檢查結果」權限才能編輯）

1. 「驗屋」分頁顯示當天所有建案的預約（可切換前一天／後一天），點一戶開始。
2. 每個檢查點按「✓ 合格／✗ 不合格／不適用」，會立即儲存；每個項目右上角「其餘全部合格」可一次完成。
3. 點檢查點名稱 →「備註／拍照」：寫備註、拍照或從相簿選照片（照片自動轉正並縮小）。最下方可加整體備註與整體照片。
4. 全部填完後按「完成檢查，請屋主簽名」：畫面列出不合格項目，屋主（或代理人）確認後在手機上簽名。
5. 簽名後檢查結果鎖定、預約標記為完成，屋主的預約頁也不能再改期。需要修改時按「重新開啟」（會清除簽名，需重新簽名）。

**第四階段：報告確認與寄送**（驗屋頁最下方「報告」區塊；需要「管理驗屋報告」權限）

```
屋主簽名 → Review OK（確認報告）→ 寄送給屋主
```

- **預覽報告 PDF**：簽名後隨時可按，瀏覽器開啟報告（基本資料、結果統計、不合格項目、完整檢查表、照片、屋主簽名）。
- **Review OK**：確認報告內容無誤。確認後不能再「重新開啟」修改；尚未寄出前可「取消確認」。
- **寄送報告給屋主**：寄出報告 PDF 與感謝信（收件人預設為預約時的 Email，可修改），之後可「重新寄送」。寄出的 PDF 留存在 `backend/storage/reports/`。

**外部報告 PDF**（驗屋頁「外部報告 PDF」區塊；代驗屋公司或其他單位提供的報告）

- 單一 PDF、30MB 以內。上傳成功後自動關閉該戶的「上傳開關」，避免重複上傳；需要換新版時按「開啟上傳開關」再上傳（取代舊檔）。
- 寄送驗屋報告時會一併附上外部報告。

**報告追蹤與自動提醒**

- 「報告完成」＝ 已上傳外部報告，或驗屋報告已寄送給屋主。
- 預約日後超過 7 天仍未完成的戶別，會出現在「驗屋」分頁上方的紅色提示 →「報告追蹤」頁。
- 系統**每天 09:00** 自動檢查，第 7 天、第 14 天各寄一封提醒信給內部人員（多戶合併成一封），同一階段不重複寄；電腦當天沒開，之後也會補寄。
- 收件人在 `.env` 設定 `REMINDER_TO=a@公司.com,b@公司.com`；未設定時寄到 `MAIL_FROM`。檢查時間可用 `REMINDER_HOUR` 調整。
- 「報告追蹤」頁可按「立即檢查並寄送提醒」。



| 權限 | 可以做什麼 |
|---|---|
| 建案 / 戶別管理 | 新增、修改建案與住戶資料 |
| 預約批次與頁面設定 | 設定健檢日期、時段、名額 |
| 檢視預約時間表 | 查看預約與授權書 |
| 新增 / 修改 / 取消預約 | 管理預約、產生屋主連結 |
| 填寫檢查結果 | 驗屋時填寫檢查項目、拍照 |
| 管理驗屋報告 | 確認並寄出報告 |
| 人員與權限管理 | 新增人員與設定權限 |

沒有任何權限的人員登入後仍可以**查看**建案資料。最高管理者擁有全部權限。

**忘記密碼**：請最高管理者在「人員」分頁重設；如果最高管理者自己忘記，在電腦上執行：

```bash
cd ~/stock/nature/nature/backend && source .venv/bin/activate && python -m scripts.reset_admin 0912345678
```

---

## 8. 線上授權（數位簽名 + PDF 授權書 + Email）

### 流程

```
管理員產生屋主專屬連結（python -m scripts.owner_link <預約編號>），用 LINE / 簡訊傳給屋主
屋主開啟 /authorize/{token}
  └─ 填受託人姓名、Email，手機上簽名 ──▶ 系統寄「簽署邀請」給受託人（連結 7 天有效）
受託人點信中連結 /sign/{token}
  └─ 確認內容、手機上簽名 ──▶ 系統把兩個簽名疊到合約範本 → 產生 PDF
                                └─ Email 寄給屋主與受託人（附 PDF）
```

| 網址 / API | 誰使用 | 說明 |
|---|---|---|
| `POST /bookings/{booking_id}/authorization-link` | 管理員 | 產生屋主專屬連結（30 天有效，重複產生沿用同一個） |
| `GET /authorize/{token}` | 屋主 | 簽名網頁 |
| `GET /sign/{token}` | 受託人 | 簽名網頁（Email 連結） |
| `GET /authorizations?booking_id=&status=` | 管理員 | 查詢授權書 |
| `GET /authorizations/{id}/pdf` | 管理員 | 下載授權書 PDF |
| `POST /authorizations/{id}/resend-invite` | 管理員 | 重寄邀請（舊連結失效，可救回已過期的邀請） |
| `POST /authorizations/{id}/cancel` | 管理員 | 取消未完成的授權 |

**屋主重新送出時，以最後一次為準**：屋主可以用同一個連結再填一次（例如受託人 Email 打錯、或想換受託人）。
- 先前的授權書一律作廢，**已經簽完的也一樣**，舊的受託人連結會顯示「已由屋主更新或取消」。
- 新的受託人會收到新的簽署邀請。
- 如果換了受託人，舊受託人會收到一封「先前邀請作廢」的通知信。
- 作廢的紀錄與 PDF 仍保留，可以用 `GET /authorizations?booking_id=` 查詢。

### 更新套件（從步驟二升級時要做一次）

```bash
cd ~/stock/nature/nature/backend && source .venv/bin/activate && pip install -r requirements.txt
```

### 在手機上試用

1. 啟動後端：`python run.py`
2. 另開終端機建立一筆示範預約：
   ```bash
   cd ~/stock/nature/nature/backend && source .venv/bin/activate
   python -m scripts.create_demo_booking                          # 不需身分證驗證
   python -m scripts.create_demo_booking --id-number A123456789   # 需要輸入身分證字號
   ```
   會印出「外網連結」與「區網連結」。外網連結需要先啟動通道（第 9 節）；只在自己手機測試時用區網連結即可
   （5G + Tailscale 時把網址中的 `192.168.68.109` 換成 `100.76.33.111`）。
3. 手機瀏覽器開啟連結，填資料並簽名送出。
4. 尚未設定 SMTP 時，信件不會真的寄出，而是存成檔案：`backend/storage/outbox/*.eml`。
   用以下指令顯示最新一封信的內容（.eml 內文經過編碼，用記事本打開看不懂）：
   ```bash
   python -m scripts.show_outbox
   ```
   把信中的 `/sign/...` 連結輸入手機瀏覽器，以受託人身分簽名。
5. 完成後：
   - PDF 在 `backend/storage/authorizations/AUTH-000001.pdf`
   - 也可以從 `http://127.0.0.1:8000/docs` 呼叫 `GET /authorizations/{id}/pdf` 下載
   - outbox 會多一封附有 PDF 的「授權書簽署完成」信

### 設定真的寄信（以 Gmail 為例）

1. Google 帳戶 → 安全性 → 開啟「兩步驟驗證」。
2. Google 帳戶搜尋「**應用程式密碼**」→ 建立一組（名稱隨意），會得到 16 碼密碼。
3. 編輯 `backend/.env`：
   ```ini
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=你的帳號@gmail.com
   SMTP_PASSWORD=16碼應用程式密碼（不含空格）
   MAIL_FROM=你的帳號@gmail.com
   ```
4. 重新啟動 `run.py`。寄信失敗不會影響簽署流程，錯誤會顯示在 `run.py` 的終端機。

Gmail 個人帳號每天約可寄 500 封；量大時改用公司郵件主機或 SendGrid 等服務，只要改上面的 SMTP 設定。

### 受託人在外網怎麼開連結？

啟動對外通道（第 9 節）後，屋主連結與 Email 中的受託人連結都會自動使用對外網址。
沒有啟動通道時，連結是區網位址（`192.168.68.109`），只有你自己的手機打得開。

### 換成自己的合約範本

- **字型**：預設使用 Windows 的標楷體（`C:\Windows\Fonts\kaiu.ttf`）。換電腦或想用其他字型時，把 `.ttf` 放到 `backend/fonts/`，或在 `.env` 設定 `PDF_FONT_PATH`。
- **合約內容**：條文在 `backend/app/services/pdf.py` 的 `CLAUSES`，簽名網頁會顯示同一份條文。
  ⚠️ 預設條文只是範例，正式使用前請請法務或律師審閱。
- **使用現成的 PDF 範本**：把一頁的 PDF 放到 `backend/storage/templates/authorization_template.pdf`，系統就會改用它當底圖。
  再依範本上的位置調整 `pdf.py` 中 `LAYOUT` 的座標（單位 pt，原點在左下角，A4 為 595 × 842）。

---

## 9. 對外公開頁面（讓外部的屋主、受託人開啟簽名頁）

外部的人用手機直接開啟簽名頁，不需要安裝任何東西。

### 安全設計

`run.py` 會同時啟動兩個伺服器：

| Port | 綁定 | 內容 | 誰連得到 |
|---|---|---|---|
| 8000 | 0.0.0.0 | 管理 API + 公開頁面 + `/docs` | 你的 Wi-Fi、Tailscale |
| 8001 | 127.0.0.1 | **只有**屋主 / 受託人簽名頁 | 只有本機，對外通道只轉發到這裡 |

對外通道只轉發 8001，所以外部**完全碰不到** `/init-db`、授權書下載等管理功能。
屋主連結使用隨機 token（例如 `/authorize/5Mc5JW8W…`），無法用流水號猜到其他戶的資料。

### 連結的組成

```
https://xxxx.trycloudflare.com/authorize/5Mc5JW8Wvm0w7iB88GzhKNim697hF71M
└──────── 對外網址（網域）────────┘└──────── 屋主專屬亂數，存在資料庫，30 天有效 ────────┘
```

亂數部分**不會**因為重新啟動而改變。會變的只有快速通道的網域，所以正式使用時請改用下面的固定網址。

### 三種方式比較

| | 快速通道（測試用） | **A. Tailscale Funnel（建議）** | B. Cloudflare 具名通道 |
|---|---|---|---|
| 網址 | `https://隨機字.trycloudflare.com` | `https://laptop-agv125d3.<你的 tailnet>.ts.net` | `https://sign.你的網域.com` |
| 重開後網址 | **會變** | 固定 | 固定 |
| 費用 | 免費 | 免費 | 網域約 US$10／年 |
| 需要 | cloudflared | 已安裝的 Tailscale | Cloudflare 帳號 + 自己的網域 |
| 啟動方式 | `python run.py --tunnel` | `python run.py`（Funnel 由 Windows 的 Tailscale 常駐） | `python run.py --tunnel` |

### 快速通道（測試用）

1. 安裝 cloudflared（只需一次）：
   ```bash
   mkdir -p ~/.local/bin
   curl -fL -o ~/.local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
   chmod +x ~/.local/bin/cloudflared
   ~/.local/bin/cloudflared --version
   ```
   `run.py` 會自動到 `~/.local/bin` 找 cloudflared，不需要設定 PATH。
2. 啟動後端 + 通道：`python run.py --tunnel`，等它顯示「✅ 對外網址」。
3. 另開終端機產生屋主連結：`python -m scripts.owner_link <預約編號>`

`Ctrl + C` 會同時關閉後端與通道。重開後網域會變，先前傳出去、還沒簽完的連結要重新執行 `owner_link` 再傳一次。

### 方案 A：Tailscale Funnel（固定網址，免費）

利用你已經安裝的 Tailscale，把 8001 開放到網際網路，網址固定不變。

1. 在 **Windows PowerShell**（不需要系統管理員）執行：
   ```powershell
   tailscale funnel --bg 8001
   ```
   第一次執行時會顯示一個網址，要你到 Tailscale 管理頁面開啟 **HTTPS** 與 **Funnel** 功能。照著網址開啟後，再執行一次同樣的指令。
2. 成功後會顯示固定網址，例如 `https://laptop-agv125d3.tail1234.ts.net`。也可以用 `tailscale funnel status` 查詢。
3. 編輯 `backend/.env`，加入：
   ```ini
   PUBLIC_BASE_URL=https://laptop-agv125d3.tail1234.ts.net
   ```
4. 重新啟動 `python run.py`（**不需要** `--tunnel`），第 4 行會顯示固定網址。
5. 手機關掉 Wi-Fi 與 Tailscale，用 5G 開啟該網址，看到「✅ 連線正常」就完成了。

- Funnel 會一直保持開啟，電腦重開機後也一樣（只要 Windows 的 Tailscale 有執行）。不用每次設定。
- 關閉 Funnel：`tailscale funnel --https=443 off`
- 如果之前用過第 6 節的 `tailscale serve --bg 8000`，它和 Funnel 都使用 443 port，請先用 `tailscale serve --https=443 off` 關掉。

### 方案 B：Cloudflare 具名通道（固定網址，使用自己的網域）

適合想讓客戶看到公司網域（例如 `https://sign.公司.com`）的情況。

1. 註冊 Cloudflare 帳號，並把網域加入 Cloudflare（可以直接在 Cloudflare 購買網域）。
2. Cloudflare 後台 → **Zero Trust** → Networks → **Tunnels** → Create a tunnel → 選 **Cloudflared** → 輸入名稱。
3. 頁面上的安裝指令中，`--token` 後面那一長串就是 token，複製下來（不用執行那段安裝指令）。
4. 在 **Public Hostname** 新增：
   - Subdomain：`sign`，Domain：你的網域
   - Service：`HTTP`，URL：`localhost:8001`
5. 編輯 `backend/.env`：
   ```ini
   CLOUDFLARE_TUNNEL_TOKEN=剛才複製的 token
   PUBLIC_BASE_URL=https://sign.你的網域.com
   ```
6. 以後都用 `python run.py --tunnel` 啟動。

### 注意事項

- 屋主連結 30 天有效、受託人邀請連結 7 天有效。
- 電腦關機或 `run.py` 停止時，外部無法開啟頁面（網址不變，開機後重新執行就恢復）。

---

## 疑難排解

| 狀況 | 原因 / 解法 |
|---|---|
| `New-NetFirewallRule : 存取被拒` | PowerShell 沒有用系統管理員身分開啟，見第 3 節 |
| `run.py` 印出 `172.x.x.x` | mirrored 模式沒有生效：檢查 `.wslconfig` 檔名與內容，並執行 `wsl --shutdown` |
| 電腦瀏覽器打得開 `/docs`，但手機連不到 | ① 防火牆兩道規則都要建立（第 3 節）② 手機和電腦要在同一個 Wi-Fi ③ 網路設定檔要是「私人網路」 |
| 手機 5G 連不到 | 正常現象，見第 6 節 |
| `npm` 出現 `ENOTEMPTY`、錯誤訊息裡有 `\\wsl.localhost\...` 或 `C:\Users\...` | 執行到 **Windows 版** npm 了。輸入 `which npm`：如果是 `/mnt/c/...`，執行 `source ~/.nvm/nvm.sh` 後再試。常見原因：`~/.bashrc` 裡 venv 的 `activate` 寫在 nvm **之前**，之後再啟動其他 venv 時 PATH 會被還原成沒有 nvm 的版本；把 `activate` 那行移到 nvm 設定之後即可（本機已修正）。`node_modules` 若已損壞：`rm -rf node_modules && npm ci` |
| APP 一直跳回登入畫面 | 密碼被重設、帳號被停用，或登入超過 30 天：重新登入即可 |
| APP 顯示「金鑰錯誤 (403)」 | APP 的管理金鑰和 `backend/.env` 的 `ADMIN_INIT_KEY` 不一致；改了 `.env` 要重新啟動 `run.py` |
| **電腦上的網頁版**（`http://localhost:8081`）顯示「連線逾時」 | WSL mirrored 模式下，Windows 用自己的區網 IP（192.168.x.x）連不到 WSL 裡的後端。電腦上的網頁版主機位址請填 **`localhost:8000`**；手機才用 192.168.x.x 或 Tailscale IP |
| APP 顯示「連線逾時」 | 後端沒有在執行，或 IP 已經改變，請重新看 `run.py` 印出的位址 |
| 授權書 PDF 中文變成方塊或空白 | 找不到繁中字型：把 `.ttf` 放到 `backend/fonts/`，或在 `.env` 設定 `PDF_FONT_PATH` |
| 沒收到簽署邀請信 | 未設定 SMTP 時信件在 `backend/storage/outbox/`；已設定時看 `run.py` 終端機的錯誤訊息，並檢查垃圾郵件匣 |
| 受託人打不開簽署連結 | 屋主簽名時沒有對外網址，連結是區網位址：設定對外網址（第 9 節）後，用 `POST /authorizations/{id}/resend-invite` 重寄 |
| `run.py` 顯示「Port 8000 已被占用」 | 另一個終端機的 `run.py` 還在執行：到那個終端機按 `Ctrl + C`；找不到的話用 `ss -ltnp \| grep 8000` 查 pid 後 `kill <pid>` |
| 通道顯示 `dial tcp 127.0.0.1:8001: connect: connection refused` | 8001 沒有在執行：確認 `run.py` 正在執行，或重新啟動它 |
| 外網連結打不開 | ① `run.py` 是否在執行 ② 快速通道重開過、網域已改變：重新執行 `owner_link` ③ 使用 Funnel 時，在 PowerShell 執行 `tailscale funnel status` 確認 |
| Windows 10 不支援 mirrored | 系統管理員 PowerShell 執行：`netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<WSL IP>`（WSL IP 用 `hostname -I` 查詢，每次重開機可能改變） |
