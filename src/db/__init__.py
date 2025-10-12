# This file makes the 'db' directory a Python package.

# (Jules @ 2025-10-12) 將 initialize_database 提升到套件層級
# 這樣，其他模組就可以直接用 `from db import initialize_database` 來匯入
from .database import initialize_database
