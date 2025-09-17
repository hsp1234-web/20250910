import logging
from typing import List, Dict, Any

class ApiKey:
    """一個簡單的類別，用於儲存 API 金鑰及其名稱。"""
    def __init__(self, key_value: str, name: str):
        self.key = key_value
        self.name = name

class GeminiManager:
    """
    管理 Google Gemini API 金鑰。
    在新的非同步架構下，此管理器的職責被大幅簡化。
    它不再管理金鑰的租借或執行 API 呼叫，僅負責在初始化時載入
    所有 API 金鑰，並提供一個方法來取得所有可用金鑰的列表。
    """
    def __init__(self, api_keys: List[Dict[str, str]]):
        """
        初始化 GeminiManager。

        Args:
            api_keys (List[Dict[str, str]]):
                一個包含 API 金鑰資訊的字典列表。
                每個字典應包含 'value' (金鑰值) 和 'name' (金鑰的可讀名稱)。
        """
        if not api_keys:
            raise ValueError("API 金鑰列表不可為空。")

        self.api_keys = [ApiKey(key_value=k['value'], name=k['name']) for k in api_keys]
        logging.info(f"Gemini 管理器已初始化，共載入 {len(self.api_keys)} 組 API 金鑰。")

    def get_all_keys(self) -> List[ApiKey]:
        """
        取得所有已載入的 API 金鑰物件。

        Returns:
            List[ApiKey]: 一個包含所有 ApiKey 物件的列表。
        """
        return self.api_keys
