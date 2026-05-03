# ---------------------------------------------------------
# 程式碼：deep_rethink_mission.py (V3.1 狀態機與 NIM 切片標記版)
# 職責：處理 mission_reverse 任務，具備斷點續傳、語義切片與多模型協同能力。
# 特色：加入 @[斷句]@ 邊界標記防禦，確保長文本翻譯拼接完美無痕。
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
# ⚙️ 初始化配置與連線
# =========================================================
def get_sb():
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")) 

def get_secrets():
    return {
        "NVIDIA_KEY": os.environ.get("NVIDIA_API_KEY"), 
        "R2_URL": (os.environ.get("R2_PUBLIC_URL") or "").rstrip('/'), 
        "TG_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"), 
        "TG_CHAT": os.environ.get("TELEGRAM_CHAT_ID") 
    }

def get_nvidia_client(api_key):
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

# =========================================================
# 🛠️ 輔助工具：語義切片器 (Semantic Chunking)
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
# 🧠 NVIDIA NIM 火控中心 
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
            
        # 💡 核心修改：植入 @[斷句]@ 標誌，並使用雙換行確保閱讀舒適度
        final_translation = "\n\n@[斷句]@\n\n".join(translated_chunks)
        return final_translation, "SUCCESS"
    except Exception as e:
        print(f"❌ [翻譯 失敗]: {e}")
        return None, str(e)

def call_nvidia_rethink(s, stt_text_tw, prompt):
    """[階段三] 呼叫 Llama-3.3-70B 進行深度逆向摘要"""
    client = get_nvidia_client(s['NVIDIA_KEY'])
    print("🧠 [深思] 啟動 Llama-3.3-70B 深度摘要...")
    
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct", 
            messages=[
                {"role": "system", "content": "你是一位頂尖的地緣政治、熟知歷史與財經戰略，有話直說(風險直視)情報官。排版請維持雙換行，確保閱讀舒適。"},
                {"role": "user", "content": f"{prompt}\n\n【情報來源逐字稿 (繁體中文)】\n{stt_text_tw}"}
            ],
            max_tokens=4096,
            temperature=0.7
        )
        
        result_text = response.choices[0].message.content.strip()
        # 確保排版舒適，將單換行替換為雙換行 (如果 AI 沒有照做的話)
        result_text = re.sub(r'(?<!\n)\n(?!\n)', '\n\n', result_text)
        
        return result_text, "SUCCESS"
    except Exception as e:
        print(f"❌ [深思 失敗]: {e}")
        return None, str(e)

# =========================================================
# 🎙️ 通訊發報站 
# =========================================================
def send_rethink_report(s, title, result, translation_text, used_model, original_command, listen_url):
    """雙檔案封裝空投"""
    safe_title = str(title).replace("*", "") 
    url_doc = f"https://api.telegram.org/bot{s['TG_TOKEN']}/sendDocument"
    
    caption_msg = f"🔍 *【深度再思：情報完工】*\n📌 *主題：{safe_title}*\n🤖 *模型：{used_model}*\n⚙️ *指令：{original_command}*\n🎧 *音檔：* [點擊聽證]({listen_url})"
    
    report_content = f"📌 主題：{safe_title}\n🤖 模型：{used_model}\n⚙️ 指令：{original_command}\n🎧 音檔：{listen_url}\n\n====================\n\n{result}" 
    report_file = {'document': (f"深度戰報_{safe_title[:15]}.txt", report_content.encode('utf-8'))}
    
    transcript_file = {'document': (f"中文逐字稿_{safe_title[:15]}.txt", translation_text.encode('utf-8'))}
    
    try:
        print(f"📨 [通訊站] 開始空投戰報...")
        requests.post(url_doc, data={'chat_id': s["TG_CHAT"], 'caption': caption_msg, 'parse_mode': 'Markdown'}, files=report_file, timeout=30) 
        requests.post(url_doc, data={'chat_id': s["TG_CHAT"]}, files=transcript_file, timeout=30) 
        print("✅ [通訊站] 雙檔案空投完畢！")
    except Exception as e:
        print(f"💥 [通訊站] 發送失敗: {e}")

# =========================================================
# 🚀 任務總部署：四檔狀態機 
# =========================================================
def run_rethink_mission():
    print(f"🚀 [TIME_ASSASSIN V3.1] 四檔狀態機啟動 (搭載邊界標記與語義切片)...") 
    sb = get_sb()
    s = get_secrets() 

    try:
        # 🎯 優先級 1：深思階段
        res = sb.table("mission_reverse").select("*").eq("status", "awaiting_rethink").limit(1).execute()
        if res.data:
            task = res.data[0]; t_id = task['id']
            print(f"🎯 發現 awaiting_rethink 任務 ({t_id[:8]})")
            sb.table("mission_reverse").update({"status": "processing_rethink"}).eq("id", t_id).execute()
            
            prompt = build_prompt(task.get('target_prompt', ''))
            stt_text_tw = task.get('stt_text_tw', '')
            
            result, status_code = call_nvidia_rethink(s, stt_text_tw, prompt)
            
            if status_code == "SUCCESS":
                sb.table("mission_reverse").update({"status": "completed", "result_text": result, "email_sent": True}).eq("id", t_id).execute()
                q_res = sb.table("mission_queue").select("episode_title, r2_url").eq("id", task.get('task_id')).single().execute()
                title = q_res.data.get('episode_title', '未知標題') if q_res.data else '未知標題'
                listen_url = f"{s['R2_URL']}/{task.get('r2_url', '').lstrip('/')}"
                
                send_rethink_report(s, title, result, stt_text_tw, "Llama-3.3-70B", task.get('target_prompt', ''), listen_url)
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
            
            stt_text = task.get('stt_text', '')
            translated_tw, status_code = call_nvidia_translate(s, stt_text)
            
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
