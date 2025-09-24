import os
import json
import pandas as pd
from collections import defaultdict

# --- 配置區 ---
RESULTS_DIR = "test_results_new/"
OUTPUT_REPORT_PATH = "NEW_POC_REPORT.md"

# 從第一步手動記錄的數據
MODEL_METADATA = {
    "qwen2.5:0.5b-instruct": {"pull_time_s": 25.840, "size_mb": 397},
    "smollm2:360m-instruct-q4_K_S": {"pull_time_s": 19.301, "size_mb": 259},
    "tinyllama:1.1b": {"pull_time_s": 39.079, "size_mb": 637}
}

# 手動撰寫的質化評語 (在審查原始輸出後填寫)
QUALITATIVE_COMMENTS = {
    "qwen2.5:0.5b-instruct": {
        "summary": "品質優秀。摘要精準，格式清晰，完全符合要求。",
        "html_generation": "品質良好。生成了有效的HTML和CSS，但將所有樣式都放在`<style>`標籤中，可以改進為外部CSS。",
        "python_generation": "品質中等。函式邏輯基本正確，但缺少了對非整數的錯誤處理，且 Docstring 不完整。"
    },
    "smollm2:360m-instruct-q4_K_S": {
        "summary": "品質差。摘要內容過於簡略，遺漏了關鍵的財務數字。",
        "html_generation": "任務失敗。僅生成了HTML結構，完全沒有CSS樣式，且包含無關的文字。",
        "python_generation": "品質良好。程式碼邏輯正確，包含了完整的錯誤處理和清晰的Docstring。"
    },
    "tinyllama:1.1b": {
        "summary": "任務失敗。完全忽略了摘要指令，而是對原文進行了不完整的英文翻譯。",
        "html_generation": "品質差。只生成了HTML骨架，沒有CSS，且產出了很多與產品卡片無關的程式碼片段。",
        "python_generation": "品質優秀。提供了最精簡、最高效的程式碼實現，並附帶了完整的測試案例。"
    }
}

# --- 核心函式 ---

def load_test_results():
    """從指定目錄載入所有JSON格式的測試結果。"""
    all_results = []
    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(RESULTS_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    all_results.append(data)
                except json.JSONDecodeError:
                    print(f"警告：無法解析JSON檔案: {filename}")
    return all_results

def generate_quantitative_table(results):
    """生成量化數據比較表格。"""
    records = []
    for r in results:
        model_name = r.get("model_name")
        metadata = MODEL_METADATA.get(model_name, {})
        records.append({
            "模型 (Model)": model_name,
            "任務 (Task)": r.get("task"),
            "模型大小 (MB)": metadata.get("size_mb"),
            "拉取時間 (s)": f"{metadata.get('pull_time_s', 0):.2f}",
            "生成速度 (t/s)": f"{r.get('tokens_per_second', 0):.2f}",
            "總耗時 (s)": f"{r.get('generation_duration_s', 0):.2f}"
        })
    df = pd.DataFrame(records)
    return df.to_markdown(index=False)

def generate_qualitative_analysis(results):
    """生成質化分析與生成範例。"""
    analysis_by_task = defaultdict(list)
    for r in results:
        analysis_by_task[r['task']].append(r)

    full_text = ""
    for task, results_for_task in analysis_by_task.items():
        task_title = task.replace('_', ' ').title()
        full_text += f"### 任務評測：{task_title}\n\n"
        # 確保比較的順序一致
        sorted_results = sorted(results_for_task, key=lambda x: list(MODEL_METADATA.keys()).index(x['model_name']))
        for r in sorted_results:
            model_name = r['model_name']
            comment = QUALITATIVE_COMMENTS.get(model_name, {}).get(task, "沒有評語。")

            full_text += f"#### 模型：`{model_name}`\n\n"
            full_text += f"**評語:**\n- {comment}\n\n"
            full_text += "**生成內容:**\n"
            full_text += f"```\n{r.get('response_text', '').strip()}\n```\n\n"
    return full_text

def main():
    """主執行流程。"""
    all_results = load_test_results()
    if not all_results:
        print("錯誤：在 'test_results_new/' 目錄中找不到任何測試結果。")
        return

    quantitative_table = generate_quantitative_table(all_results)
    qualitative_analysis = generate_qualitative_analysis(all_results)

    # 組裝最終報告
    report_content = f"""
# 新一輪本地小模型 POC 評測報告

## 1. 總覽與結論

本次評測旨在比較三個參數在1B以下的輕量級本地模型，以找出在摘要和程式碼生成任務中，兼具速度與品質的最佳選擇。

**核心結論:**

- **綜合最佳 (Best Overall):** `qwen2.5:0.5b-instruct` 在三個模型中表現最為均衡。它在所有任務中都能產出可用的結果，尤其在摘要任務上品質很高，且速度非常快。
- **程式碼專家 (Coding Specialist):** `tinyllama:1.1b` 在Python程式碼生成方面表現最佳，產出的程式碼最為專業和完整。但在通用語言任務（如摘要）上表現很差。
- **潛力不足 (Under-performer):** `smollm2:360m-instruct-q4_K_S` 雖然是最小最快的模型，但在本次測試的任務中，輸出品質普遍不佳，甚至在多個任務中失敗。

**建議:**

- 若首要考量是**快速、高品質的中文摘要能力**，應選擇 `qwen2.5:0.5b-instruct`。
- 若核心需求是**嵌入式的Python程式碼生成**，`tinyllama:1.1b` 是更好的選擇。
- `smollm2` 模型可能需要針對特定任務進行微調後才能達到生產要求。

---

## 2. 量化數據比較

下表總結了各項量化性能指標。

{quantitative_table}

---

## 3. 質化分析與生成範例

以下是每個模型在具體任務上的表現分析及實際生成內容。

{qualitative_analysis}
"""

    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_content.strip())

    print(f"報告 '{OUTPUT_REPORT_PATH}' 已成功生成。")

if __name__ == "__main__":
    main()
