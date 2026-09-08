# Substance Painter 2022 → Unreal Engine 5 自動同步使用說明

適用外掛：**Painter UE Bridge 0.3.1**  
已核對的 Painter 版本：**2022／8.3.1（Python 3.9、PySide2）**  
UE 接收端測試版本：**5.8.1**

## 下載

[下載 0.3.1 軸向修正版](../PainterUEBridge-0.3.1-AxisFix.zip)

## 功能

- 首次同步：從 Painter 專案匯出模型，UE 自動匯入成 `SM_PainterModel` 並套用材質。
- 後續繪製：Painter 停筆後自動匯出貼圖，UE 更新既有貼圖與材質，不需要每次手動匯出。
- 同步 Base Color、DirectX Normal、ORM（R＝AO、G＝Roughness、B＝Metallic）。
- 修正 Painter OBJ 的 Y-up 與 UE Z-up 軸向差異。
- 支援包含內嵌模型的 Painter 範例專案，例如 JadeToad。

這是單向、透過檔案匯出與匯入的近即時同步。最後一次貼圖變更事件後，外掛預設等待約 0.6 秒再匯出；總延遲還包含 Painter 事件節流、貼圖計算、匯出與 UE 匯入時間。高解析度、多材質模型可能需要更久。

## 一、安裝 Painter 外掛

1. 解壓縮外掛包。
2. 開啟 **Substance Painter 2022**。
3. 點選上方 **Python → Plugins Folder**。
4. 將解壓後的 `Painter/painter_ue_sync.py` 複製進剛開啟的資料夾。
5. 重新啟動 Painter，在 **Python** 選單啟用 `painter_ue_sync`。

請以 Painter 2022 自己開啟的 Plugins Folder 為準，避免安裝到另一個年份版本。

## 二、安裝 UE 外掛

1. 關閉 UE 編輯器。
2. 找到你的 `.uproject` 所在資料夾。
3. 若沒有 `Plugins`，建立該資料夾。
4. 將解壓後 `Unreal` 裡的 **PainterUEBridge 整個資料夾**複製進去。

正確結構：

```text
你的專案/
├─ 你的專案.uproject
└─ Plugins/
   └─ PainterUEBridge/
      ├─ PainterUEBridge.uplugin
      └─ Content/
         └─ Python/
            ├─ init_unreal.py
            ├─ painter_ue_bridge.py
            └─ bridge_protocol.py
```

5. 開啟 UE 專案，前往 **Edit → Plugins**。
6. 搜尋並啟用 **Painter UE Bridge**。
7. 若提示啟用 **Python Editor Script Plugin** 與 **Editor Scripting Utilities**，接受並重新啟動 UE。

## 三、第一次同步模型與材質

1. 在 Painter 開啟模型專案，先儲存一次 `.spp`。
2. 確認 UE 專案已開啟。
3. 在 Painter 勾選 **File → UE5 Live Sync**。
4. 等待首次模型與貼圖匯出、UE 匯入完成。
5. 在 UE 按 **Ctrl＋Space** 開啟 Content Browser。
6. 前往 **Content → PainterSync → 專案子資料夾**。
7. 找到 **SM_PainterModel**，將它拖進場景。
8. 模型已套好材質，儲存你的場景。

`PainterSync` 會在第一次成功匯入後才建立，僅啟用外掛不會產生空資料夾。

同一資料夾內也會有：

| 資產 | 用途 |
| --- | --- |
| `SM_PainterModel` | 匯入的靜態模型 |
| `M_PainterBridge` | 主材質 |
| `MI_...` | 各貼圖集對應的材質實例 |
| `T_..._BaseColor` | 顏色貼圖 |
| `T_..._Normal` | 法線貼圖 |
| `T_..._ORM` | AO、粗糙度、金屬度打包貼圖 |

## 四、繪製時自動更新

1. 保持 Painter 的 **UE5 Live Sync** 勾選。
2. 在 Painter 畫一筆，停筆後等待同步。
3. UE 中已套用同步材質的模型會更新。

後續不必再按匯出，也不必每一筆儲存 `.spp`。但繪製內容仍應自行儲存，避免關閉 Painter 時遺失。

連續繪製時會合併更新。UE 尚未接收上一筆工作時，Painter 會保留最新修改，等上一筆接收完成才再次匯出。

重新載入 Painter 外掛後，需要重新勾選 **UE5 Live Sync**。

### Painter 選單

| 選項 | 用途 |
| --- | --- |
| `UE5 Live Sync` | 啟用或停止自動同步 |
| `Send textures to UE5` | 手動強制傳送目前狀態 |
| `UE5 sync folder…` | 選擇共用同步資料夾 |
| `UE5 sync status…` | 查看發送端狀態、Python／Qt 版本與事件間隔 |

## 五、更新到 0.3.1，修正模型側躺

若已安裝 **0.3.0**：

1. 關閉 UE。
2. 用新版覆蓋專案內的 `Plugins/PainterUEBridge`。
3. 重新開啟 UE。
4. 在 Painter 將 **UE5 Live Sync** 取消勾選，再重新勾選。
5. 等待同步，新版會對未修正的既有模型重匯入一次。

**從 0.3.0 升級不需要更新 Painter 端。** 若原本是 0.2.x，請更新兩端，才能傳送模型。

軸向修正套用在 Static Mesh 資產，保留資產路徑、材質與場景引用，不會修改 Actor 的位置、旋轉或縮放。

如果你曾手動旋轉 Actor 補償側躺，請還原那次補償旋轉，避免修正兩次。重匯入可能覆寫手動修改的模型幾何或碰撞匯入設定。

## 六、同步資料夾設定

預設共用資料夾：

```text
D:/UnrealPlugins/PainterUEBridge/Sync
```

預設 UE 內容目的地：

```text
/Game/PainterSync
```

兩端使用預設值時不用另外設定。若要改路徑：

1. 在 Painter 點 **File → UE5 sync folder…** 選擇新資料夾。
2. 在 UE 開啟 **Output Log**，將輸入模式由 **Cmd** 切換成 **Python**。
3. 執行下列命令，將路徑換成你選擇的資料夾：

```python
import painter_ue_bridge; painter_ue_bridge.configure("D:/UnrealPlugins/PainterUEBridge/Sync", "/Game/PainterSync")
```

同一同步資料夾一次只提供給一個 UE 專案使用。

## 七、常見問題

### UE 找不到 PainterSync

1. 確認 **Painter UE Bridge** 已啟用，且 UE 已重啟完成。
2. 確認 Painter 已開啟、儲存專案並勾選 **UE5 Live Sync**。
3. 在 Content Browser 選取 **Content**，清除搜尋文字與篩選條件。
4. 查看 UE Output Log：

```text
Painter UE Bridge listening: ...
```

表示接收端已啟動。

```text
Painter UE Bridge synced: 專案名稱
```

表示該次同步成功。

### 有貼圖，但沒有模型

- 確認兩端至少已更新到 **0.3.0**。
- 重新勾選 Painter 的 **UE5 Live Sync**，觸發首次模型傳送。
- 模型資產名稱為 **SM_PainterModel**，需要自行拖進場景。

### UE 在背景時更新很慢

到 **Editor Preferences** 搜尋 **Use Less CPU when in Background** 並關閉；同時確認 Viewport 的 **Realtime** 已啟用。

### Painter 顯示等待 UE

確認 UE 已開啟、外掛已啟動，且兩端共用資料夾相同。若 UE 匯入報錯，先修正日誌中的原因，再於 UE 的 Python 輸入模式執行：

```python
import painter_ue_bridge; painter_ue_bridge.retry()
```

### Painter 自動同步開關自己關閉

匯出失敗時外掛會暫停。點 **UE5 sync status…** 查看原因，修正後重新勾選 **UE5 Live Sync**。

### 模型更新後仍然側躺

- 確認 UE 外掛已更新至 **0.3.1**，並重新同步過一次。
- 確認場景中使用的是同步資料夾內的 `SM_PainterModel`。
- 檢查 Actor 是否保留了先前手動加入的補償旋轉。

## 八、目前限制與驗證範圍

- 支援一般非 UDIM、非分層材質的 Metallic/Roughness 工作流程。
- 模型以 OBJ 傳送，匯入為合併的靜態模型，不包含骨架或動畫。
- 模型首次匯入後，不持續同步幾何／拓撲變更；0.3.1 的一次性軸向修正除外。
- 材質為 opaque/default lit，未接入透明度、放射色或位移。
- 材質槽會依名稱匹配，無法唯一匹配時會報錯。
- 同步會儲存外掛更新的資產；大型模型與高解析度貼圖可能造成短暫停頓。
- `Sync/meshes` 保留模型來源；不要任意刪除目前使用中的重匯入來源。
- UE 5.8.1 已通過軸向轉換、重匯入與連續同步測試；尚未完整驗證所有 Painter 2022 小版本及各種模型的視覺結果。
