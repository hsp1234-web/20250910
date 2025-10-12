# src/core/workflow_engine.py
import logging
import json
from typing import Dict, Any, Callable

from src.db.client import DBClient
# (Jules @ 2025-10-12) 匯入指令處理函式
from .workflow_commands import command_download_and_extract, command_analyze_text

log = logging.getLogger(__name__)

class WorkflowEngine:
    """
    負責執行宣告式工作流的引擎。
    """
    def __init__(self, db_client: DBClient):
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
        """
        註冊一個指令及其處理函式。
        :param command_name: 指令的唯一名稱。
        :param handler: 一個函式，接收 (db_client, **parameters) 並回傳結果。
        """
        if command_name in self._command_registry:
            log.warning(f"指令 '{command_name}' 已被註冊，將被覆寫。")
        self._command_registry[command_name] = handler
        log.info(f"指令 '{command_name}' 已成功註冊。")

    def run_workflow(self, workflow_id: int):
        """
        執行指定 ID 的工作流。
        這是一個同步函式，通常會在一個背景任務中被呼叫。
        """
        log.info(f"--- 工作流 {workflow_id} 開始執行 ---")
        try:
            # 1. 將工作流總體狀態設定為 'running'
            self.db.update_workflow_status(workflow_id, 'running')

            # 2. 獲取所有待處理的步驟
            steps = self.db.get_workflow_steps(workflow_id)
            if not steps:
                log.warning(f"工作流 {workflow_id} 中沒有任何步驟，執行結束。")
                self.db.update_workflow_status(workflow_id, 'completed')
                return

            # 3. 依序執行每一個步驟
            for step in steps:
                # 跳過已完成或已失敗的步驟，以支援從中斷處恢復
                if step['status'] not in ['pending']:
                    log.info(f"跳過步驟 {step['id']} (指令: {step['command']})，因其狀態為 '{step['status']}'。")
                    continue

                log.info(f"--> 開始執行步驟 {step['id']}: 指令 = {step['command']}")
                self.db.update_workflow_step_status(step_id=step['id'], status='running')

                handler = self._command_registry.get(step['command'])
                if not handler:
                    raise ValueError(f"未知的指令: {step['command']}")

                try:
                    # 執行指令
                    result = handler(self.db, **step['parameters'])
                    log.info(f"<-- 步驟 {step['id']} 執行成功。")
                    self.db.update_workflow_step_status(
                        step_id=step['id'],
                        status='completed',
                        result=result
                    )
                except Exception as e:
                    log.error(f"步驟 {step['id']} 執行失敗: {e}", exc_info=True)
                    self.db.update_workflow_step_status(
                        step_id=step['id'],
                        status='failed',
                        error_message=str(e)
                    )
                    # 一旦有步驟失敗，就終止整個工作流
                    raise Exception(f"工作流 {workflow_id} 因步驟 {step['id']} 失敗而終止。")

            # 4. 如果所有步驟都成功，將工作流總體狀態設定為 'completed'
            log.info(f"工作流 {workflow_id} 中的所有步驟均已成功執行。")
            self.db.update_workflow_status(workflow_id, 'completed')

        except Exception as e:
            log.error(f"執行工作流 {workflow_id} 時發生嚴重錯誤: {e}", exc_info=True)
            self.db.update_workflow_status(workflow_id, 'failed')
        finally:
            log.info(f"--- 工作流 {workflow_id} 執行結束 ---")