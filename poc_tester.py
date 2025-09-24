import sys
import json
import time
import requests

# --- 配置區 ---
OLLAMA_HOST = "http://localhost:11434"
API_ENDPOINT = f"{OLLAMA_HOST}/api/generate"

PROMPTS = {
    "summary": """請總結以下這份關於一家虛構公司「Innovate Inc.」的2024年第二季度財務報告：

Innovate Inc. 在2024年第二季度表現出色，總營收達到1.5億美元，較去年同期增長15%。淨利潤為3000萬美元，利潤率達到20%，主要受其旗艦產品「QuantumLeap」強勁銷售的推動。研發投入增加至2500萬美元，專注於下一代AI技術的開發。公司預計第三季度將推出新產品「ConnectSphere」，有望進一步擴大市場份額。""",
    "html_generation": "請使用HTML和CSS建立一個簡單的產品展示卡片。卡片應該包含一張圖片(使用placeholder圖片)、產品名稱、一段簡短描述和一個「購買」按鈕。請確保卡片有圓角、陰影和一個懸停(hover)效果。",
    "python_generation": "請編寫一個Python函式 `calculate_fibonacci(n)`。這個函式應該接收一個整數 `n` 作為輸入，並返回費波那契數列中的第 `n` 個數字。請包含錯誤處理，例如當輸入為負數或非整數時，應引發 `ValueError`。同時，請為此函式加上適當的Docstring。"
}

# --- 核心測試函式 ---

def run_test_prompt(model_name, task_name, prompt):
    """執行單一測試提示並收集數據，然後將結果以JSON格式印出。"""
    print(f"  - 正在對模型 '{model_name}' 執行任務：'{task_name}'...", file=sys.stderr)
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }

    try:
        start_time = time.time()
        response = requests.post(API_ENDPOINT, json=payload, timeout=300) # 5分鐘超時
        response.raise_for_status()
        end_time = time.time()

        response_data = response.json()

        generation_duration = end_time - start_time
        total_duration_ns = response_data.get("total_duration", 1)
        eval_count = response_data.get("eval_count", 0)
        tokens_per_second = (eval_count / (total_duration_ns / 1e9)) if total_duration_ns > 0 else 0

        result = {
            "model_name": model_name,
            "task": task_name,
            "response_text": response_data.get("response", ""),
            "generation_duration_s": generation_duration,
            "tokens_per_second": tokens_per_second,
            "raw_metrics": response_data
        }
        print(f"    完成。耗時: {generation_duration:.2f}s, 速度: {tokens_per_second:.2f} t/s", file=sys.stderr)
        return result
    except requests.exceptions.RequestException as e:
        print(f"    執行任務 '{task_name}' 時出錯: {e}", file=sys.stderr)
        return {"model_name": model_name, "task": task_name, "error": str(e)}

# --- 主執行流程 ---

def main():
    """
    腳本主入口。
    用法: python poc_tester.py --task <task_name> <model_name>
    """
    if len(sys.argv) != 4 or sys.argv[1] != '--task':
        print("用法: python poc_tester.py --task <task_name> <model_name>", file=sys.stderr)
        print("可用任務: summary, html_generation, python_generation", file=sys.stderr)
        sys.exit(1)

    task_name = sys.argv[2]
    model_name = sys.argv[3]

    if task_name not in PROMPTS:
        print(f"錯誤：未知的任務 '{task_name}'", file=sys.stderr)
        sys.exit(1)

    prompt_text = PROMPTS[task_name]
    test_result = run_test_prompt(model_name, task_name, prompt_text)

    # 將最終結果以JSON格式打印到標準輸出，以便外部程序捕獲
    print(json.dumps(test_result, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    main()
