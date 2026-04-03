# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V1.8 時光刺客 - 終極觀測版)
# 職責：處理 mission_reverse 任務，具備最高韌性梯隊與報告溯源功能。
# 特色：終極防拒絕梯隊 (-001固定版)、報告內建模型名稱溯源。
# ---------------------------------------------------------
import os, time, random, base64, requests, gc # 引入核心工具
from datetime import datetime, timezone # 處理時間戳
from supabase import create_client # 資料庫連線工具

# =========================================================
# ⚙️ 初始化配置與連線
# =========================================================
def get_sb():
    """建立 Supabase 連線客戶端"""
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")) 

def get_secrets():
    """獲取系統機密設定，並清理網址末端"""
    return {
        "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"), 
        "R2_URL": (os.environ.get("R2_PUBLIC_URL") or "").rstrip('/'), 
        "TG_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"), 
        "TG_CHAT": os.environ.get("TELEGRAM_CHAT_ID") 
    }

# =========================================================
# 🧠 AI 火控中心 (最高韌性梯隊)
# =========================================================
def call_gemini_with_fallback(s, r2_path, prompt):
    """執行 AI 請求，並在成功時回傳立功的模型名稱"""
    models = [
        "gemini-flash-lite-latest",  # 順位 1：配額最高，輕量快速
        "gemini-flash-latest",       # 順位 2：當代主力，英聽極強
        "gemini-2.5-flash",          # 順位 3：次世代主力備援
        "gemini-3-flash-preview",    # 順位 4：尖端架構，預覽版備援
        "gemini-2.0-flash-lite-001"  # 💥 順位 5：終極防禦。固定舊版節點，避開全球 latest 資源搶奪，最不易被拒絕。
    ]
    wait_times = [0, 120, 240] 
    
    url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"
    
    try:
        print(f"📡 [目標鎖定] 準備下載音檔: {url}") 
        raw_bytes = requests.get(url, timeout=120).content 
        b64_audio = base64.b64encode(raw_bytes).decode('utf-8') 
        del raw_bytes; gc.collect() 
    except Exception as e:
        return None, f"音檔下載失敗: {str(e)}", None # 💡 新增 None 作為模型名稱回傳
    
    for model in models:
        print(f"📡 [DEEP_RETHINK] 嘗試使用模型: {model}") 
        for wait in wait_times:
            if wait > 0:
                print(f"⏳ [避震防禦] 原地等待 {wait//60} 分鐘...") 
                time.sleep(wait) 
            
            gemini_jitter = random.uniform(3.0, 10.0) 
            print(f"🎲 [Gemini Jitter] 戰術延遲 {gemini_jitter:.1f} 秒...")
            time.sleep(gemini_jitter)

            try:
                g_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={s['GEMINI_KEY']}" 
                payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "audio/ogg", "data": b64_audio}}]}]} 
                resp = requests.post(g_url, json=payload, timeout=300) 
                
                if resp.status_code == 200:
                    res_json = resp.json() 
                    # 💡 重大更新：成功時一併回傳模型名稱 (model)
                    return res_json['candidates'][0]['content']['parts'][0].get('text', ""), "SUCCESS", model 
                elif resp.status_code == 429:
                    print(f"⚠️ [能量耗盡] 429 流量管制中。") 
                    continue 
                else:
                    return None, f"API 報錯: {resp.status_code}", None 
            except Exception as e:
                return None, f"請求崩潰: {str(e)}", None 
                
    return None, "FAILED_ALL_MODELS", None 

# =========================================================
# 🎙️ 通訊發報站 (報告封裝空投)
# =========================================================
def send_rethink_report(s, title, result, used_model):
    """將翻譯結果與模型名稱封裝為 TXT 檔案"""
    safe_title = str(title).replace("*", "") 
    try:
        url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
        caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n🤖 *模型：{used_model}*"
        
        # 💡 重大更新：將模型名稱寫入純文字檔的第二行，確保日後溯源
        file_content = f"📌 主題：{safe_title}\n🤖 負責模型：{used_model}\n\n====================\n\n{result}" 
        
        files = {'document': (f"深度戰報_{safe_title[:15]}.txt", file_content.encode('utf-8'))}
        data = {'chat_id': s["TG_CHAT"], 'caption': caption_msg, 'parse_mode': 'Markdown'}
        requests.post(url_doc, data=data, files=files, timeout=30) 
    except Exception as e:
        print(f"⚠️ 發報失敗: {e}")

# =========================================================
# 🚀 任務總部署 (Mission Entry)
# =========================================================
def run_rethink_mission():
    """主程序：掃描 pending 任務並執行 AI 轉譯"""
    start_time = time.time() 
    print(f"🚀 [TIME_ASSASSIN] V1.8 產線啟動，最高韌性防禦陣型就緒...") 
    
    start_jitter = random.uniform(2.0, 6.0) 
    print(f"🎲 [DB Jitter] 啟動冷卻 {start_jitter:.1f} 秒...")
    time.sleep(start_jitter)

    sb = get_sb(); s = get_secrets() 
    
    try:
        res = sb.table("mission_reverse").select("*").in_("status", ["pending", "failed_rate_limit"]).limit(3).execute() 
        tasks = res.data or []
        
        if not tasks:
            print("🛌 目前無待處理議題。"); return

        for task in tasks:
            if time.time() - start_time > 7200: break 

            t_id = task['id']; q_id = task.get('task_id'); prompt = task.get('target_prompt', '請全文翻譯') 
            
            if not q_id:
                sb.table("mission_reverse").update({"status": "not_found", "error_log": "未提供任務 ID"}).eq("id", t_id).execute()
                continue

            q_res = sb.table("mission_queue").select("episode_title, r2_url, audio_size_mb").eq("id", q_id).single().execute()
            q_data = q_res.data or {}
            r2_path = str(q_data.get('r2_url') or '')
            audio_size = q_data.get('audio_size_mb') or 0
            title = q_data.get('episode_title', '未知主題') 

            if not r2_path.lower().endswith('.opus') or audio_size > 60:
                sb.table("mission_reverse").update({"status": "rejected", "error_log": f"規格不符: {audio_size}MB, {r2_path}"}).eq("id", t_id).execute()
                continue

            sb.table("mission_reverse").update({"status": "processing"}).eq("id", t_id).execute() 
            
            # ⚡ 接收三個變數：翻譯文本、狀態碼、使用的模型
            final_text, status_code, used_model = call_gemini_with_fallback(s, r2_path, prompt) 
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": final_text, "email_sent": True}).eq("id", t_id).execute() 
                # ⚡ 傳遞模型名稱給發報站
                send_rethink_report(s, title, final_text, used_model) 
                print(f"🎉 任務 {t_id[:8]} 完成！負責模型：{used_model}") 
            else:
                sb.table("mission_reverse").update({"status": "failed_rate_limit", "error_log": status_code}).eq("id", t_id).execute() 
                print(f"🚨 任務 {t_id[:8]} 失敗: {status_code}") 

            gc.collect() 

    except Exception as e:
        print(f"💥 [核心潰敗] 程序中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
