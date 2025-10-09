# services/llm_service/model_manager.py

import ollama
import asyncio
import base64

class ModelManager:
    """
    一個專門用來管理 Ollama 模型的類別。
    它處理模型的下載、狀態追蹤和推論。
    """

    def __init__(self):
        """
        初始化 ModelManager。
        """
        try:
            self.client = ollama.Client()
            # 嘗試與 Ollama 服務進行基本通訊以確認其可用性
            self.client.list()
            print("成功連接到 Ollama 服務。")
        except Exception as e:
            print(f"錯誤：無法連接到 Ollama 服務。請確保 Ollama 正在運行。")
            print(f"詳細錯誤訊息: {e}")
            # 在無法連接的情況下，可能需要一個更優雅的處理方式，
            # 例如在一段時間後重試，或讓服務以受限模式啟動。
            # 目前，我們先將 client 設為 None。
            self.client = None

    def list_local_models(self):
        """
        返回本地 Ollama 環境中所有可用的模型列表。
        """
        if not self.client:
            return {"error": "Ollama 服務未連接。"}

        try:
            models = self.client.list()
            return models.get('models', [])
        except Exception as e:
            print(f"從 Ollama 獲取模型列表時出錯: {e}")
            return {"error": f"獲取模型列表失敗: {e}"}

    async def ensure_model_is_ready(self, model_name: str):
        """
        確保指定的模型已經準備好可供使用。
        如果模型不在本地，此方法將會異步下載它。
        這是「懶加載」的核心實現。
        """
        if not self.client:
            raise ConnectionError("無法連接到 Ollama 服務。")

        # 1. 檢查模型是否已經存在於本地
        local_models = self.list_local_models()
        is_local = any(model['name'] == model_name for model in local_models)

        if is_local:
            print(f"模型 '{model_name}' 已存在於本地，無需下載。")
            return True

        # 2. 如果模型不存在，則開始下載
        print(f"模型 '{model_name}' 不存在於本地，開始下載...")
        try:
            # ollama.pull 是個異步操作，但目前的 python-ollama 函式庫
            # 似乎將其包裝為同步阻塞呼叫。我們將以異步方式運行它，
            # 以免阻塞整個服務。
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # 使用預設的執行器
                lambda: self.client.pull(model_name)
            )
            print(f"成功下載模型 '{model_name}'。")
            return True
        except Exception as e:
            print(f"下載模型 '{model_name}' 時發生錯誤: {e}")
            raise IOError(f"下載模型 '{model_name}' 失敗。") from e

    async def generate_text(self, model_name: str, prompt: str):
        """
        使用指定的模型生成文字。
        在生成前，會先確保模型已經準備就緒。
        """
        if not self.client:
            raise ConnectionError("無法連接到 Ollama 服務。")

        # 確保模型可用（懶加載）
        await self.ensure_model_is_ready(model_name)

        print(f"正在使用模型 '{model_name}' 處理提示...")
        try:
            response = self.client.chat(
                model=model_name,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                    },
                ]
            )
            return response['message']['content']
        except Exception as e:
            print(f"使用模型 '{model_name}' 生成文字時發生錯誤: {e}")
            raise RuntimeError(f"模型推論失敗。") from e

    async def analyze_image(self, model_name: str, prompt: str, image_base64: str):
        """
        使用指定的多模態模型分析圖像。
        在分析前，會先確保模型已經準備就緒。
        """
        if not self.client:
            raise ConnectionError("無法連接到 Ollama 服務。")

        # 確保模型可用（懶加載）
        await self.ensure_model_is_ready(model_name)

        print(f"正在使用模型 '{model_name}' 分析圖片...")
        try:
            # 異步執行阻塞的 chat 呼叫
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=model_name,
                    messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                            'images': [image_base64]
                        }
                    ]
                )
            )
            return response['message']['content']
        except Exception as e:
            print(f"使用模型 '{model_name}' 分析圖片時發生錯誤: {e}")
            raise RuntimeError(f"圖片分析的模型推論失敗。") from e