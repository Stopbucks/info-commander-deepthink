# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V3.2 狀態機與 NIM/Gemini 雙引擎終極版)
# 職責：處理 mission_reverse 任務，具備斷點續傳、語義切片與雙軌對照能力。
# 特色：加入 @[斷句]@ 邊界標記，並預留 Gemini 全面接管的一鍵開關。
# ---------------------------------------------------------
import os, time, random, requests, gc
import re
import subprocess, tempfile
from datetime import datetime, timezone
from supabase import create_client
from openai import OpenAI 
from prompt_templates import build_prompt
from mission_janitor import run_janitor

# =========================================================
# 🎛️ 戰略升級開關 (Future-Proof Switch)
# =========================================================
# 若設為 True，即使長官只輸入 /A，也會強制啟動 Gemini 雙軌輔助。
USE_GEMINI_AS_DEFAULT = False 

# =========================================================
# ⚙️ 初始化配置與連線
# =========================================================
def get_sb():
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")) 

def get_secrets():
    return {
        "NVIDIA_KEY": os.environ.get("NVIDIA_API_KEY"), 
        "GEMINI_KEY": os.environ.get("GEMINI_API_KEY"), # 💡 包含 Gemini 金鑰
        "R2_URL": (os.environ.get("R2_PUBLIC_URL") or "").rstrip('/'), 
        "TG_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"), 
        "TG_CHAT": os.environ.get("TELEGRAM_CHAT_ID") 
    }

def get_nvidia_client(api_key):
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

# =========================================================
# 🛠️ 輔助工具：語義切片器 
# =========================================================
def split_text_semantically(text, target_size=1800):
    """在接近 1800 字時，往回尋找最近的句點或換行符號進行完美斷句"""
    chunks = []
    while len(text) > target_size:
        search_window = text[:target_size]
        match = re.search(r'[.!?\n](?=\s|$)', search_window[::-1]) 
        
        if match:
            cut_idx = target_size - match.start()
        else:
            cut_idx = target_size 
            
        chunks.append(text[:cut_idx].strip())
        text = text[cut_idx:].strip()
        
    if text: chunks.append(text)
    return chunks

# =========================================================
# 🧠 AI 火控中心 (NVIDIA + Gemini)
# =========================================================

def call_nvidia_stt(s, r2_path):
    """[階段一] 呼叫 Whisper-large-v3 進行聽打"""
    client = get_nvidia_client(s['NVIDIA_KEY'])
    url = r2_path if r2_path.startswith("http") else f"{s['R2_URL']}/{r2_path.lstrip('/')}"
    
    try:
        print(f"📡 [STT] 下載音檔中: {url}")
        raw_bytes = requests.get(url, timeout=120).content 
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".raw") as tmp_raw:
            tmp_raw.write(raw_bytes)
            tmp_raw_path = tmp_raw.name
        
        tmp_mp3_path = tmp_raw_path + ".mp3"
        subprocess.run(['ffmpeg', '-y', '-i', tmp_raw_path, 
                        '-ar', '16000', '-ac', '1', 
                        '-c:a', 'libmp3lame', '-b:a', '32k', 
                        tmp_mp3_path], 
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print("🎙️ [STT] 啟動 NVIDIA Whisper 聽寫...")
        with open(tmp_mp3_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                file=audio_file,
                model="openai/whisper-large-v3",
                response_format="text"
            )
            
        return transcript, "SUCCESS"
    except Exception as e:
        print(f"❌ [STT 失敗]: {e}")
        return None, str(e)
    finally:
        if os.path.exists(tmp_raw_path): os.remove(tmp_raw_path)
        if os.path.exists(tmp_mp3_path): os.remove(tmp_mp3_path)
        del raw_bytes; gc.collect()

def call_nvidia_translate(s, english_text):
    """[階段二] 呼叫 DeepSeek-flash 進行切片翻譯與標記植入"""
    client = get_nvidia_client(s['NVIDIA_KEY'])
    chunks = split_text_semantically(english_text, target_size=1800)
    translated_chunks = []
    
    sys_prompt = "你是一個精通繁體中文的頂級口譯員。請將以下英文逐字稿翻譯為流暢、具備母語語感的繁體中文。請保留講者的語氣，專注於語意準確，排版請適度保留段落換行，不需要加上任何解釋或標題。"
    
    print(f"🌐 [翻譯] 啟動 DeepSeek 翻譯，共分為 {len(chunks)} 個切片...")
    try:
        for i, chunk in enumerate(chunks):
            print(f"   ⏳ 處理切片 {i+1}/{len(chunks)}...")
            response = client.chat.completions.create(
                model="deepseek-ai/deepseek-v4-flash", 
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": chunk}
                ],
                max_tokens=4096,
                temperature=0.3
            )
            translated_chunks.append(response.choices[0].message.content.strip())
            time.sleep(1.5) 
            
        # 💡 植入 @[斷句]@ 標誌，並使用雙換行確保閱讀舒適度
        final_translation = "\n\n@[斷句]@\n\n".join(translated_chunks)
        return final_translation, "SUCCESS"
    except Exception as e:
        print(f"❌ [翻譯 失敗]: {e}")
        return None, str(e)

def call_nvidia_rethink(s, stt_text_tw, prompt):
    """[階段三 A 路徑] 呼叫 Llama-3.3-70B 進行中文切片深度摘要"""
    client = get_nvidia_client(s['NVIDIA_KEY'])
    print("🧠 [深思 A] 啟動 Llama-3.3-70B 深度摘要...")
    
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct", 
            messages=[
                {"role": "system", "content": "你是一位頂尖的地緣政治、熟知歷史與財經戰略，直言不諱情報官。排版請維持雙換行，確保閱讀舒適。"},
                {"role": "user", "content": f"{prompt}\n\n【情報來源逐字稿 (繁體中文)】\n{stt_text_tw}"}
            ],
            max_tokens=4096,
            temperature=0.7
        )
        result_text = response.choices[0].message.content.strip()
        result_text = re.sub(r'(?<!\n)\n(?!\n)', '\n\n', result_text) # 強制舒適雙換行
        return result_text, "SUCCESS"
    except Exception as e:
        print(f"❌ [深思 A 失敗]: {e}")
        return None, str(e)

def call_gemini_text_rethink(s, stt_text_en, prompt):
    """[階段三 B 路徑] 呼叫 Gemini-2.5-Flash 直吞英文原稿摘要"""
    print("🧠 [深思 B] 啟動 Gemini-2.5-Flash 英文原稿直讀摘要...")
    g_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={s['GEMINI_KEY']}"
    
    sys_prompt = "你是一位頂尖的地緣政治與財經戰略情報官。請根據以下提供的「英文逐字稿 (Raw STT)」，以「繁體中文」進行深度分析與回答。排版請維持雙換行。"
    
    payload = {
        "contents": [{"parts": [{"text": sys_prompt}, {"text": f"{prompt}\n\n【英文逐字稿 (Raw STT)】\n{stt_text_en}"}]}],
        "generationConfig": {"temperature": 0.7}
    }
    
    try:
        resp = requests.post(g_url, json=payload, timeout=180)
        if resp.status_code == 200:
            result_text = resp.json()['candidates'][0]['content']['parts'][0].get('text', "").strip()
            result_text = re.sub(r'(?<!\n)\n(?!\n)', '\n\n', result_text) 
            return result_text, "SUCCESS"
        else:
            return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, str(e)

# =========================================================
# 🎙️ 通訊發報站 
# =========================================================
def send_rethink_report(s, title, result_nvidia, translation_text, result_gemini, original_command, listen_url):
    """支援最多 3 個檔案的終極空投系統"""
    safe_title = str(title).replace("*", "") 
    url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
    
    model_name = "Llama-3.3-70B" + (" + Gemini-2.5" if result_gemini else "")
    caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n🤖 *模型：{model_name}*\n⚙️ *指令：{original_command}*\n🎧 *音檔：* [點擊聽證]({listen_url})"
    
    # 檔案 1：Llama 戰報
    report_content = f"📌 主題：{safe_title}\n🤖 模型：Llama-3.3-70B\n⚙️ 指令：{original_command}\n🎧 音檔：{listen_url}\n\n====================\n\n{result_nvidia}" 
    report_file = {'document': (f"NVIDIA戰報_{safe_title[:15]}.txt", report_content.encode('utf-8'))}
    
    # 檔案 2：繁中逐字稿
    transcript_file = {'document': (f"中文逐字稿_{safe_title[:15]}.txt", translation_text.encode('utf-8'))}
    
    try:
        print(f"📨 [通訊站] 開始空投戰報...")
        requests.post(url_doc, data={'chat_id': s["TG_CHAT"], 'caption': caption_msg, 'parse_mode': 'Markdown'}, files=report_file, timeout=30) 
        requests.post(url_doc, data={'chat_id': s["TG_CHAT"]}, files=transcript_file, timeout=30) 
        
        # 檔案 3：Gemini 對照戰報 (若有觸發)
        if result_gemini:
            gemini_content = f"📌 主題：{safe_title}\n🤖 模型：Gemini-2.5-Flash\n⚙️ 指令：{original_command}\n\n====================\n\n{result_gemini}"
            gemini_file = {'document': (f"Gemini對照戰報_{safe_title[:15]}.txt", gemini_content.encode('utf-8'))}
            requests.post(url_doc, data={'chat_id': s["TG_CHAT"]}, files=gemini_file, timeout=30) 
            
        print("✅ [通訊站] 所有檔案空投完畢！")
    except Exception as e:
        print(f"💥 [通訊站] 發送失敗: {e}")

# =========================================================
# 🚀 任務總部署：四檔狀態機 
# =========================================================
def run_rethink_mission():
    print(f"🚀 [TIME_ASSASSIN V3.2] 四檔狀態機啟動 (搭載雙引擎與智能升級開關)...") 
    sb = get_sb(); s = get_secrets() 

    try:
        # 🎯 優先級 1：深思階段 (等待摘要)
        res = sb.table("mission_reverse").select("*").eq("status", "awaiting_rethink").limit(1).execute()
        if res.data:
            task = res.data[0]; t_id = task['id']
            print(f"🎯 發現 awaiting_rethink 任務 ({t_id[:8]})")
            sb.table("mission_reverse").update({"status": "processing_rethink"}).eq("id", t_id).execute()
            
            raw_prompt = task.get('target_prompt', '')
            # 💡 判斷是否啟動 Gemini (依據全域開關 或 指令字尾 G)
            need_gemini = USE_GEMINI_AS_DEFAULT or bool(re.search(r'/[ABD]G', raw_prompt.upper()))
            
            prompt = build_prompt(raw_prompt)
            stt_text_tw = task.get('stt_text_tw', '')
            stt_text_en = task.get('stt_text', '')
            
            # 執行 NVIDIA 主線
            result_nvidia, status_code = call_nvidia_rethink(s, stt_text_tw, prompt)
            
            if status_code == "SUCCESS":
                # 執行 Gemini 輔助線 (若符合條件)
                result_gemini = None
                if need_gemini and stt_text_en:
                    result_gemini, _ = call_gemini_text_rethink(s, stt_text_en, prompt)
                
                sb.table("mission_reverse").update({"status": "completed", "result_text": result_nvidia, "email_sent": True}).eq("id", t_id).execute()
                
                # 取得基本資訊準備空投
                q_res = sb.table("mission_queue").select("episode_title, r2_url").eq("id", task.get('task_id')).single().execute()
                title = q_res.data.get('episode_title', '未知標題') if q_res.data else '未知標題'
                listen_url = f"{s['R2_URL']}/{task.get('r2_url', '').lstrip('/')}"
                
                send_rethink_report(s, title, result_nvidia, stt_text_tw, result_gemini, raw_prompt, listen_url)
                return 
            else:
                sb.table("mission_reverse").update({"status": "awaiting_rethink", "error_log": f"Rethink Error: {status_code}"}).eq("id", t_id).execute()
                return

        # 🎯 優先級 2：翻譯階段
        res = sb.table("mission_reverse").select("*").eq("status", "awaiting_translation").limit(1).execute()
        if res.data:
            task = res.data[0]; t_id = task['id']
            print(f"🎯 發現 awaiting_translation 任務 ({t_id[:8]})")
            sb.table("mission_reverse").update({"status": "processing_translation"}).eq("id", t_id).execute()
            
            translated_tw, status_code = call_nvidia_translate(s, task.get('stt_text', ''))
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "awaiting_rethink", "stt_text_tw": translated_tw}).eq("id", t_id).execute()
                print("✅ 翻譯完畢，推進至 awaiting_rethink。")
            else:
                sb.table("mission_reverse").update({"status": "awaiting_translation", "error_log": f"Trans Error: {status_code}"}).eq("id", t_id).execute()
            return

        # 🎯 優先級 3：聽打階段
        res = sb.table("mission_reverse").select("*").eq("status", "awaiting_stt").limit(1).execute()
        if res.data:
            task = res.data[0]; t_id = task['id']
            print(f"🎯 發現 awaiting_stt 任務 ({t_id[:8]})")
            sb.table("mission_reverse").update({"status": "processing_stt"}).eq("id", t_id).execute()
            
            stt_text, status_code = call_nvidia_stt(s, task.get('r2_url'))
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "awaiting_translation", "stt_text": stt_text}).eq("id", t_id).execute()
                print("✅ 聽寫完畢，推進至 awaiting_translation。")
            else:
                sb.table("mission_reverse").update({"status": "awaiting_stt", "error_log": f"STT Error: {status_code}"}).eq("id", t_id).execute()
            return

        print("🛌 產線空閒，無待處理任務。")
        run_janitor(sb)

    except Exception as e:
        print(f"💥 [核心潰敗] 狀態機中斷: {str(e)}") 

if __name__ == "__main__":
    run_rethink_mission()
