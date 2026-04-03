
# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V2.4 - 補救搜索雷達版)
# 職責：處理 mission_reverse 任務，具備最高韌性梯隊與報告溯源功能。
# 特色：終極防拒絕梯隊、大質量防禦、Emoji 淨化補救與 TG 異常通報。
# ---------------------------------------------------------
import os, time, random, base64, requests, gc # 引入核心工具
import re # 💡 新增：用於正規表達式處理 Emoji
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
# 🛠️ 輔助工具 (V2.4 新增)
# =========================================================
def clean_title_for_search(title):
    """移除 Emoji 與特殊字元，僅保留文字、數字與基本標點"""
    return re.sub(r'[^\w\s,.?\'"-]', '', title).strip()

def send_tg_notice(s, message):
    """發送純文字通知到 Telegram (用於異常告警)"""
    try:
        url = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendMessage"
        data = {"chat_id": s["TG_CHAT"], "text": message, "parse_mode": "Markdown"}
        requests.post(url, data=data, timeout=10)
    except: pass

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
                resp = requests.post(g_url, json=payload, timeout=900) 
                
                if resp.status_code == 200:
                    res_json = resp.json() 
                    return res_json['candidates'][0]['content']['parts'][0].get('text', ""), "SUCCESS", model 
                
                elif resp.status_code == 429:
                    print(f"⚠️ [能量耗盡] {model} 觸發 429 流量管制。") 
                    continue 
                
                else:
                    print(f"❌ [系統異常] {model} 報錯 {resp.status_code}，放棄此模型。") 
                    break 
            
            except Exception as e:
                print(f"💥 [通訊中斷] {model} 請求崩潰 ({str(e)})，放棄此模型。") 
                break 
                
    return None, "FAILED_ALL_MODELS", None

# =========================================================
# 🎙️ 通訊發報站 (報告封裝空投)
# =========================================================
def send_rethink_report(s, title, result, used_model, original_command, listen_url, is_downgraded=False):
    """將翻譯結果、模型名稱、原始指令與聆聽連結封裝為 TXT 檔案"""
    safe_title = str(title).replace("*", "") 
    try:
        url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
        
        caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n🤖 *模型：{used_model}*\n⚙️ *指令：{original_command}*\n🎧 *音檔：* [點擊聽證]({listen_url})"
        if is_downgraded:
            caption_msg += "\n⚠️ *狀態：巨獸檔案觸發防禦，已自動轉為降級鑽探模式 (/D)*"
        
        file_content = f"📌 主題：{safe_title}\n🤖 負責模型：{used_model}\n⚙️ 原始指令：{original_command}\n🎧 聆聽連結：{listen_url}\n"
        
        if is_downgraded:
            file_content += "⚠️ 系統防禦紀錄：因原始音檔過長(超過系統安全輸出上限)，已自動切換至 /D (降級鑽探) 模式，以最高算力集中於您的核心指示。\n"
            
        file_content += f"\n====================\n\n{result}" 
        
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
    print(f"🚀 [TIME_ASSASSIN] V2.4 產線啟動，補救雷達與降級路由已掛載...") 
    
    start_jitter = random.uniform(2.0, 6.0) 
    print(f"🎲 [DB Jitter] 啟動冷卻 {start_jitter:.1f} 秒...")
    time.sleep(start_jitter)

    sb = get_sb(); s = get_secrets() 
    
    try:
        # 💡 重大修正：允許抓取 not_found 的任務進行補救
        res = sb.table("mission_reverse").select("*").in_("status", ["pending", "failed_rate_limit", "not_found"]).limit(3).execute() 
        tasks = res.data or []
        
        if not tasks:
            print("🛌 目前無待處理議題。"); return

        for task in tasks:
            if time.time() - start_time > 7200: break 

            t_id = task['id']; q_id = task.get('task_id')
            raw_command = task.get('target_prompt', '').strip() 
            original_user_command = raw_command 
            
            # ==========================================
            # 🛡️ 補救搜索雷達 (處理 Emoji 導致的 not_found)
            # ==========================================
            if task.get('status') == "not_found" or not q_id:
                print(f"🕵️ 偵測到 {t_id[:8]} 狀態異常，嘗試補救...")
                
                # 若 Vercel 失敗，通常會在 error_log 或某處留有原始標題。
                # 這裡假設您的 Vercel 在失敗時，會把使用者觸發的 raw_command 留著。
                # 但 Vercel 當時找不到 q_id，我們 GHA 只能回報長官「任務失敗」。
                if not q_id:
                    print("❌ 無法取得任務 ID，發送 TG 警告。")
                    send_tg_notice(s, f"⚠️ *系統告警：情報溯源失敗*\n長官，您剛才下達的指令 (`{original_user_command}`) 無法在資料庫中找到對應的母檔案。\n\n*可能原因*：該情報標題含有 Emoji 等特殊符號，導致系統比對失敗。此任務已終止。")
                    sb.table("mission_reverse").update({"status": "rejected", "error_log": "無法補救的標題失聯 (q_id 缺失)"}).eq("id", t_id).execute()
                    continue

            # 如果 q_id 存在，繼續正常流程
            q_res = sb.table("mission_queue").select("episode_title, r2_url, audio_size_mb").eq("id", q_id).single().execute()
            q_data = q_res.data or {}
            r2_path = str(q_data.get('r2_url') or '')
            audio_size = q_data.get('audio_size_mb') or 0
            title = q_data.get('episode_title', '未知主題') 
            
            listen_url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"

            if not r2_path.lower().endswith('.opus') or audio_size > 600:
                sb.table("mission_reverse").update({"status": "rejected", "error_log": f"規格不符: {audio_size}MB, {r2_path}"}).eq("id", t_id).execute()
                continue

            sb.table("mission_reverse").update({"status": "processing"}).eq("id", t_id).execute() 
            
            # ==========================================
            # 🛡️ 大質量音檔防禦與智能路由
            # ==========================================
            is_downgraded = False
            final_command = raw_command
            
            if audio_size > 100:
                print(f"⚠️ [巨獸防禦] 偵測到大型音檔 ({audio_size}MB)，強制切換至 /D 降級鑽探模式...")
                is_downgraded = True
                clean_req = raw_command.upper().replace("/A", "").replace("/B", "").replace("/C", "").replace("/D", "").strip()
                final_command = f"/D {clean_req}"

            actual_prompt = build_prompt(final_command)
            
            # 💡 針對巨型檔案注入前置導航脈絡 (配合 V3.4 解除字數封印)
            if audio_size > 100:
                context_injection = f"\n\n[⚠️ 系統導航脈絡]\n此檔案原始大小達 {audio_size}MB。請跳過無關段落，將輸出算力 100% 集中於回覆長官的具體指示。在該指示範圍內，請給出極度詳盡的長篇幅翻譯與還原，無需擔憂長度，請盡情展開您的輸出額度。"
                actual_prompt += context_injection
            
            final_text, status_code, used_model = call_gemini_with_fallback(s, r2_path, actual_prompt) 
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": final_text, "email_sent": True}).eq("id", t_id).execute() 
                send_rethink_report(s, title, final_text, used_model, original_user_command, listen_url, is_downgraded) 
                print(f"🎉 任務 {t_id[:8]} 完成！負責模型：{used_model}") 
            else:
                sb.table("mission_reverse").update({"status": "failed_rate_limit", "error_log": status_code}).eq("id", t_id).execute() 
                print(f"🚨 任務 {t_id[:8]} 失敗: {status_code}") 

            gc.collect() 

    except Exception as e:
        print(f"💥 [核心潰敗] 程序中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
