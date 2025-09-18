# src/core/orchestrator.py
import argparse
import logging
import sys
import threading
from pathlib import Path

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 新的管理員導入 ---
from core.managers.dependency_manager import DependencyManager
from core.managers.process_manager import ProcessManager
from core.managers.readiness_manager import ReadinessManager

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('orchestrator')

def main():
    """
    新版協調器主函式。
    負責依序調用各個管理器來完成啟動流程。
    """
    parser = argparse.ArgumentParser(description="系統協調器 v6 (模組化)。")
    parser.add_argument("--mock", action="store_true", help="如果設置，則 worker 將以模擬模式運行。")
    args, _ = parser.parse_known_args()

    process_manager = None
    try:
        log.info("--- [協調器啟動 v6] ---")

        # 步驟 1: 處理依賴
        dep_manager = DependencyManager()
        dep_manager.setup_core_dependencies()

        # 步驟 2: 啟動核心進程
        process_manager = ProcessManager()
        api_port, api_ready_event = process_manager.start_services(mock_mode=args.mock)

        # 步驟 3: 啟動背景就緒檢查任務
        readiness_manager = ReadinessManager(api_port, api_ready_event)
        readiness_thread = threading.Thread(target=readiness_manager.run_in_background, daemon=True)
        readiness_thread.start()

        # 步驟 4: 進入主監控迴圈
        process_manager.monitor_processes()

    except (Exception, KeyboardInterrupt) as e:
        if isinstance(e, KeyboardInterrupt):
            log.warning("捕獲到手動中斷信號 (KeyboardInterrupt)...")
        else:
            log.critical(f"協調器發生致命錯誤: {e}", exc_info=True)
    finally:
        log.info("--- [協調器開始關閉程序] ---")
        if process_manager:
            process_manager.shutdown()
        log.info("✅ 協調器已關閉。")
        # 根據是否有錯誤來決定退出碼
        sys.exit(1 if 'e' in locals() and not isinstance(e, KeyboardInterrupt) else 0)

if __name__ == "__main__":
    main()
