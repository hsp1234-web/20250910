# src/db/__init__.py

# (Jules @ 2025-10-12) 修正啟動器 API 匹配問題
# 啟動器期望呼叫 initialize_database.initialize()，而不是直接呼叫函式。
# 因此，我們建立一個符合此介面的物件。

from . import database

class _InitializeHelper:
    def initialize(self):
        """
        呼叫真正的資料庫初始化函式。
        """
        database.initialize_database()

# 將這個 helper 物件的實例命名為 initialize_database，以便啟動器可以
# 透過 `from db import initialize_database` 找到它，並呼叫 .initialize() 方法。
initialize_database = _InitializeHelper()