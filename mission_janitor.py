# ---------------------------------------------------------
# 程式碼：mission_janitor.py (V1.0 戰場清道夫)
# 職責：定期清理 mission_reverse 中過期的舊任務，保持資料庫輕量。
# 特色：獨立模組、安全隔離、可自訂保留天數。
# ---------------------------------------------------------
from datetime import datetime, timezone, timedelta

def run_janitor(sb, days_to_keep=30):
    """
    自動清理過期的已結案任務。
    :param sb: Supabase 客戶端實例
    :param days_to_keep: 保留天數，預設 30 天 (可於主程式呼叫時修改)
    """
    try:
        # 計算過期臨界點的 ISO 格式時間戳記
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()
        
        # 💡 一鍵無情殲滅：只刪除狀態為 completed, rejected, not_found，且早於設定天數的紀錄
        result = sb.table("mission_reverse").delete() \
                   .in_("status", ["completed", "rejected", "not_found"]) \
                   .lt("created_at", cutoff_date).execute()
          
        # 獲取刪除的筆數 (Supabase SDK 若刪除成功，data 內會包含被刪除的資料)
        deleted_count = len(result.data) if result.data else 0
        
        if deleted_count > 0:
            print(f"🧹 [清道夫] 戰場打掃完畢，共清除 {deleted_count} 筆超過 {days_to_keep} 天之舊紀錄。")
    except Exception as e:
        print(f"⚠️ [清道夫] 清理作業異常 (不影響主產線): {e}")
