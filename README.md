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
cd ~/stock/nature/nature/backend && source .venv/bin/activate && python run.py
```

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
```

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

1. 「主機位址」輸入 `run.py` 印出的位址：Wi-Fi 填 `192.168.68.109:8000`，5G 填 `100.76.33.111:8000`（可以省略 `http://`）。
2. 「管理金鑰」輸入 `backend/.env` 裡的 `ADMIN_INIT_KEY`。
3. 按「**連線測試**」，顯示綠色「連線成功」即可。
4. 第一次使用時按「**初始化資料庫**」，會建立所有資料表並寫入預設檢查項目。重複按也安全，不會清掉資料。
5. 按「**資料庫狀態**」可以查看各資料表的筆數。

設定會儲存在手機上，下次開啟 APP 會自動帶入。

---

## 疑難排解

| 狀況 | 原因 / 解法 |
|---|---|
| `New-NetFirewallRule : 存取被拒` | PowerShell 沒有用系統管理員身分開啟，見第 3 節 |
| `run.py` 印出 `172.x.x.x` | mirrored 模式沒有生效：檢查 `.wslconfig` 檔名與內容，並執行 `wsl --shutdown` |
| 電腦瀏覽器打得開 `/docs`，但手機連不到 | ① 防火牆兩道規則都要建立（第 3 節）② 手機和電腦要在同一個 Wi-Fi ③ 網路設定檔要是「私人網路」 |
| 手機 5G 連不到 | 正常現象，見第 6 節 |
| APP 顯示「金鑰錯誤 (403)」 | APP 的管理金鑰和 `backend/.env` 的 `ADMIN_INIT_KEY` 不一致；改了 `.env` 要重新啟動 `run.py` |
| APP 顯示「連線逾時」 | 後端沒有在執行，或 IP 已經改變，請重新看 `run.py` 印出的位址 |
| Windows 10 不支援 mirrored | 系統管理員 PowerShell 執行：`netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<WSL IP>`（WSL IP 用 `hostname -I` 查詢，每次重開機可能改變） |
