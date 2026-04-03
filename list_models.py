# ---------------------------------------------------------
# 程式碼：list_models.py (兵器庫偵查兵)
# 職責：精準列出目前 API Key 授權的所有可用模型。
# ---------------------------------------------------------
import os
import google.generativeai as genai # 引入 Google AI SDK

def scout_available_models():
    # 從環境變數獲取 API Key
    api_key = os.environ.get("GEMINI_API_KEY") 
    
    if not api_key:
        print("❌ 錯誤：找不到 GEMINI_API_KEY，請確認環境變數設定。")
        return

    # 配置 API 密鑰
    genai.configure(api_key=api_key) 

    print(f"📡 正在連結總部，讀取可用模型列表...\n")
    print(f"{'模型名稱 (ID)':<40} | {'支援功能'}")
    print("-" * 70)

    # 執行偵查：遍歷所有模型
    for m in genai.list_models():
        # 過濾掉不支援生成內容的模型 (例如僅支援 Embedding 的)
        if 'generateContent' in m.supported_generation_methods:
            print(f"{m.name:<40} | {m.display_name}")

if __name__ == "__main__":
    scout_available_models() # 啟動偵查任務
