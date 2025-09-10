# src/tools/readme_tool.py
"""
這是一個自動化工具，用於生成 `src/tools/` 目錄下所有工具的說明文件。
它會掃描所有非模擬的 Python 檔案，提取其模組級別的 docstring，
並將結果編譯成一個易於閱讀的 Markdown 檔案。
"""

import os
import ast
from pathlib import Path
import logging

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('readme_tool')

# --- 常數 ---
TOOLS_DIR = Path(__file__).parent
ROOT_DIR = TOOLS_DIR.parent.parent
OUTPUT_FILE = ROOT_DIR / "TOOLS_README.md"

def get_module_docstring(filepath: Path) -> str | None:
    """
    使用 ast 安全地解析 Python 檔案並提取其模組級別的 docstring。

    :param filepath: Python 檔案的路徑。
    :return: 模組的 docstring，如果沒有則回傳 None。
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        return ast.get_docstring(tree)
    except Exception as e:
        log.warning(f"無法解析檔案 {filepath} 或提取其 docstring: {e}")
        return None

def generate_tools_readme():
    """
    掃描 tools 目錄，生成一個包含所有工具說明的 README.md 檔案。
    """
    log.info("--- 開始生成工具 README ---")

    markdown_lines = ["# 工具說明文件", ""]
    markdown_lines.append("本文件自動生成，旨在說明 `src/tools/` 目錄下所有可用的工具。")
    markdown_lines.append("")

    tool_files = sorted(TOOLS_DIR.glob("*.py"))

    for tool_file in tool_files:
        # 排除 __init__.py、模擬工具和此工具本身
        if tool_file.name.startswith(("__", "mock_", "readme_tool")):
            continue

        log.info(f"正在處理工具: {tool_file.name}")
        docstring = get_module_docstring(tool_file)

        if not docstring:
            docstring = "未提供說明文件。"

        markdown_lines.append(f"## ` {tool_file.name} `")
        # 清理 docstring 的縮排
        cleaned_docstring = '\n'.join(line.strip() for line in docstring.strip().split('\n'))
        markdown_lines.append(cleaned_docstring)
        markdown_lines.append("")

    # 將結果寫入檔案
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(markdown_lines))
        log.info(f"✅ 工具說明文件已成功生成於: {OUTPUT_FILE}")
    except IOError as e:
        log.error(f"寫入 README 檔案時發生錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    generate_tools_readme()
