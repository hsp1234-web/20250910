import logging
import sqlite3
import sys
from pathlib import Path
import threading
import time
from queue import Queue, Empty

handler_log = logging.getLogger('db_log_handler_internal')
handler_log.propagate = False
if not handler_log.handlers:
    console_handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(asctime)s - [DBLogHandler] - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    handler_log.addHandler(console_handler)

DB_FILE = Path(__file__).parent / "tasks.db"

class DatabaseLogHandler(logging.Handler):
    def __init__(self, source: str):
        super().__init__()
        self.source = source
        self.log_queue = Queue(-1)

        self.db_writer_thread = threading.Thread(
            target=self._db_writer_loop,
            name="DBLogWriterThread",
            daemon=True
        )
        self.shutdown_event = threading.Event()
        self.db_writer_thread.start()

    def _db_writer_loop(self):
        conn = None
        while not self.shutdown_event.is_set() or not self.log_queue.empty():
            try:
                records_to_process = []
                try:
                    first_record = self.log_queue.get(block=True, timeout=0.1)
                    if first_record is None: # Shutdown signal
                        self.shutdown_event.set()
                        continue
                    records_to_process.append(first_record)
                except Empty:
                    continue

                while len(records_to_process) < 50:
                    try:
                        record = self.log_queue.get_nowait()
                        if record is None: # Shutdown signal
                            self.shutdown_event.set()
                            break
                        records_to_process.append(record)
                    except Empty:
                        break

                if not conn:
                    conn = self._get_db_connection_with_retry()

                if conn and records_to_process:
                    params_to_insert = []
                    for record in records_to_process:
                        log_source = record.name
                        message = self.format(record)
                        params_to_insert.append((log_source, record.levelname, message))

                    if params_to_insert:
                        self._execute_batch_insert(conn, params_to_insert)

            except Exception as e:
                handler_log.error(f"資料庫寫入執行緒發生未預期錯誤: {e}", exc_info=True)
                time.sleep(1)

        if conn:
            conn.close()

    def _get_db_connection_with_retry(self):
        for i in range(10):
            try:
                conn = sqlite3.connect(DB_FILE, timeout=10)
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                return conn
            except sqlite3.OperationalError as e:
                handler_log.warning(f"獲取資料庫連線失敗 (嘗試 {i+1}/10): {e}。將在1秒後重試...")
                time.sleep(1)
        handler_log.error("在多次重試後，依然無法建立資料庫連線。")
        return None

    def _execute_batch_insert(self, conn, params):
        sql = "INSERT INTO system_logs (source, level, message) VALUES (?, ?, ?)"
        for i in range(5):
            try:
                with conn:
                    conn.executemany(sql, params)
                return
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) or "no such table" in str(e):
                    handler_log.warning(f"資料庫操作錯誤 '{e}'，正在重試 (嘗試 {i+1}/5)...")
                    time.sleep(0.5 if "no such table" in str(e) else 0.2)
                    continue
                else:
                    handler_log.error(f"執行批次插入時發生資料庫錯誤: {e}", exc_info=True)
                    return
        handler_log.error("在多次重試後，資料庫依然鎖定或表格不存在，此批次日誌遺失。")

    def emit(self, record: logging.LogRecord):
        self.log_queue.put(record)

    def close(self):
        self.log_queue.put(None)
        self.db_writer_thread.join(timeout=5)
        super().close()
