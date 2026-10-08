#!/usr/bin/env python3
"""
数据模型定义
定义API请求和响应的数据结构
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class BoundingBox(BaseModel):
    """边界框"""
    x1: float = Field(..., description="左上角x坐标")
    y1: float = Field(..., description="左上角y坐标")
    x2: float = Field(..., description="右下角x坐标")
    y2: float = Field(..., description="右下角y坐标")


class Detection(BaseModel):
    """单个检测结果"""
    class_id: int = Field(..., description="类别ID")
    class_name: str = Field(..., description="类别名称")
    confidence: float = Field(..., description="置信度")
    bbox: BoundingBox = Field(..., description="边界框")


class RiskAssessment(BaseModel):
    """图像火灾风险报告

    图像检测是单帧的，没有视频那套跨帧持续时长证据，
    因此按「可见证据强度」分级：明火 > 仅有烟雾、火烟共现、置信度、目标覆盖面积。
    """
    score: int = Field(0, description="风险评分 0-100")
    level: str = Field("无风险 - 未检测到异常", description="风险等级")
    reasons: List[str] = Field(default_factory=list, description="评分依据明细")
    advice: str = Field("", description="处置建议")
    fire_count: int = Field(0, description="火焰数量")
    smoke_count: int = Field(0, description="烟雾数量")
    max_confidence: float = Field(0.0, description="最高置信度")
    max_fire_area_ratio: float = Field(0.0, description="最大火焰框占画面比例")
    max_smoke_area_ratio: float = Field(0.0, description="最大烟雾框占画面比例")


class DetectionResult(BaseModel):
    """检测结果"""
    detection_id: str = Field(..., description="检测ID")
    image_path: Optional[str] = Field(None, description="图像路径")
    image_url: Optional[str] = Field(None, description="图像URL")
    detections: List[Detection] = Field(default_factory=list, description="检测结果列表")
    fire_count: int = Field(0, description="火焰数量")
    smoke_count: int = Field(0, description="烟雾数量")
    inference_time: float = Field(..., description="推理时间(ms)")
    image_width: int = Field(..., description="图像宽度")
    image_height: int = Field(..., description="图像高度")
    timestamp: datetime = Field(default_factory=datetime.now, description="检测时间")
    model_name: str = Field(..., description="使用的模型名称")
    confidence_threshold: float = Field(..., description="置信度阈值")
    iou_threshold: float = Field(..., description="IOU阈值")
    risk: Optional[RiskAssessment] = Field(None, description="火灾风险报告")


class DetectionHistory(BaseModel):
    """检测历史记录"""
    detection_id: str = Field(..., description="检测ID")
    image_path: str = Field(..., description="图像路径")
    fire_count: int = Field(0, description="火焰数量")
    smoke_count: int = Field(0, description="烟雾数量")
    total_detections: int = Field(0, description="总检测数量")
    inference_time: float = Field(..., description="推理时间(ms)")
    timestamp: datetime = Field(..., description="检测时间")
    model_name: str = Field(..., description="使用的模型名称")
    has_alert: bool = Field(False, description="是否有告警")
    alert_level: Optional[str] = Field(None, description="告警级别")


class ModelInfo(BaseModel):
    """模型信息"""
    name: str = Field(..., description="模型名称")
    version: str = Field(..., description="模型版本")
    path: str = Field(..., description="模型路径")
    size: str = Field(..., description="模型大小")
    description: str = Field("", description="模型描述")
    is_loaded: bool = Field(False, description="是否已加载")
    load_time: Optional[datetime] = Field(None, description="加载时间")


class AlertLevel(str, Enum):
    """告警级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Alert(BaseModel):
    """告警信息"""
    alert_id: str = Field(..., description="告警ID")
    detection_id: str = Field(..., description="检测ID")
    level: AlertLevel = Field(..., description="告警级别")
    message: str = Field(..., description="告警消息")
    fire_count: int = Field(0, description="火焰数量")
    smoke_count: int = Field(0, description="烟雾数量")
    timestamp: datetime = Field(default_factory=datetime.now, description="告警时间")
    is_read: bool = Field(False, description="是否已读")


class Statistics(BaseModel):
    """统计信息"""
    total_detections: int = Field(0, description="总检测次数")
    total_fire: int = Field(0, description="总火焰检测数")
    total_smoke: int = Field(0, description="总烟雾检测数")
    avg_inference_time: float = Field(0.0, description="平均推理时间(ms)")
    alert_count: int = Field(0, description="告警次数")
    detection_by_day: dict = Field(default_factory=dict, description="按天检测次数")
    detection_by_hour: dict = Field(default_factory=dict, description="按小时检测次数")
    # 下面四项用于「数据分析」页的趋势图：detection_by_* 只统计记录条数，
    # 画不出火/烟分离的趋势，故单独按类聚合目标数量
    fire_by_day: dict = Field(default_factory=dict, description="按天火焰目标数")
    smoke_by_day: dict = Field(default_factory=dict, description="按天烟雾目标数")
    fire_by_hour: dict = Field(default_factory=dict, description="按小时火焰目标数")
    smoke_by_hour: dict = Field(default_factory=dict, description="按小时烟雾目标数")


class SystemStatus(BaseModel):
    """系统状态"""
    status: str = Field("running", description="系统状态")
    uptime: float = Field(0.0, description="运行时间(秒)")
    model_loaded: bool = Field(False, description="模型是否加载")
    current_model: Optional[str] = Field(None, description="当前模型")
    gpu_available: bool = Field(False, description="GPU是否可用")
    gpu_memory_used: Optional[float] = Field(None, description="GPU显存使用(MB)")
    gpu_memory_total: Optional[float] = Field(None, description="GPU显存总量(MB)")
    cpu_usage: float = Field(0.0, description="CPU使用率")
    memory_usage: float = Field(0.0, description="内存使用率")
    disk_usage: float = Field(0.0, description="磁盘使用率")