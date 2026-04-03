# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V2.0 - 提示詞轉移_詢問模型防崩潰版)
# 職責：處理 mission_reverse 任務，具備最高韌性梯隊與報告溯源功能。
# 特色：終極防拒絕梯隊 (-001固定版)、報告內建模型名稱溯源。
# ---------------------------------------------------------
import os, time, random, base64, requests, gc # 引入核心工具
from datetime import datetime, timezone # 處理時間戳
from supabase import create_client # 資料庫連線工具
from prompt_templates import build_prompt

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
# =========================================================
# 🧠 AI 火控中心 (V1.9 絕對防禦版：無縫模型切換)
# =========================================================
def call_gemini_with_fallback(s, r2_path, prompt):
    """執行 AI 請求，遇到滿載則等待，遇到崩潰則秒切下一個模型"""
    models = [
        "gemini-flash-lite-latest",  # 順位 1：最不易拒絕 (通訊兵)
        "gemini-flash-latest",       # 順位 2：最強英聽 (主力部隊)
        "gemini-2.5-flash",          # 順位 3：穩定備援
        "gemini-3-flash-preview",    # 順位 4：尖端備援 (最易被限制)
        "gemini-2.0-flash-lite-001"  # 💥 順位 5：終極防禦 (老將死守)
    ]
    # 避震時間：0分, 2分, 4分 (單一模型最多糾纏 6 分鐘，防止 GHA 超時)
    wait_times = [0, 120, 240] 
    
    url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"
    
    try:
        print(f"📡 [目標鎖定] 準備下載音檔: {url}") 
        raw_bytes = requests.get(url, timeout=120).content 
        b64_audio = base64.b64encode(raw_bytes).decode('utf-8') 
        del raw_bytes; gc.collect() 
    except Exception as e:
        return None, f"音檔下載失敗: {str(e)}", None 
    
    for model in models:
        print(f"📡 [DEEP_RETHINK] 嘗試使用模型: {model}") 
        
        # 針對單一模型進行最多 3 次嘗試
        for wait in wait_times:
            if wait > 0:
                print(f"⏳ [避震防禦] {model} 滿載，原地等待 {wait//60} 分鐘...") 
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
                    return res_json['candidates'][0]['content']['parts'][0].get('text', ""), "SUCCESS", model 
                
                elif resp.status_code == 429:
                    print(f"⚠️ [能量耗盡] {model} 觸發 429 流量管制。") 
                    continue # 💡 遇到 429：繼續內層迴圈，進入下一個 wait 時間
                
                else:
                    print(f"❌ [系統異常] {model} 報錯 {resp.status_code}，放棄此模型。") 
                    break # 💡 重大修正：遇到 404/500 等死錯，跳出 wait 迴圈，立刻換下一個 model！
            
            except Exception as e:
                print(f"💥 [通訊中斷] {model} 請求崩潰 ({str(e)})，放棄此模型。") 
                break # 💡 重大修正：遇到 Timeout 斷線，跳出 wait 迴圈，立刻換下一個 model！
                
    # 五個模型全部陣亡才會走到這一步
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
    print(f"🚀 [TIME_ASSASSIN] V2.0 產線啟動，動態提示詞引擎已掛載...") 
    
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

            t_id = task['id']; q_id = task.get('task_id')
            # 取得原始指令 (例如："/A", "古巴經濟 /b" 等)
            raw_command = task.get('target_prompt', '').strip() 
            
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
            
            # ⚡ 動態提示詞解析 (呼叫外部軍火庫)
            # 將使用者在 TG 群組輸入的字串交給解析器，產生最終版軍令
            actual_prompt = build_prompt(raw_command)
            
            # ⚡ 將「組裝完成的長篇提示詞」餵給 AI，並接收三變數回傳
            final_text, status_code, used_model = call_gemini_with_fallback(s, r2_path, actual_prompt) 
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": final_text, "email_sent": True}).eq("id", t_id).execute() 
                # ⚡ 傳遞模型名稱與「原始指令(raw_command)」給發報站
                send_rethink_report(s, title, final_text, used_model, raw_command) 
                print(f"🎉 任務 {t_id[:8]} 完成！負責模型：{used_model}") 
            else:
                sb.table("mission_reverse").update({"status": "failed_rate_limit", "error_log": status_code}).eq("id", t_id).execute() 
                print(f"🚨 任務 {t_id[:8]} 失敗: {status_code}") 

            gc.collect() 

    except Exception as e:
        print(f"💥 [核心潰敗] 程序中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
