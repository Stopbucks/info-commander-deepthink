# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V1.2 時光刺客 - 雙軌空投版)
# 職責：處理 mission_reverse 任務，具備 3-6-9 避震、雙重 Jitter 與長文自動打包機制。
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
        "R2_URL": os.environ.get("R2_PUBLIC_URL").rstrip('/'), # 確保網址尾端無斜線
        "TG_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"), 
        "TG_CHAT": os.environ.get("TELEGRAM_CHAT_ID") 
    }

# =========================================================
# 🧠 AI 火控中心 (含避震、降檔與 Jitter)
# =========================================================
def call_gemini_with_fallback(s, r2_path, prompt):
    """執行 AI 請求，具備 API Jitter 與降檔備援"""
    models = ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"] # 設定降檔梯隊
    wait_times = [0, 180, 360, 540] # 設定 3, 6, 9 分鐘等待秒數
    
    url = f"{s['R2_URL']}/{r2_path}" # 組合 R2 下載網址
    m_type = "audio/ogg" # Opus 皆視為 ogg
    
    try:
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
            
            # 🛡️ [Gemini Jitter] 錯開與 T1/T2 主產線的併發衝突
            gemini_jitter = random.uniform(3.0, 10.0)
            print(f"🎲 [Gemini Jitter] 戰術延遲 {gemini_jitter:.1f} 秒，規避連線峰值...")
            time.sleep(gemini_jitter)

            try:
                g_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={s['GEMINI_KEY']}" 
                payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": m_type, "data": b64_audio}}]}]} 
                resp = requests.post(g_url, json=payload, timeout=300) # 發送請求 (給予5分鐘充裕時間)
                
                if resp.status_code == 200:
                    res_json = resp.json() 
                    return res_json['candidates'][0]['content']['parts'][0].get('text', ""), "SUCCESS" 
                elif resp.status_code == 429:
                    print(f"⚠️ [能量耗盡] 觸發 429 Rate Limit，準備下一輪避震。") 
                    continue 
                else:
                    print(f"❌ [系統異常] API 報錯: {resp.status_code}") 
                    break 
            except Exception as e:
                print(f"💥 [通訊中斷] 請求崩潰: {str(e)}") 
                break 
                
    return None, "FAILED_ALL_MODELS" 


# =========================================================
# 🎙️ 通訊發報站 (升級：1500字門檻，雙軌預覽與 TXT 空投機制)
# =========================================================
def send_rethink_report(s, title, result):
    """將翻譯結果寄送至 Telegram，超載則截斷預覽並空投全文檔案"""
    safe_title = str(title).replace("*", "") 
    
    try:
        # 🛡️ 視覺防線設定：小於等於 1500 字，全文舒適閱讀
        if len(result) <= 1500:
            report_msg = f"🔍 *【深度再思戰報】*\n📌 *主題：{safe_title}*\n\n{result}" 
            url = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendMessage" 
            payload = {"chat_id": s["TG_CHAT"], "text": report_msg, "parse_mode": "Markdown"} 
            requests.post(url, json=payload, timeout=15) 
        
        # 🛡️ 超載防禦設定：大於 1500 字，發送 1000 字預覽 + 附件空投
        else:
            # 1. 發送 1000 字預覽文字
            preview_text = result[:1000]
            notify_msg = f"🔍 *【深度再思：巨量情報預覽】*\n📌 *主題：{safe_title}*\n\n{preview_text}...\n\n*(⚠️ 報告指揮官，本情報總字數高達 {len(result)} 字。為保持版面簡潔，全文已自動打包為 .txt 檔案，請參閱下方附件！)*"
            url_msg = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendMessage"
            requests.post(url_msg, json={"chat_id": s["TG_CHAT"], "text": notify_msg, "parse_mode": "Markdown"}, timeout=15)
            
            # 2. 呼叫 TG sendDocument 動態生成純文字檔並傳送
            url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
            files = {'document': (f"深度戰報_{safe_title[:15]}.txt", result.encode('utf-8'))}
            data = {'chat_id': s["TG_CHAT"]}
            requests.post(url_doc, data=data, files=files, timeout=30)
            
    except Exception as e:
        print(f"⚠️ 發報失敗: {e}")
# =========================================================
# 🚀 任務總部署 (Mission Entry)
# =========================================================
def run_rethink_mission():
    """主程序：安全掃描、過濾、轉譯、結案"""
    start_time = time.time() # 記錄開機時間
    max_duration_seconds = 7200 # 🛡️ 安全斷電：2 小時 (7200 秒)

    print(f"🚀 [TIME_ASSASSIN] 深度再思產線啟動，最大生存時間: 2 小時...") 
    
    # 🛡️ [Supabase Jitter] 模擬啟動延遲，規避 Vercel/FLY 競合寫入
    start_jitter = random.uniform(2.0, 6.0)
    print(f"🎲 [DB Jitter] 啟動冷卻 {start_jitter:.1f} 秒...")
    time.sleep(start_jitter)

    sb = get_sb() 
    s = get_secrets() 
    
    try:
        # 1. 獨立查詢逆向任務表 (解除無 Foreign Key 的巢狀查詢地雷)
        res = sb.table("mission_reverse").select("*").in_("status", ["pending", "failed_rate_limit"]).limit(3).execute() 
        tasks = res.data or []
        
        if not tasks:
            print("🛌 目前無待處理之議題，產線轉入低耗能休眠。") 
            return

        for task in tasks:
            # ⏱️ 檢查是否達到斷電極限
            if time.time() - start_time > max_duration_seconds:
                print("⏱️ [安全斷電] 逼近 2 小時服役極限，強制優雅撤退！")
                break

            t_id = task['id'] 
            q_id = task.get('task_id')
            prompt = task.get('target_prompt', '請全文翻譯') 
            
            if not q_id:
                sb.table("mission_reverse").update({"status": "not_found", "error_log": "Vercel 未提供關聯 ID"}).eq("id", t_id).execute()
                continue

            # 2. 獨立查詢任務母表，獲取音檔情報
            q_res = sb.table("mission_queue").select("episode_title, r2_url, audio_size_mb").eq("id", q_id).single().execute()
            q_data = q_res.data or {}
            
            r2_path = str(q_data.get('r2_url') or '').lower()
            audio_size = q_data.get('audio_size_mb') or 0
            title = q_data.get('episode_title', '未知主題') 

            # 🛡️ 嚴格物資過濾：必須是 .opus 且小於 60MB
            if not r2_path.endswith('.opus') or audio_size > 60:
                print(f"⛔ [規格不符] 任務 {t_id[:8]} 音檔過大 ({audio_size}MB) 或非 Opus 格式，予以退回。")
                sb.table("mission_reverse").update({"status": "rejected", "error_log": f"檔案過大或格式錯誤: {audio_size}MB, {r2_path}"}).eq("id", t_id).execute()
                continue

            # 標記處理中，防重複領取
            sb.table("mission_reverse").update({"status": "processing"}).eq("id", t_id).execute() 
            
            # ⚡ 執行 AI 降檔轉譯產線
            final_text, status_code = call_gemini_with_fallback(s, r2_path, prompt) 
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": final_text, "email_sent": True}).eq("id", t_id).execute() 
                send_rethink_report(s, title, final_text) 
                print(f"🎉 任務 {t_id[:8]} 深度再思完成！") 
            else:
                sb.table("mission_reverse").update({"status": "failed_rate_limit", "error_log": "所有備援模型皆滿載"}).eq("id", t_id).execute() 
                print(f"🚨 任務 {t_id[:8]} 能量耗盡，等待明日補給。") 

            # 每次處理完手動觸發記憶體回收
            gc.collect()

    except Exception as e:
        print(f"💥 [核心潰敗] 程序中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
