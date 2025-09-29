# poc/bond_data_service_v2/globals.py
# 繁體中文註解：全域共享狀態模組

from asyncio import Queue
from pathlib import Path
from typing import List, Optional

# 導入新的服務層和倉儲層
from .repository import DataRepository
from .service import StressIndexService

# --- 路徑常數 ---
STATIC_DIR = Path(__file__).parent.parent.parent / "src" / "static"
HTML_DIR = Path(__file__).parent.parent.parent / "src" / "static"

# --- 全域實例 ---
# 這些變數將在 main.py 的 lifespan 事件中被初始化
data_repository: Optional[DataRepository] = None
stress_index_service: Optional[StressIndexService] = None
sse_connections: List[Queue] = []