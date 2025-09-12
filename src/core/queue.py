#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import redis
from rq import Queue

# --- Redis 連線設定 ---
# 這裡我們使用標準的本地 Redis 連線。
# 在生產環境中，這個 URL 可能會來自環境變數。
REDIS_URL = "redis://localhost:6379"

# --- 建立連線 ---
# `decode_responses=True` 確保從 Redis 讀取的鍵和值是字串，而不是位元組。
redis_conn = redis.from_url(REDIS_URL, decode_responses=True)

# --- 建立佇列 ---
# 我們為 AI 分析任務建立一個名為 'ai_analysis' 的專用佇列。
analysis_queue = Queue("ai_analysis", connection=redis_conn)

def get_redis_connection():
    """提供一個取得 redis 連線的函式，方便測試或直接操作。"""
    return redis_conn

def get_analysis_queue():
    """提供一個取得分析佇列的函式。"""
    return analysis_queue
