# src/core/workflow_engine.py
import logging
from typing import Dict, Any, Callable

# V78 重構：不再導入 DBClient
# from src.db.client import DBClient

from .workflow_commands import command_download_and_extract, command_analyze_text

log = logging.getLogger(__name__)

class WorkflowEngine:
    """
    負責執行宣告式工作流的引擎。
    """
    # V78 重構：修改 __init__ 的類型提示，使其更通用
    def __init__(self, db_client: Any):
        self.db = db_client
        self._command_registry: Dict[str, Callable] = {}
        self._register_commands()

    def _register_commands(self):
        """
        將指令名稱與其對應的處理函式進行註冊。
        """
        self.register_command('DOWNLOAD_AND_EXTRACT', command_download_and_extract)
        self.register_command('ANALYZE_TEXT', command_analyze_text)
        log.info("指令註冊表初始化完成。")

    def register_command(self, command_name: str, handler: Callable):
        if command_name in self._command_registry:
            log.warning(f"指令 '{command_name}' 已被註冊，將被覆寫。")
        self._command_registry[command_name] = handler
        log.info(f"指令 '{command_name}' 已成功註冊。")

    def run_workflow(self, workflow_id: int):
        log.info(f"--- 工作流 {workflow_id} 開始執行 ---")
        has_failures = False
        try:
            self.db.update_workflow_status(workflow_id, 'running')
            steps = self.db.get_workflow_steps(workflow_id)
            if not steps:
                self.db.update_workflow_status(workflow_id, 'completed')
                return

            for step in steps:
                if step['status'] not in ['pending']:
                    if step['status'] == 'failed': has_failures = True
                    continue

                log.info(f"--> 開始執行步驟 {step['id']}: 指令 = {step['command']}")
                self.db.update_workflow_step_status(step_id=step['id'], status='running')

                handler = self._command_registry.get(step['command'])
                if not handler:
                    self.db.update_workflow_step_status(step_id=step['id'], status='failed', error_message=f"未知的指令: {step['command']}")
                    has_failures = True
                    continue

                try:
                    result = handler(self.db, **step['parameters'])
                    self.db.update_workflow_step_status(step_id=step['id'], status='completed', result=result)
                except Exception as e:
                    log.error(f"步驟 {step['id']} 執行失敗: {e}", exc_info=True)
                    self.db.update_workflow_step_status(step_id=step['id'], status='failed', error_message=str(e))
                    has_failures = True

            final_steps = self.db.get_workflow_steps(workflow_id)
            all_steps_completed = all(s['status'] == 'completed' for s in final_steps)

            final_status = 'completed' if all_steps_completed else 'completed_with_errors'
            self.db.update_workflow_status(workflow_id, final_status)

        except Exception as e:
            log.error(f"執行工作流 {workflow_id} 時發生嚴重錯誤: {e}", exc_info=True)
            self.db.update_workflow_status(workflow_id, 'failed')
        finally:
            log.info(f"--- 工作流 {workflow_id} 執行結束 ---")
