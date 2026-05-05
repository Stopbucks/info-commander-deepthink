# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V4.1 重裝雙軌版)
# 職責：處理 mission_reverse 任務，跳過翻譯，直攻跨語言摘要。
# 特色：搭載 Llama 128K 與 Gemini 降級梯隊，透過控制面板自由切換。
# 更新：任務處理狀態校正，加入 while True: 迴圈
# ---------------------------------------------------------
import os, time, requests
import re
from datetime import datetime, timezone
from supabase import create_client
from openai import OpenAI 
from prompt_templates import build_prompt
from mission_janitor import run_janitor

# =========================================================
# 🎛️ 戰略控制面板 (Control Panel)
# =========================================================
class CONTROL_PANEL:
    # 目前正式上線： 啟用雙核 同時先讓NVIDIA 摘要後，換GEMINI 摘要 
    # 測試階段 1：設定 NVIDIA 為主攻手 (True)，Gemini 關閉 (False)
    # 測試階段 2：設定 NVIDIA 關閉 (False)，Gemini 啟動 (True)
    ENABLE_NVIDIA_LLAMA = True
    ENABLE_GEMINI_FALLBACK = True 
    
    # NVIDIA 要測試的模型陣列 (128K 巨胃怪獸)
    NVIDIA_MODELS = [
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-70b-instruct"
    ]
    
    # Gemini 降級梯隊 (當啟動 Gemini 時會依序輪詢)
    GEMINI_MODELS = [
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]

# =========================================================
# ⚙️ 初始化配置與連線
# =========================================================
def get_sb():
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")) 

def get_secrets():
    return {
        "NVIDIA_KEY": os.environ.get("NVIDIA_API_KEY"), 
        "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"),
        "HF_TOKEN": os.environ.get("HF_TOKEN"), 
        "R2_URL": (os.environ.get("R2_PUBLIC_URL") or "").rstrip('/'), 
        "TG_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"), 
        "TG_CHAT": os.environ.get("TELEGRAM_CHAT_ID") 
    }

def get_nvidia_client(api_key):
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

# =========================================================
# 🧠 AI 火控中心 (HF 提領 + 跨語言深思)
# =========================================================

def fetch_stt_from_huggingface(s, task_id, created_at_str):
    """[階段一] 從 Hugging Face 歸檔庫抓取英文逐字稿"""
    try:
        short_id = task_id[:8]
        base_date = datetime.strptime(created_at_str[:10], "%Y-%m-%d")
        
        # 尋找當月與前兩個月
        target_months = []
        for i in range(3):
            m = base_date.month - i
            y = base_date.year
            while m <= 0:
                m += 12; y -= 1
            target_months.append(f"{y}/{m:02d}")
            
        headers = {"Authorization": f"Bearer {s['HF_TOKEN']}"} if s.get("HF_TOKEN") else {}
            
        for ym in target_months:
            hf_url = f"https://huggingface.co/datasets/Hubonbon2025/fortress-intelligence-archive/raw/main/intel_archive/{ym}/{short_id}.json"
            print(f"📡 [HF 尋標] 嘗試搜索座標: {ym} ({short_id}.json)")
            resp = requests.get(hf_url, headers=headers, timeout=30)
            if resp.status_code == 200:
                stt_text = resp.json().get("stt_text")
                if stt_text:
                    print(f"✅ [HF 尋標] 成功提取歸檔！長度：{len(stt_text)} 字元")
                    return stt_text, "SUCCESS"
            elif resp.status_code == 404:
                continue
            else:
                return None, f"HF_HTTP_{resp.status_code}"
        return None, "ARCHIVE_NOT_FOUND_IN_3_MONTHS"
    except Exception as e:
        return None, str(e)

def call_nvidia_rethink(s, stt_text_en, prompt):
    """[階段二 A] 呼叫 Llama 跨語言摘要 (測試 128K 完整吞噬)"""
    client = get_nvidia_client(s['NVIDIA_KEY'])
    print(f"🧠 [深思 A] 啟動 NVIDIA Llama 跨語言深度摘要 (嘗試直吞全文)...")
    
    last_error = ""
    for model_name in CONTROL_PANEL.NVIDIA_MODELS:
        print(f"   🎯 嘗試呼叫模型: {model_name}...")
        try:
            response = client.chat.completions.create(
                model=model_name, 
                messages=[
                    {"role": "system", "content": "你是一位頂尖的情報官。請閱讀以下【英文原稿】，並直接以「繁體中文」回答使用者的問題。排版請維持雙換行，確保閱讀舒適。"},
                    {"role": "user", "content": f"{prompt}\n\n【英文原稿】\n{stt_text_en}"} # 💡 這次我們不切片，整包丟給 128K 模型！
                ],
                max_tokens=4096, temperature=0.7, timeout=120 # 設定 120 秒防卡死
            )
            result_text = response.choices[0].message.content.strip()
            return f"*(本戰報由 NVIDIA {model_name.split('/')[-1]} 生成)*\n\n" + re.sub(r'(?<!\n)\n(?!\n)', '\n\n', result_text), "SUCCESS"
        
        except Exception as e:
            print(f"   ⚠️ 模型 {model_name} 連線異常/逾時: {e}")
            last_error = str(e)
            continue
            
    print("❌ [深思 A 失敗]: 所有 NVIDIA 模型均無回應或發生超時 (Payload 可能過大)。")
    return None, f"ALL_NVIDIA_FAILED: {last_error}"

def call_gemini_rethink(s, stt_text_en, prompt):
    """[階段二 B] 呼叫 Gemini 跨語言摘要 (搭載降級梯隊)"""
    print("🧠 [深思 B] 啟動 Gemini 降級梯隊，準備全文跨語言摘要...")
    
    sys_prompt = "你是一位頂尖的情報官。請吞噬以下超長【英文原稿】，精準掌握全域語意後，直接以「繁體中文」回答使用者的問題。排版請維持雙換行。"
    payload = {
        "contents": [{"parts": [{"text": sys_prompt}, {"text": f"{prompt}\n\n【英文原稿】\n{stt_text_en}"}]}],
        "generationConfig": {"temperature": 0.7}
    }
    
    last_error = ""
    for model_name in CONTROL_PANEL.GEMINI_MODELS:
        print(f"   🎯 嘗試呼叫模型: {model_name}...")
        g_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={s['GEMINI_KEY']}"
        
        try:
            resp = requests.post(g_url, json=payload, timeout=180)
            if resp.status_code == 200:
                result_text = resp.json()['candidates'][0]['content']['parts'][0].get('text', "").strip()
                return f"*(本戰報由 {model_name} 生成)*\n\n" + re.sub(r'(?<!\n)\n(?!\n)', '\n\n', result_text), "SUCCESS"
            elif resp.status_code == 429:
                print(f"   ⚠️ 模型 {model_name} 額度受限 (HTTP 429)，自動降級...")
                last_error = f"HTTP 429: {model_name} Quota Exceeded"
                continue
            else:
                print(f"   ⚠️ 模型 {model_name} 遭遇錯誤: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                continue
        except Exception as e:
            print(f"   ⚠️ 模型 {model_name} 連線異常: {e}")
            last_error = str(e)
            continue
            
    print("❌ [深思 B 失敗]: 所有 Gemini 梯隊均無回應或額度耗盡。")
    return None, f"ALL_GEMINI_FAILED: {last_error}"

# =========================================================
# 🎙️ 通訊發報站 
# =========================================================
def send_rethink_report(s, title, result_nvidia, result_gemini, original_command, listen_url):
    """只空投精華戰報，不再丟垃圾翻譯"""
    safe_title = str(title).replace("*", "") 
    url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
    
    caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n⚙️ *指令：{original_command}*\n🎧 *音檔：* [點擊聽證]({listen_url})"
    
    try:
        print(f"📨 [通訊站] 開始空投戰報...")
        # NVIDIA 戰報
        if result_nvidia:
            n_content = f"📌 主題：{safe_title}\n\n====================\n\n{result_nvidia}" 
            requests.post(url_doc, data={'chat_id': s["TG_CHAT"], 'caption': caption_msg, 'parse_mode': 'Markdown'}, files={'document': (f"NVIDIA戰報_{safe_title[:15]}.txt", n_content.encode('utf-8'))}, timeout=30) 
        
        # Gemini 戰報
        if result_gemini:
            g_content = f"📌 主題：{safe_title}\n\n====================\n\n{result_gemini}"
            requests.post(url_doc, data={'chat_id': s["TG_CHAT"], 'caption': caption_msg if not result_nvidia else "", 'parse_mode': 'Markdown'}, files={'document': (f"Gemini戰報_{safe_title[:15]}.txt", g_content.encode('utf-8'))}, timeout=30) 
            
        print("✅ [通訊站] 戰報空投完畢！")
    except Exception as e:
        print(f"💥 [通訊站] 發送失敗: {e}")

# =========================================================
# 🚀 任務總部署：V4 狀態機 (已移除翻譯階段，加入無盡渦輪)
# =========================================================
def run_rethink_mission():
    print(f"🚀 [TIME_ASSASSIN V4.0] 狀態機啟動 (搭載無盡渦輪，自動推進檔位)...") 
    sb = get_sb(); s = get_secrets() 

    try:
        while True: # 💡 新增無盡渦輪迴圈
            # 🎯 優先級 1：深思階段 
            res = sb.table("mission_reverse").select("*").in_("status", ["awaiting_rethink", "awaiting_translation"]).limit(1).execute()
            if res.data:
                task = res.data[0]; t_id = task['id']
                print(f"🎯 發現待深思任務 ({t_id[:8]})")
                sb.table("mission_reverse").update({"status": "processing_rethink"}).eq("id", t_id).execute()
                
                raw_prompt = task.get('target_prompt', '')
                prompt = build_prompt(raw_prompt)
                stt_text_en = task.get('stt_text', '') 
                
                result_nvidia, result_gemini = None, None
                
                if CONTROL_PANEL.ENABLE_NVIDIA_LLAMA:
                    result_nvidia, n_status = call_nvidia_rethink(s, stt_text_en, prompt)
                else:
                    n_status = "SKIPPED"
                    
                if CONTROL_PANEL.ENABLE_GEMINI_FALLBACK:
                    result_gemini, g_status = call_gemini_rethink(s, stt_text_en, prompt)
                else:
                    g_status = "SKIPPED"
                
                if n_status == "SUCCESS" or g_status == "SUCCESS":
                    sb.table("mission_reverse").update({"status": "completed", "result_text": result_nvidia or result_gemini, "email_sent": True}).eq("id", t_id).execute()
                    
                    q_res = sb.table("mission_queue").select("episode_title, r2_url").eq("id", task.get('task_id')).single().execute()
                    title = q_res.data.get('episode_title', '未知標題') if q_res.data else '未知標題'
                    listen_url = f"{s['R2_URL']}/{task.get('r2_url', '').lstrip('/')}"
                    
                    send_rethink_report(s, title, result_nvidia, result_gemini, raw_prompt, listen_url)
                    continue # 💡 任務完成，繼續下一輪檢查
                else:
                    sb.table("mission_reverse").update({"status": "awaiting_rethink", "error_log": "All Rethink Engines Failed"}).eq("id", t_id).execute()
                    continue # 💡 任務失敗，記錄後繼續下一輪檢查

            # 🎯 優先級 2：歸檔提領階段 (HF)
            res = sb.table("mission_reverse").select("*").eq("status", "awaiting_stt").limit(1).execute()
            if res.data:
                task = res.data[0]; t_id = task['id']; q_id = task.get('task_id')
                print(f"🎯 發現 awaiting_stt 任務 ({t_id[:8]})，啟動 HF 歸檔提領...")
                sb.table("mission_reverse").update({"status": "processing_stt"}).eq("id", t_id).execute()
                
                q_res = sb.table("mission_queue").select("created_at").eq("id", q_id).single().execute()
                if not q_res.data:
                    sb.table("mission_reverse").update({"status": "awaiting_stt", "error_log": "Queue Record Not Found"}).eq("id", t_id).execute()
                    continue # 💡 找不到紀錄，繼續下一輪檢查
                    
                created_at = q_res.data.get('created_at', '')
                stt_text, status_code = fetch_stt_from_huggingface(s, q_id, created_at)
                
                if status_code == "SUCCESS":
                    sb.table("mission_reverse").update({"status": "awaiting_rethink", "stt_text": stt_text}).eq("id", t_id).execute()
                    print("✅ 逐字稿提領完畢，跳過翻譯，直接推進至 awaiting_rethink。")
                else:
                    sb.table("mission_reverse").update({"status": "awaiting_stt", "error_log": f"HF Error: {status_code}"}).eq("id", t_id).execute()
                continue # 💡 提領完畢，繼續下一輪檢查（會自動進入優先級 1）

            # 🎯 如果所有狀態都找不到任務，退出迴圈
            print("🛌 產線空閒，無待處理任務。")
            run_janitor(sb)
            break # 💡 退出迴圈，結束 GHA 任務

    except Exception as e:
        print(f"💥 [核心潰敗] 狀態機中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
