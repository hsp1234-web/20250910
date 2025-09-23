# -*- coding: utf-8 -*-
# services/transcription_service/main.py
import time
import logging
import torch
from pathlib import Path
from opencc import OpenCC
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

# --- 日誌設定 ---
# 將日誌訊息導向標準錯誤流，以便在服務日誌中查看
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
log = logging.getLogger('transcription_service')

# --- 繁簡轉換器 ---
CC = OpenCC('s2t')

# --- 核心轉錄邏輯 (從原始腳本遷移) ---
class Transcriber:
    """
    封裝 faster-whisper 模型的核心轉錄功能的類別。
    """
    def __init__(self, model_size="large-v3"):
        self.model_size = model_size
        self.model = self._load_model()

    def _load_model(self):
        """在服務啟動時載入 faster-whisper 模型。"""
        log.info(f"準備載入 '{self.model_size}' 模型...")
        # 根據環境自動選擇計算裝置和類型
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        log.info(f"裝置: {device}, 計算類型: {compute_type}")

        start_time = time.time()
        try:
            from faster_whisper import WhisperModel
            # 模型會在初始化時自動下載 (如果不存在)
            model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
            duration = time.time() - start_time
            log.info(f"✅ 成功載入 '{self.model_size}' 模型到 {device.upper()}！耗時: {duration:.2f} 秒。")
            return model
        except ImportError as e:
            log.critical(f"❌ 模型載入失敗：缺少 'faster_whisper' 或 'torch' 模組。請確認 requirements.txt 已正確安裝。")
            raise e
        except Exception as e:
            log.critical(f"❌ 載入 '{self.model_size}' 模型時發生未預期錯誤: {e}", exc_info=True)
            raise e

    def transcribe(self, audio_path: str, language: str = None, beam_size: int = 5) -> str:
        """
        執行音訊轉錄，並將完整的轉錄稿作為單一字串返回。
        """
        try:
            log.info(f"模型載入完成，開始轉錄檔案: {audio_path}")

            segments, info = self.model.transcribe(audio_path, beam_size=beam_size, language=language)

            detected_lang_msg = f"'{info.language}' (機率: {info.language_probability:.2f})"
            if language:
                log.info(f"🌍 使用者指定語言: '{language}'，模型偵測到 {detected_lang_msg}")
            else:
                log.info(f"🌍 未指定語言，模型自動偵測到 {detected_lang_msg}")

            full_transcript = []
            for segment in segments:
                # 將 whisper 偵測到的簡體中文轉換為繁體中文
                text_traditional = CC.convert(segment.text)
                full_transcript.append(text_traditional)

            log.info(f"✅ 檔案轉錄完成: {audio_path}")
            # 將所有片段合併成一個完整的文字稿
            return "".join(full_transcript)

        except Exception as e:
            log.error(f"❌ 轉錄過程中發生錯誤: {e}", exc_info=True)
            # 向上拋出異常，讓 API 端點可以捕捉並回傳適當的 HTTP 錯誤
            raise e

# --- FastAPI 應用程式設定 ---
app = FastAPI(
    title="語音轉錄微服務",
    description="一個接收音訊檔案路徑並回傳轉錄文字的 API 服務。",
    version="1.0.0",
)

# 這個全域變數將在服務啟動時被實例化
transcriber_instance: Transcriber | None = None

@app.on_event("startup")
def startup_event():
    """應用程式啟動時執行的異步函數，用於載入 AI 模型。"""
    global transcriber_instance
    log.info("伺服器啟動程序開始：準備載入轉錄模型...")
    # 從環境變數讀取模型大小，若未設定則使用預設值
    model_size = os.environ.get("TRANSCRIPTION_MODEL_SIZE", "large-v3")
    transcriber_instance = Transcriber(model_size=model_size)
    log.info("✅ 伺服器啟動完成，模型已載入並準備就緒。")

# --- API 請求與回應模型 ---
class TranscriptionRequest(BaseModel):
    audio_path: str
    language: str | None = None
    beam_size: int = 5

class TranscriptionResponse(BaseModel):
    transcript: str

class HealthResponse(BaseModel):
    status: str
    message: str
    model_loaded: bool

# --- API 端點 ---
@app.get("/health", response_model=HealthResponse, summary="健康檢查")
def health_check():
    """
    提供服務的健康狀況。如果模型已成功載入，則回報為健康。
    """
    is_model_loaded = transcriber_instance is not None
    if is_model_loaded:
        return {"status": "ok", "message": "服務運行中且模型已載入。", "model_loaded": True}
    else:
        return {"status": "loading", "message": "服務正在啟動，模型載入中...", "model_loaded": False}

@app.post("/api/v1/transcribe", response_model=TranscriptionResponse, summary="執行語音轉錄")
def run_transcription(request: TranscriptionRequest):
    """
    接收一個包含音訊檔案路徑的請求，執行轉錄並返回結果。
    這是一個同步 (阻塞) 的操作。
    """
    if not transcriber_instance:
        log.error("收到轉錄請求，但模型尚未準備好。")
        raise HTTPException(status_code=503, detail="服務尚未完全啟動，模型正在載入中，請稍後再試。")

    audio_file = Path(request.audio_path)
    if not audio_file.exists() or not audio_file.is_file():
        log.warning(f"請求的音訊檔案不存在: {request.audio_path}")
        raise HTTPException(status_code=404, detail=f"音訊檔案不存在或不是一個有效的檔案: {request.audio_path}")

    try:
        log.info(f"開始處理轉錄請求: {request.audio_path}")
        transcript_text = transcriber_instance.transcribe(
            audio_path=request.audio_path,
            language=request.language,
            beam_size=request.beam_size
        )
        log.info(f"成功完成轉錄請求: {request.audio_path}")
        return TranscriptionResponse(transcript=transcript_text)
    except Exception as e:
        # 捕捉來自 Transcriber 的所有潛在錯誤
        log.critical(f"處理請求 {request.audio_path} 時發生無法恢復的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理音訊檔案時發生內部伺服器錯誤: {str(e)}")
