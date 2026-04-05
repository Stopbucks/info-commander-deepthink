# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V2.7 - M&M逆向分析、過境壓縮與脈絡對齊版)
# 職責：處理 mission_reverse 任務，具備最高韌性梯隊與報告溯源功能。
# 特色：本機極速 Opus 壓縮、大質量防禦、Emoji 淨化補救與 TG 異常通報。
# 修改：導入本機 ffmpeg 壓縮並針對人聲極致優化，修正長文本認知提示詞。
# ---------------------------------------------------------
# 修改：導入透明容量標籤，TG 戰報將明確標示音檔來源大小，防禦流量盲區。
# ---------------------------------------------------------
import os, time, random, base64, requests, gc # 引入核心工具
import re # 用於正規表達式處理 Emoji
import subprocess, tempfile # 💡 用於本機執行 FFmpeg 過境壓縮
from datetime import datetime, timezone # 處理時間戳
from supabase import create_client # 資料庫連線工具
from prompt_templates import build_prompt
from mission_janitor import run_janitor # 💡 匯入戰場清道夫模組

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
# 🛠️ 輔助工具
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
# 🧠 AI 火控中心 (V2.0 過境壓縮防禦版)
# =========================================================
def call_gemini_with_fallback(s, r2_path, prompt):
    """執行 AI 請求，遇到非 Opus 檔案則自動執行本機極速壓縮"""
    models = [
        "gemini-flash-lite-latest",  
        "gemini-flash-latest",       
        "gemini-2.5-flash",          
        "gemini-3-flash-preview",    
        "gemini-2.0-flash-lite-001"  
    ]
    wait_times = [0, 120, 240] 
    
    url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"
    
    try:
        print(f"📡 [目標鎖定] 準備下載音檔: {url}") 
        raw_bytes = requests.get(url, timeout=120).content 
        
        # 💡 核心防禦：過境壓縮機制 (專為純英語人聲優化)
        if not url.lower().endswith('.opus'):
            print(f"🗜️ [過境壓縮] 啟動 GHA 本機 FFmpeg 人聲極致降噪壓縮...")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".raw") as tmp_raw:
                tmp_raw.write(raw_bytes)
                tmp_raw_path = tmp_raw.name
            
            tmp_opus_path = tmp_raw_path + ".opus"
            
            try:
                # 🎙️ 殺手級參數：-application voip 專注語音清晰度
                subprocess.run(['ffmpeg', '-y', '-i', tmp_raw_path, 
                                '-ar', '16000', '-ac', '1', 
                                '-c:a', 'libopus', '-b:a', '24k', '-application', 'voip', 
                                tmp_opus_path], 
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                with open(tmp_opus_path, 'rb') as f:
                    b64_audio = base64.b64encode(f.read()).decode('utf-8')
                print("✅ [過境壓縮] 人聲提煉完畢！準備發送至 AI。")
            except Exception as e:
                print(f"❌ 本機壓縮失敗: {e}")
                return None, f"本機壓縮失敗: {str(e)}", None
            finally:
                if os.path.exists(tmp_raw_path): os.remove(tmp_raw_path)
                if os.path.exists(tmp_opus_path): os.remove(tmp_opus_path)
                del raw_bytes; gc.collect()
        else:
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
# 🎙️ 通訊發報站 (報告封裝空投 - 透明容量標籤版)
# =========================================================
# 💡 修改：新增 audio_size 參數
def send_rethink_report(s, title, result, used_model, original_command, listen_url, is_downgraded=False, audio_size=0):
    """將翻譯結果、模型名稱、原始指令與聆聽連結封裝為 TXT 檔案"""
    safe_title = str(title).replace("*", "") 
    try:
        url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
        
        # 💡 新增：組合音檔大小的警告或提示標籤
        size_label = f"({audio_size}MB)" if audio_size else "(大小未知)"
        if audio_size > 25:
            size_label += " ⚠️" # 大於 25MB 視為大檔，附上警告圖示
        
        caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n🤖 *模型：{used_model}*\n⚙️ *指令：{original_command}*\n🎧 *音檔：* [點擊聽證 {size_label}]({listen_url})"
        if is_downgraded:
            caption_msg += "\n⚠️ *狀態：觸發巨集認知防禦 (因應超長時數節目)*"
        
        file_content = f"📌 主題：{safe_title}\n🤖 負責模型：{used_model}\n⚙️ 原始指令：{original_command}\n🎧 聆聽連結：{listen_url} {size_label}\n"
        
        if is_downgraded:
            file_content += "⚠️ 系統防禦紀錄：系統偵測此音檔長度極長。已自動啟動巨集認知防禦，指示 AI 放棄瑣碎雜訊，將最高算力集中於核心指示。\n"
            
        file_content += f"\n====================\n\n{result}" 
        
        files = {'document': (f"深度戰報_{safe_title[:15]}.txt", file_content.encode('utf-8'))}
        data = {'chat_id': s["TG_CHAT"], 'caption': caption_msg, 'parse_mode': 'Markdown'}
        
        print(f"📨 [通訊站] 準備空投至 TG Chat ID: {s['TG_CHAT']}")
        
        # 執行第一次發送 (帶 Markdown)
        resp = requests.post(url_doc, data=data, files=files, timeout=30) 
        
        # 💡 除錯核心：攔截 Telegram 的真實臉色
        if resp.status_code == 200:
            print("✅ [通訊站] TG 戰報發送成功！")
        else:
            # 🚨 這裡會印出 Telegram 為什麼不收的真正原因！
            print(f"⚠️ [通訊站] TG 拒絕接收 (HTTP {resp.status_code})！詳細錯誤：{resp.text}")
            
            # 啟動降級重試：拔除 Markdown 解析，以純文字硬發
            print("🔄 [通訊站] 啟動降級防禦：拔除 Markdown 格式重試中...")
            data['parse_mode'] = None 
            
            # 重新封裝檔案 (避免檔案指標跑到尾端導致空檔案)
            files_fallback = {'document': (f"深度戰報_{safe_title[:15]}.txt", file_content.encode('utf-8'))}
            resp_fallback = requests.post(url_doc, data=data, files=files_fallback, timeout=30)
            
            if resp_fallback.status_code == 200:
                print("✅ [通訊站] 降級純文字發送成功！")
            else:
                print(f"❌ [通訊站] 終極發送失敗！詳細錯誤：{resp_fallback.text}")
                
    except Exception as e:
        print(f"💥 [通訊站] 程式執行崩潰: {e}")
# =========================================================
# 🚀 任務總部署 (Mission Entry)
# =========================================================
def run_rethink_mission():
    """主程序：掃描 pending 任務並執行 AI 轉譯"""
    start_time = time.time() 
    print(f"🚀 [TIME_ASSASSIN] V2.7 產線啟動，透明容量標籤與動態壓縮已掛載...") 
    
    start_jitter = random.uniform(2.0, 6.0) 
    print(f"🎲 [DB Jitter] 啟動冷卻 {start_jitter:.1f} 秒...")
    time.sleep(start_jitter)

    sb = get_sb(); s = get_secrets() 
    
    try:
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
                if not q_id:
                    print("❌ 無法取得任務 ID，發送 TG 警告。")
                    send_tg_notice(s, f"⚠️ *系統告警：情報溯源失敗*\n長官，指令 (`{original_user_command}`) 無法在資料庫中找到對應的母檔案。\n*可能原因*：標題含有特殊符號，導致比對失敗。任務已終止。")
                    sb.table("mission_reverse").update({"status": "rejected", "error_log": "標題失聯 (q_id 缺失)"}).eq("id", t_id).execute()
                    continue

            q_res = sb.table("mission_queue").select("episode_title, r2_url, audio_size_mb").eq("id", q_id).single().execute()
            q_data = q_res.data or {}
            r2_path = str(q_data.get('r2_url') or '')
            audio_size = q_data.get('audio_size_mb') or 0
            title = q_data.get('episode_title', '未知主題') 
            
            listen_url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"

            # 💡 關鍵放行：允許 MP3 與 M4A 進入產線，交由火控中心本機壓縮
            valid_exts = ('.opus', '.mp3', '.m4a')
            if not r2_path.lower().endswith(valid_exts) or audio_size > 600:
                reject_msg = f"規格不符: 檔案過大或類型異常 ({audio_size}MB, {r2_path})"
                print(f"🚫 [系統攔截] 任務 {t_id[:8]} 被拒絕 - {reject_msg}")
                sb.table("mission_reverse").update({"status": "rejected", "error_log": reject_msg}).eq("id", t_id).execute()
                continue

            sb.table("mission_reverse").update({"status": "processing"}).eq("id", t_id).execute() 
            
            # ==========================================
            # 🛡️ 雙層檢視：超長時數音檔動態脈絡注入 (對接 V4.0 雙劍流)
            # ==========================================
            is_downgraded = False
            
            actual_prompt = build_prompt(raw_command)
            
            # 💡 邏輯對齊：用檔案大小推測節目長度，並調整給 AI 的認知脈絡
            if audio_size > 75:
                print(f"⚠️ [長文本防禦] 偵測到馬拉松級節目 ({audio_size}MB)，動態注入認知授權...")
                is_downgraded = True 
                
                # 重新設計的提示詞，強調「內容長度」而非物理大小
                giant_file_injection = "\n\n[⚠️ 系統前置導航：超長文本認知防禦]\n系統偵測此音檔內容極長、資訊密度極高。您現在的任務是「第二波深度逆向工程」。無須擔心遺漏全局的瑣碎細節（因第一線部隊已完成基礎掃描）。請將 100% 的算力高度集中於長官指示的戰略核心與結構化要求，針對無關段落請堅決略過或無情壓縮，以防輸出截斷！"
                
                actual_prompt += giant_file_injection
            
            final_text, status_code, used_model = call_gemini_with_fallback(s, r2_path, actual_prompt) 
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": final_text, "email_sent": True}).eq("id", t_id).execute() 
                # 💡 修改：將 audio_size 傳遞給通訊發報站
                send_rethink_report(s, title, final_text, used_model, original_user_command, listen_url, is_downgraded, audio_size) 
                print(f"🎉 任務 {t_id[:8]} 完成！負責模型：{used_model}") 
            else:
                sb.table("mission_reverse").update({"status": "failed_rate_limit", "error_log": status_code}).eq("id", t_id).execute() 
                print(f"🚨 任務 {t_id[:8]} 失敗: {status_code}") 

            gc.collect() 

        
        # 💡 新增：所有轉譯任務處理完畢後，派清道夫打掃戰場 (預設 60 天)
        # 若未來想改成 15 天，只需改成 run_janitor(sb, days_to_keep=15) 即可，主程式依舊乾淨！
        run_janitor(sb)

    except Exception as e:
        print(f"💥 [核心潰敗] 程序中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
