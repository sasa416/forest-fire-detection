#!/usr/bin/env python3
"""
配置文件
定义系统配置参数
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """系统配置"""
    
    # 基础配置
    APP_NAME: str = "森林火灾烟雾检测系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    # SQL 语句回显开关：仅排查数据库问题时才打开。
    # 不要再复用 DEBUG —— DEBUG 一经开启会把每条 SQL 都打到日志里，
    # 淹没真正的错误堆栈（本项目踩过坑）。
    SQL_ECHO: bool = False
    
    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # 模型配置
    # 注意：DEFAULT_MODEL 必须指向真正训练好的火灾模型（fire/smoke 两分类）
    # 不要填 "yolov8s"（那是 COCO 80 类原版，不含 fire/smoke 类别，会误报日常物体）
    MODEL_PATH: str = "./models/fire_smoke_v3.pt"
    DEFAULT_MODEL: str = "fire_smoke_v3"
    MODEL_DIR: str = "./models"
    
    # 检测配置
    # 说明：v3 模型 AP 偏低，conf 0.5 会大量漏检；imgsz 640 对远景烟雾（低对比、大范围）
    #     召回不足。二者组合是"火焰/烟雾只识别出一个"的主因，故下调 conf、提高 imgsz。
    DEFAULT_CONFIDENCE: float = 0.30
    DEFAULT_IOU_THRESHOLD: float = 0.45
    DEFAULT_IMAGE_SIZE: int = 960

    # ── 多尺度融合推理 ──
    # 实测：单尺度必然丢类（960 只出火、1280 只出烟），融合 960+1280 后两类同时恢复
    #      （fire 0.341 / smoke 0.302）。默认开启，关闭后退回单尺度。
    FUSION_ENABLED: bool = True
    # 640 必须保留：小尺度对大面积火焰响应最强（fire_max=0.415），
    # 去掉 640 后火焰置信度会从 0.415 掉到 0.341。
    # 960/1280 负责大范围浅色烟雾。三者融合同时拿到两类最优。
    MULTI_SCALE_SIZES: list = [640, 960, 1280]
    FUSION_IOU: float = 0.45            # YOLO 内部 NMS 的 IOU
    FUSION_CANDIDATE_CONF: float = 0.05  # 融合前候选下限，避免过早滤掉弱目标
    # 分类别阈值系数：浅色扩散型烟雾绝对置信度天然偏低，
    # smoke 按基准阈值的 70% 判定（conf=0.30 → smoke 实际 0.21），fire 保持基准。
    CLASS_CONF_RELAX: dict = {"fire": 1.0, "smoke": 0.7}
    
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./data/detection.db"
    
    # 上传配置
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_IMAGE_EXTENSIONS: set = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    ALLOWED_VIDEO_EXTENSIONS: set = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}
    
    # 告警配置
    ALERT_ENABLED: bool = True
    ALERT_CHANNELS: list = ["email", "sms", "dingtalk"]
    # 原阈值 fire>=3 / smoke>=5 在实际画面里几乎不可能达到，导致告警永不触发；
    # 现改为「检测到即告警」，误报由实时流的跨帧跟踪确认（track_confirm_hits）抑制。
    ALERT_RULES: dict = {
        "fire_count_threshold": 1,
        "smoke_count_threshold": 1,
        "confidence_threshold": 0.75,
        "alert_cooldown": 30,        # 秒，同一路流的告警冷却
        "track_confirm_hits": 3,     # 实时流：同一目标需连续 N 次推理命中才确认告警
    }
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"
    
    # CORS配置
    CORS_ORIGINS: list = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["*"]
    CORS_ALLOW_HEADERS: list = ["*"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 创建全局配置实例
settings = Settings()

# 确保目录存在
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.MODEL_DIR).mkdir(parents=True, exist_ok=True)
Path("./data").mkdir(parents=True, exist_ok=True)
Path("./logs").mkdir(parents=True, exist_ok=True)


def get_model_path(model_name: str = None) -> str:
    """获取模型路径"""
    if model_name is None:
        model_name = settings.DEFAULT_MODEL
    
    model_path = Path(settings.MODEL_DIR) / f"{model_name}.pt"
    if not model_path.exists():
        # 尝试其他扩展名
        for ext in ['.onnx', '.engine', '.tflite']:
            alt_path = Path(settings.MODEL_DIR) / f"{model_name}{ext}"
            if alt_path.exists():
                return str(alt_path)
        
        # 返回默认路径
        return str(model_path)
    
    return str(model_path)


def get_upload_path(filename: str) -> str:
    """获取上传文件路径"""
    return str(Path(settings.UPLOAD_DIR) / filename)


def get_result_path(detection_id: str, filename: str) -> str:
    """获取结果文件路径"""
    result_dir = Path("./static/results") / detection_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return str(result_dir / filename)