
# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V1.5 時光刺客 - 極速 Flash 版)
# 職責：處理 mission_reverse 任務，優先調度 Flash 梯隊處理高品質音檔。
# 特色：1.5-Flash 先行、智慧 URL 修正、詳細錯誤日誌、長文打包空投。
# ---------------------------------------------------------
import os, time, random, base64, requests, gc # 引入標準與隨機工具庫
from datetime import datetime, timezone # 處理時區與時間
from supabase import create_client # 引入資料庫連線工具

# =========================================================
# ⚙️ 初始化配置與連線
# =========================================================
def get_sb():
    """建立 Supabase 連線客戶端"""
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")) 

def get_secrets():
    """獲取系統機密設定"""
    return {
        "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"), 
        "R2_URL": (os.environ.get("R2_PUBLIC_URL") or "").rstrip('/'), # 確保網址尾端無斜線
        "TG_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"), 
        "TG_CHAT": os.environ.get("TELEGRAM_CHAT_ID") 
    }

# =========================================================
# 🧠 AI 火控中心 (Flash 優先梯隊)
# =========================================================
def call_gemini_with_fallback(s, r2_path, prompt):
    """執行 AI 請求，優先使用 Flash 模型陣列"""
    # 🎯 依照指揮官指令排列：1.5-Flash -> 3-Flash-Preview -> 其他 Flash 與 Pro
    models = [
        "gemini-1.5-flash", 
        "gemini-3-flash-preview", 
        "gemini-2.5-flash", 
        "gemini-2.0-flash-001",
        "gemini-1.5-pro"
    ]
    wait_times = [0, 120, 240] # 設定避震延遲秒數
    
    # 🛡️ 智慧網址判定：防止網址重複拼接導致下載失敗
    url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"
    
    try:
        print(f"📡 [目標鎖定] 準備下載音檔: {url}") # 輸出目標網址
        raw_bytes = requests.get(url, timeout=120).content # 下載音檔至記憶體
        b64_audio = base64.b64encode(raw_bytes).decode('utf-8') # 轉為 Base64 格式
        del raw_bytes; gc.collect() # 立即釋放記憶體
    except Exception as e:
        return None, f"音檔下載失敗: {str(e)}" 
    
    for model in models:
        print(f"📡 [DEEP_RETHINK] 嘗試使用模型: {model}") 
        for wait in wait_times:
            if wait > 0:
                print(f"⏳ [避震防禦] 原地等待 {wait//60} 分鐘後重試...") 
                time.sleep(wait) 
            
            # 🛡️ [Gemini Jitter] 規避 API 併發峰值
            gemini_jitter = random.uniform(3.0, 10.0)
            print(f"🎲 [Gemini Jitter] 戰術延遲 {gemini_jitter:.1f} 秒...")
            time.sleep(gemini_jitter)

            try:
                g_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={s['GEMINI_KEY']}" 
                payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "audio/ogg", "data": b64_audio}}]}]} 
                resp = requests.post(g_url, json=payload, timeout=300) # 發送 AI 請求
                
                if resp.status_code == 200:
                    res_json = resp.json() 
                    return res_json['candidates'][0]['content']['parts'][0].get('text', ""), "SUCCESS" 
                elif resp.status_code == 429:
                    print(f"⚠️ [能量耗盡] 觸發 429 Rate Limit。") 
                    continue 
                else:
                    return None, f"API 報錯: {resp.status_code}" 
            except Exception as e:
                return None, f"請求崩潰: {str(e)}" 
                
    return None, "FAILED_ALL_MODELS" 

# =========================================================
# 🎙️ 通訊發報站 (一律空投 TXT 檔案)
# =========================================================
def send_rethink_report(s, title, result):
    """將翻譯結果打包為純文字檔案空投至 Telegram"""
    safe_title = str(title).replace("*", "") 
    try:
        url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
        caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n*(📝 報告指揮官，已完成高品質 Flash 轉譯任務。)*"
        file_content = f"📌 主題：{safe_title}\n\n====================\n\n{result}" # 檔案第一行含標題
        files = {'document': (f"深度戰報_{safe_title[:15]}.txt", file_content.encode('utf-8'))}
        data = {'chat_id': s["TG_CHAT"], 'caption': caption_msg, 'parse_mode': 'Markdown'}
        requests.post(url_doc, data=data, files=files, timeout=30) # 執行檔案空投
    except Exception as e:
        print(f"⚠️ 發報失敗: {e}")

# =========================================================
# 🚀 任務總部署 (Mission Entry)
# =========================================================
def run_rethink_mission():
    """主程序：安全掃描、過濾、轉譯、結案"""
    start_time = time.time() # 記錄開機時間
    print(f"🚀 [TIME_ASSASSIN] V1.5 產線啟動，優先使用 Flash 梯隊...") 
    
    start_jitter = random.uniform(2.0, 6.0) # 🛡️ [DB Jitter] 規避資料庫併發
    print(f"🎲 [DB Jitter] 啟動冷卻 {start_jitter:.1f} 秒...")
    time.sleep(start_jitter)

    sb = get_sb(); s = get_secrets() 
    
    try:
        # 1. 查詢待處理任務 (限額 3 筆)
        res = sb.table("mission_reverse").select("*").in_("status", ["pending", "failed_rate_limit"]).limit(3).execute() 
        tasks = res.data or []
        
        if not tasks:
            print("🛌 目前無待處理議題。"); return

        for task in tasks:
            if time.time() - start_time > 7200: break # 🛡️ 安全斷電

            t_id = task['id']; q_id = task.get('task_id'); prompt = task.get('target_prompt', '請全文翻譯') 
            
            if not q_id:
                sb.table("mission_reverse").update({"status": "not_found", "error_log": "未提供關聯 ID"}).eq("id", t_id).execute()
                continue

            # 2. 獲取任務細節
            q_res = sb.table("mission_queue").select("episode_title, r2_url, audio_size_mb").eq("id", q_id).single().execute()
            q_data = q_res.data or {}
            r2_path = str(q_data.get('r2_url') or '')
            audio_size = q_data.get('audio_size_mb') or 0
            title = q_data.get('episode_title', '未知主題') 

            # 🛡️ 規格過濾
            if not r2_path.lower().endswith('.opus') or audio_size > 60:
                sb.table("mission_reverse").update({"status": "rejected", "error_log": f"規格不符: {audio_size}MB, {r2_path}"}).eq("id", t_id).execute()
                continue

            sb.table("mission_reverse").update({"status": "processing"}).eq("id", t_id).execute() # 標記處理中
            
            # ⚡ 執行 AI 降檔轉譯
            final_text, status_code = call_gemini_with_fallback(s, r2_path, prompt) 
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": final_text, "email_sent": True}).eq("id", t_id).execute() 
                send_rethink_report(s, title, final_text) 
                print(f"🎉 任務 {t_id[:8]} 深度再思完成！") 
            else:
                # 💡 記錄真實錯誤碼，方便後續精準除錯
                sb.table("mission_reverse").update({"status": "failed_rate_limit", "error_log": status_code}).eq("id", t_id).execute() 
                print(f"🚨 任務 {t_id[:8]} 失敗: {status_code}") 

            gc.collect() # 回收資源

    except Exception as e:
        print(f"💥 [核心潰敗] 程序中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
