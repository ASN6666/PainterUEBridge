# Substance Painter → Unreal Engine 5 Live Sync（0.3.1，軸向修正，Painter 2022）

0.3.1 修正 Painter OBJ 的 Y-up 模型在 UE Z-up 場景中側躺的問題。明確關閉 FBX 場景軸向推測，指定匯入 Roll +90°。修正烘入 Static Mesh 資產，不修改場景 Actor 的位置、旋轉或縮放。模型前方方向由來源幾何決定，本版不推測角色朝向。

從 0.3.0 更新只需關閉 UE、覆蓋 `Plugins/PainterUEBridge` 後重開。在 Painter 關閉再勾選 **UE5 Live Sync**，會強制發送一次目前狀態。接收端會對尚無軸向標記的 `SM_PainterModel` 重新匯入一次並重新套好材質，保留資產路徑與場景引用；後續繪製不會反覆旋轉。若你先前手动旋轉 Actor 補償側躺，請還原該補償旋轉，避免修正兩次。重匯入可能覆寫你手動編輯過的模型幾何／碰撞匯入設定。

首次同步會透過 Painter 2022 的 `alg.project.exportMesh()` 將 `.spp` 內的模型匯出為 OBJ，UE 自動匯入為 **SM_PainterModel** 並套用同步材質。包含 JadeToad 等內嵌模型的範例專案。之後繪製更新沿用同一個 Static Mesh，不會每一筆重建幾何。

升級 0.3.0：關閉 UE、停用 Painter 外掛，覆蓋兩端外掛後重啟。在 Painter 重新勾選 **UE5 Live Sync**，等首次同步完成，在 UE **Content → PainterSync → 專案子資料夾** 找到 **SM_PainterModel**，拖進場景。材質已自動套好，不需要再找原始 FBX 或逐一拖曳材質。現有 0.2.x 貼圖資產可沿用。

模型匯入為合併的靜態模型，沒有骨架／動畫。依原始材質槽名稱匹配貼圖集，無法唯一匹配時會報錯，不以槽順序猜測。單槽模型配單一貼圖集時可自動配對。已有 `SM_PainterModel` 時不自動替換幾何；此版本處理首次模型傳送與後續貼圖更新，不包含持續模型拓撲同步。模型不會自動放進關卡。`Sync/meshes` 保留模型匯出來源，不隨貼圖快照清理。

0.3.0 驗證：22 項離線測試通過；UE 5.8.1 實際 OBJ 匯入、材質自動指定與第二次同步測試通過，退出碼 0。測試有 SSL 環境與測試三角形缺少 smoothing groups 的警告。Painter 模型匯出依安裝隨附 API 核對，尚未在 Painter 內實際執行。

0.2.2 修正 UE 匯入／儲存期間 Slate 回呼重入，導致同一筆工作被重複處理與 `.ready.json` 改名失敗的問題。更新 UE 外掛後重啟編輯器即可；Painter 端與 0.2.1 相同。`PainterSync` 資料夾會在第一次成功匯入時才建立，外掛啟用本身不會建立空資料夾。

已依本機 Steam 版 **Substance 3D Painter 2022／8.3.1** 隨附 Python API 0.2.9 文件與模組核對：Python 3.9、PySide2、`TextureStateEvent`、`project.is_busy()` 與匯出虛擬貼圖名稱。0.2.1 修正先前 AO 匯出欄位，改用 `AO_Mixed`，可包含烘焙與繪製的 AO，並在匯出前拒絕 UDIM 專案。這是 API 相容性核對，尚未完成 Painter 內實際畫筆驗收；較早的 2022 小版本也未逐一測試。

啟用 **File → UE5 Live Sync** 後，Painter 的貼圖變更事件會自動排程匯出，UE 編輯器自動匯入貼圖並更新材質。畫完一筆後不用按匯出，也不用每次儲存 `.spp`。這是貼圖匯出／匯入式的單向近即時同步。

預設最後一次貼圖事件後等待 0.6 秒，再於 Painter 非忙碌時匯出；UE 每 0.25 秒檢查工作。以上是排程設定，**不是保證 0.85 秒內顯示完成**，總延遲還包含貼圖計算、PNG 匯出、UE 匯入／壓縮／儲存。連續繪製時合併變更，停筆後更新最新狀態。高解析度／多貼圖集可能卡頓，本版每次會匯出完整貼圖集。

Painter 2022 的事件本身也有節流時間（API 設定下限 500ms）；外掛不修改其全域設定。**UE5 sync status…** 會顯示目前 Python／Qt 與實際事件節流間隔，總延遲需另外包含此間隔。

## 安裝

1. 在 Painter 選 **Python → Plugins Folder**，將 `Painter/painter_ue_sync.py` 複製到該資料夾。在 **Python** 選單啟用 `painter_ue_sync`。需要支援 Python 的 Substance 3D Painter，並提供 `substance_painter.event.TextureStateEvent` 與 `substance_painter.project.is_busy()`；介面相容 PySide2／PySide6。實際 Painter 版本仍待驗證。
2. 將 `Unreal/PainterUEBridge` 整個資料夾複製到目標 UE 專案的 `Plugins` 資料夾。
3. 在 UE 的 Plugins 啟用 **Painter UE Bridge**，允許啟用 Python Editor Script Plugin 與 Editor Scripting Utilities，重新啟動編輯器。這個外掛不需要編譯 C++，只在編輯器運作。
4. 預設共用資料夾是 `D:/UnrealPlugins/PainterUEBridge/Sync`；UE 目的地為 `/Game/PainterSync`。Painter 的 **File → UE5 sync folder…** 可改資料夾；修改後，在 UE Output Log 切換至 **Python**，執行下列命令，讓兩端使用相同路徑。

```python
import painter_ue_bridge; painter_ue_bridge.configure("D:/UnrealPlugins/PainterUEBridge/Sync", "/Game/PainterSync")
```

UE 設定會存到該專案的 `Saved/PainterUEBridge.json`。同一同步資料夾一次只供一個 UE 專案消費，避免兩個編輯器搶同一工作。

從 0.1.0／0.2.0 升級：先停用 Painter 外掛，覆蓋 Python 檔；關閉 UE 後覆蓋 UE 外掛資料夾，再啟動兩端。既有設定、資產名稱與材質實例相容。Painter 2022 的安裝位置以 **Python → Plugins Folder** 開啟的資料夾為準，避免裝入另一個 Painter 年份版本。

## 使用

1. 開啟並儲存 Painter `.spp` 專案。使用一般非 UDIM、非 layered material 的 Metallic/Roughness 貼圖集，先烘焙 Ambient Occlusion mesh map。
2. 勾選 **File → UE5 Live Sync**，會排程首次同步。此開關每次重新載入 Painter 外掛需重新啟用；後續每一筆不用點選任何按鈕。使用目前貼圖集解析度，匯出 8-bit PNG：BaseColor、DirectX Normal、ORM（R=AO、G=Roughness、B=Metallic）。UE Output Log 出現 `Painter UE Bridge synced` 才表示接收完成。
3. 在 UE `/Game/PainterSync` 找到專案子資料夾中的 `SM_PainterModel`，將它拖進場景，材質已自動套好。`MI_*` 材質實例也會保留在同一資料夾。
4. 在 Painter 畫一筆，停筆後等待自動同步。既有貼圖會更新並儲存，模型繼續使用同一個材質實例；自動同步不會彈出成功對話框。
5. 取消勾選 **UE5 Live Sync** 可停止。**File → UE5 sync status…** 可查看發送端狀態；**Send textures to UE5** 保留手動強制匯出功能。

若 UE 在背景時更新緩慢，可在 UE **Editor Preferences** 搜尋 **Use Less CPU when in Background**，關閉該選項；Viewport 的 Realtime 也應啟用。本外掛不會代改編輯器偏好。

材質使用獨立的 BaseColor、Normal、ORM 參數；BaseColor 啟用 sRGB，Normal 使用法線壓縮，ORM 使用遮罩壓縮並關閉 sRGB。材質是 opaque/default lit，這版未接入透明度、放射色、高度或位移。不要以此版本傳送 UDIM／分層材質。

## 工作與錯誤

- `jobs/<id>` 保留每次匯出原圖，完成匯出後才原子發布 `<id>.ready.json`，UE 成功後改成 `.done.json`。
- 依序處理工作；錯誤會記錄 Output Log 並阻擋後續工作。修正原因後執行 `import painter_ue_bridge; painter_ue_bridge.retry()`。
- Live Sync 最多新增一個尚未接收的工作；UE 離線或匯入失敗時，Painter 保留待更新狀態，不會為每一筆繼續匯出。UE 接收完成後自動傳送最新畫面。若 Painter 在此之前關閉，記得儲存繪製內容，重開並啟用 Live Sync 可同步。
- Painter 匯出錯誤會自動關閉 Live Sync，原因顯示於狀態與 Python 輸出；修正後重新勾選開關。版本缺少所需 API 時不會假裝啟動成功。
- 匯出期间產生的同步事件會被忽略，避免遞迴匯出；內容雜湊相同時不會重複通知 UE。
- 匯入不是跨資產交易：中途失敗可能已有部分貼圖更新，重試會覆寫為該工作的完整輸出。
- `import painter_ue_bridge; painter_ue_bridge.stop()` 暫停；`painter_ue_bridge.start()` 重啟。
- 同步會自動儲存這個外掛所建立／更新的資產；請使用專用目的地，不要手動改動產生的主材質參數名稱。
- 專案路徑與貼圖集名稱決定資產識別。移動／另存 `.spp` 或改名貼圖集會建立另一組資產。
- Live Sync 在下一次成功匯出時清理自己產生的舊快照，每個 Painter 專案保留最近兩個已確認完成的快照與待接收工作。手動匯出、0.1.0 工作與失敗匯出不自動清理。不要移除目前 UE 引用的最新來源圖。

## 驗證

`Tests/test_protocol.py` 驗證工作資料、檔案路徑範圍與命名。`Tests/test_live_sync.py` 使用 Painter／Qt 替身驗證筆畫事件合併、離線接收端、錯誤暫停、無彈窗、重複內容、清理與關閉流程，以及 PySide2 載入、2022 匯出設定與 UDIM 拒絕，共 19 項離線測試通過。替身測試不能驗證 Painter 真正的事件發送時機。

`Tests/ue_smoke.py` 在隔離 UE 5.8.1 專案內驗證輪詢接收、真實貼圖匯入、材質建立、參數讀回與第二次更新。測試使用 NullRHI，不包含材質視覺檢查。完整 Painter → UE5 實機筆畫同步仍待使用者自行安裝後驗證。先前未找到 Painter 安裝；本次已在 Steam 資料夾找到 2022／8.3.1 並核對其隨附 API。

2026-09-08：0.2.0 UE 測試通過，程序退出碼 0，0 個錯誤；有 1 個環境 SSL 憑證存放區警告。測試專案使用自己的磁碟快取，已解決先前 0.1.0 測試的 Zen／DDC 啟動問題。

測試結果記錄於工作區 `Tests/ue_smoke_result.json` 與 `Tests/ue_smoke.log`；安裝包僅包含外掛與本說明。
