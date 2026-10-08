#!/usr/bin/env python3
"""
业务服务层
实现检测、模型管理、历史记录等核心业务逻辑
"""

import os
import time
import uuid
import asyncio
from pathlib import Path
from typing import List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import json

import torch
import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from loguru import logger

from app.models import (
    DetectionResult, Detection, BoundingBox, DetectionHistory,
    ModelInfo, Statistics, RiskAssessment,
)
from app.config import settings, get_model_path, get_upload_path, get_result_path
from app.inference import fuse_multiscale, draw_detections, warmup
from app.risk import assess_image_risk
from app import runtime_config

# 数据库模型
Base = declarative_base()


class DetectionRecord(Base):
    """检测记录表"""
    __tablename__ = 'detection_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    detection_id = Column(String(50), unique=True, nullable=False)
    image_path = Column(String(500))
    fire_count = Column(Integer, default=0)
    smoke_count = Column(Integer, default=0)
    total_detections = Column(Integer, default=0)
    inference_time = Column(Float)
    model_name = Column(String(100))
    confidence_threshold = Column(Float)
    iou_threshold = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class AlertRecord(Base):
    """告警记录表"""
    __tablename__ = 'alert_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(50), unique=True, nullable=False)
    detection_id = Column(String(50))
    level = Column(String(20))
    message = Column(Text)
    fire_count = Column(Integer, default=0)
    smoke_count = Column(Integer, default=0)
    is_read = Column(Boolean, default=False)
    # 处置状态：pending 待处置 / confirmed 已确认 / ignored 已忽略
    status = Column(String(20), default="pending", index=True)
    handled_by = Column(String(100), default="")
    handled_at = Column(DateTime, nullable=True)
    handled_note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


# 数据库连接
# check_same_thread=False：实时流告警回调发生在独立读取线程里，必须允许跨线程使用连接
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建表
Base.metadata.create_all(bind=engine)


def _ensure_alert_columns() -> None:
    """轻量迁移：为已存在的 alert_records 表补齐后续新增的列

    SQLAlchemy 的 create_all 不会给已存在的表加列，
    线上历史库必须通过 ALTER TABLE 补字段，否则查询会因缺列报错。
    """
    from sqlalchemy import text
    needed = {
        "status": "VARCHAR(20) DEFAULT 'pending'",
        "handled_by": "VARCHAR(100) DEFAULT ''",
        "handled_at": "DATETIME",
        "handled_note": "TEXT DEFAULT ''",
    }
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(alert_records)")).fetchall()
            existing = {row[1] for row in rows}
            for col, ddl in needed.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE alert_records ADD COLUMN {col} {ddl}"))
                    logger.info(f"alert_records 补充字段: {col}")
            conn.execute(text(
                "UPDATE alert_records SET status = 'pending' "
                "WHERE status IS NULL OR status = ''"
            ))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"alert_records 迁移失败: {exc}")


_ensure_alert_columns()


class DetectionService:
    """检测服务"""

    # 严格白名单：只允许 fire 和 smoke，任何其他类别一律丢弃
    VALID_CLASSES = {'fire', 'smoke'}

    def __init__(self):
        self.model = None
        self.model_name = None
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"使用设备: {self.device}")

    def _infer_fused(self, image, confidence, iou_threshold, final_threshold=True,
                     candidate_conf=None):
        """统一推理入口：多尺度融合（settings.FUSION_ENABLED 可回退单尺度）

        所有检测入口都必须经过这里，否则会出现"某个入口还是漏检"的不一致行为。
        :param candidate_conf: 候选下限覆盖值；视频检测需要保留低置信弱框做跨帧跟踪，
                               此时传入 LOW_CONF_FLOOR 而不是全局的更低下限。
        """
        if candidate_conf is None:
            candidate_conf = settings.FUSION_CANDIDATE_CONF
        if not settings.FUSION_ENABLED:
            from app.inference import raw_detect
            return raw_detect(
                self.model, image, runtime_config.default_image_size(),
                min(candidate_conf, confidence), iou_threshold,
                device=self.device, valid_classes=self.VALID_CLASSES,
            )
        return fuse_multiscale(
            self.model, image,
            scales=settings.MULTI_SCALE_SIZES,
            confidence=confidence,
            iou=iou_threshold,
            device=self.device,
            class_relax=settings.CLASS_CONF_RELAX,
            valid_classes=self.VALID_CLASSES,
            candidate_conf=candidate_conf,
            final_threshold=final_threshold,
        )

    @staticmethod
    def _to_detections(fused):
        """融合结果 -> (Detection 列表, fire 数量, smoke 数量)"""
        detections = []
        fire_count = 0
        smoke_count = 0
        for d in fused:
            cls_name = d["cls"]
            x1, y1, x2, y2 = d["xyxy"]
            detections.append(Detection(
                class_id=0 if cls_name == 'fire' else 1,
                class_name=cls_name,
                confidence=d["conf"],
                bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
            ))
            if cls_name == 'fire':
                fire_count += 1
            elif cls_name == 'smoke':
                smoke_count += 1
        return detections, fire_count, smoke_count
    
    async def load_model(self, model_name: str = None):
        """加载模型"""
        if model_name is None:
            model_name = settings.DEFAULT_MODEL
        
        model_path = get_model_path(model_name)
        logger.info(f"加载模型: {model_path}")
        
        try:
            self.model = YOLO(model_path)
            self.model_name = model_name
            self.model.to(self.device)
            logger.info(f"模型加载成功: {model_name}")
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

        # 预热：CUDA 首次推理要跑 cuDNN autotune，实测冷启动 4861ms、稳态仅 11~28ms。
        # 不前移这段开销的话，用户首次检测就要白等 3.5s+（即"推理耗时异常"的根因）。
        try:
            warmup(self.model, device=self.device,
                   imgsz=settings.DEFAULT_IMAGE_SIZE, rounds=2)
            logger.info("模型预热完成（已消除首次推理的冷启动开销）")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"模型预热失败（不影响功能）: {e}")
    
    async def detect_image(self, image_path: str, confidence: float = None, iou_threshold: float = None) -> DetectionResult:
        """图像检测"""
        if self.model is None:
            await self.load_model()

        # 默认值走运行时配置（管理员在「系统设置」改的值优先于 .env）
        if confidence is None:
            confidence = runtime_config.default_confidence()
        if iou_threshold is None:
            iou_threshold = runtime_config.default_iou()

        # 读取图像
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法读取图像: {image_path}")

        image_height, image_width = image.shape[:2]

        # 执行检测（放到线程池，避免阻塞事件循环拖慢前端轮询）
        # 多尺度融合：单尺度必然丢一类，融合后 fire/smoke 同时召回
        start_time = time.time()
        fused = await asyncio.to_thread(
            self._infer_fused, image, confidence, iou_threshold
        )
        inference_time = (time.time() - start_time) * 1000  # 转换为毫秒

        # 解析结果 — 严格白名单过滤，只保留 fire/smoke
        detections, fire_count, smoke_count = self._to_detections(fused)

        # 生成检测ID
        detection_id = f"det_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # 保存标注结果图（融合后没有单一 results 对象，改为按融合框自绘）
        result_image = draw_detections(image, fused)
        result_path = get_result_path(detection_id, "result.jpg")
        cv2.imwrite(result_path, result_image)

        # 构建结果
        result = DetectionResult(
            detection_id=detection_id,
            image_path=image_path,
            image_url=f"/static/results/{detection_id}/result.jpg",
            detections=detections,
            fire_count=fire_count,
            smoke_count=smoke_count,
            inference_time=inference_time,
            image_width=image_width,
            image_height=image_height,
            timestamp=datetime.now(),
            model_name=self.model_name or settings.DEFAULT_MODEL,
            confidence_threshold=confidence,
            iou_threshold=iou_threshold,
            risk=RiskAssessment(**assess_image_risk(fused, image_width, image_height)),
        )

        # 检查是否需要告警
        await self._check_alert(result)

        return result
    
    async def detect_video_stream(self, video_path: str, confidence: float = None, 
                                   iou_threshold: float = None, frame_interval: int = 30) -> AsyncGenerator[bytes, None]:
        """视频流检测"""
        if self.model is None:
            await self.load_model()
        
        # 默认值走运行时配置（管理员在「系统设置」改的值优先于 .env）
        if confidence is None:
            confidence = runtime_config.default_confidence()
        if iou_threshold is None:
            iou_threshold = runtime_config.default_iou()
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频: {video_path}")
        
        frame_count = 0
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                
                # 按间隔处理帧
                if frame_count % frame_interval != 0:
                    continue
                
                # 执行检测
                results = self.model(frame, conf=confidence, iou=iou_threshold,
                                     imgsz=runtime_config.default_image_size(),
                                     verbose=False, device=self.device)
                
                # 绘制结果
                result_frame = results[0].plot()
                
                # 转换为JPEG
                _, buffer = cv2.imencode('.jpg', result_frame)
                frame_bytes = buffer.tobytes()
                
                # 返回帧
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                # 控制帧率
                await asyncio.sleep(0.01)
        
        finally:
            cap.release()
    
    @staticmethod
    def _iou(box_a, box_b):
        """计算两个 [x1,y1,x2,y2] 框的 IOU"""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0

    def detect_video_file(self, video_path: str, confidence: float = None,
                          iou_threshold: float = None, frame_interval: int = 3) -> dict:
        """视频文件检测：低置信候选框缓存 + IOU 跨帧跟踪 + 持续时长风险判定

        两个模块分离：
        1. 模型推理：每帧跑模型，输出所有检测框（含低置信 0.1~0.25）
        2. 时序后处理：IOU 跟踪同一目标，统计持续帧数，基于持续时长判定风险
        """
        if self.model is None:
            self.model = YOLO(get_model_path(settings.DEFAULT_MODEL))
            self.model_name = settings.DEFAULT_MODEL
            self.model.to(self.device)
            logger.info(f"视频检测时延迟加载模型: {self.model_name}")

        # 默认值走运行时配置（管理员在「系统设置」改的值优先于 .env）
        if confidence is None:
            confidence = runtime_config.default_confidence()
        if iou_threshold is None:
            iou_threshold = runtime_config.default_iou()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps

        _static_root = Path(__file__).parent.parent / "static"
        out_dir = _static_root / f"video_{int(time.time())}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── 跟踪器状态 ──
        # 每个 track: {cls, bbox, conf_sum, conf_max, conf_min, hit_count, last_frame, first_frame, boxes_history}
        tracks = []
        TRACK_IOU_THRESH = 0.3   # 跨帧 IOU 匹配阈值
        LOW_CONF_FLOOR = 0.10    # 低置信候选框下限
        TRACK_EXPIRE_FRAMES = 10 # 超过 N 帧未匹配则过期

        frame_idx = 0
        sampled_frames = 0
        all_frame_results = []   # 每帧的预测结果（含低置信）

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % frame_interval == 0:
                sampled_frames += 1
                t0 = time.time()
                # 多尺度融合取全部候选框（final_threshold=False 保留低置信弱框，
                # 交给下面的跨帧跟踪做时序确认）。单尺度会整类漏掉烟雾。
                fused = self._infer_fused(
                    frame, LOW_CONF_FLOOR, iou_threshold,
                    final_threshold=False, candidate_conf=LOW_CONF_FLOOR,
                )
                infer_ms = round((time.time() - t0) * 1000, 1)

                # 提取本帧所有检测框
                frame_dets = [{
                    'cls': d['cls'],
                    'bbox': list(d['xyxy']),
                    'conf': d['conf'],
                    'matched': False,
                } for d in fused]

                all_frame_results.append({
                    'frame': frame_idx,
                    'time': round(frame_idx / fps, 2),
                    'infer_ms': infer_ms,
                    'detections': [{'cls': d['cls'], 'conf': round(d['conf'], 3),
                                    'bbox': [round(v, 1) for v in d['bbox']]} for d in frame_dets]
                })

                # ── IOU 跟踪匹配 ──
                # 尝试将本帧检测框匹配到已有 track
                for det in frame_dets:
                    best_iou = 0
                    best_track = None
                    for track in tracks:
                        if track['cls'] != det['cls']:
                            continue
                        if frame_idx - track['last_frame'] > TRACK_EXPIRE_FRAMES:
                            continue
                        iou_val = self._iou(det['bbox'], track['bbox'])
                        if iou_val > best_iou:
                            best_iou = iou_val
                            best_track = track

                    if best_track and best_iou >= TRACK_IOU_THRESH:
                        # 匹配成功，更新 track
                        best_track['bbox'] = det['bbox']
                        best_track['conf_sum'] += det['conf']
                        best_track['conf_max'] = max(best_track['conf_max'], det['conf'])
                        best_track['conf_min'] = min(best_track['conf_min'], det['conf'])
                        best_track['hit_count'] += 1
                        best_track['last_frame'] = frame_idx
                        best_track['above_thresh'] = best_track['above_thresh'] or (det['conf'] >= confidence)
                    else:
                        # 新 track
                        tracks.append({
                            'cls': det['cls'],
                            'bbox': det['bbox'],
                            'conf_sum': det['conf'],
                            'conf_max': det['conf'],
                            'conf_min': det['conf'],
                            'hit_count': 1,
                            'first_frame': frame_idx,
                            'last_frame': frame_idx,
                            'above_thresh': det['conf'] >= confidence
                        })

            frame_idx += 1

        cap.release()

        # ── 分析跟踪结果 ──
        # 只保留 ≥2 帧的 track（单帧不算跟踪）
        valid_tracks = [t for t in tracks if t['hit_count'] >= 2]

        fire_tracks = [t for t in valid_tracks if t['cls'] == 'fire']
        smoke_tracks = [t for t in valid_tracks if t['cls'] == 'smoke']

        # 高置信 track（单帧 ≥ threshold）
        high_conf_tracks = [t for t in valid_tracks if t['above_thresh']]
        # 低置信但持续 track（单帧 < threshold 但持续 ≥5 帧）
        sustained_low_conf_tracks = [t for t in valid_tracks
                                     if not t['above_thresh'] and t['hit_count'] >= 5]

        # 统计所有有效检出帧（含高置信 + 跟踪确认的低置信）
        confirmed_frame_indices = set()
        fire_total = 0
        smoke_total = 0
        max_fire_conf = 0.0
        max_smoke_conf = 0.0

        for t in high_conf_tracks:
            if t['cls'] == 'fire':
                fire_total += t['hit_count']
                max_fire_conf = max(max_fire_conf, t['conf_max'])
            else:
                smoke_total += t['hit_count']
                max_smoke_conf = max(max_smoke_conf, t['conf_max'])
            # 高置信 track 的所有帧都算检出帧
            for f_idx in range(t['first_frame'], t['last_frame'] + 1, frame_interval):
                confirmed_frame_indices.add(f_idx)

        for t in sustained_low_conf_tracks:
            # 持续低置信 track 也算有效检出
            if t['cls'] == 'fire':
                fire_total += t['hit_count']
                max_fire_conf = max(max_fire_conf, t['conf_max'])
            else:
                smoke_total += t['hit_count']
                max_smoke_conf = max(max_smoke_conf, t['conf_max'])
            for f_idx in range(t['first_frame'], t['last_frame'] + 1, frame_interval):
                confirmed_frame_indices.add(f_idx)

        detected_frames = len(confirmed_frame_indices)

        # ── 构建 alert_moments（从 all_frame_results 中提取有检出的帧）──
        # 被跟踪确认的帧即使单帧置信度低于 threshold 也算有效检出，
        # 否则会出现"模型看见了但统计里没有"的漏报。
        track_confirmed_frames = set()
        for t in valid_tracks:
            for f_idx in range(t['first_frame'], t['last_frame'] + 1, frame_interval):
                track_confirmed_frames.add(f_idx)

        alert_moments = []
        result_frames = []
        for fr in all_frame_results:
            if fr['detections']:
                # 优先取 ≥ threshold 的框；若没有，但该帧被跟踪确认，则纳入低置信候选
                relevant = [d for d in fr['detections'] if d['conf'] >= confidence]
                confirmed = bool(relevant)
                if not relevant and fr['frame'] in track_confirmed_frames:
                    relevant = [d for d in fr['detections'] if d['conf'] >= LOW_CONF_FLOOR]
                    confirmed = bool(relevant)
                if relevant:
                    fire_c = sum(1 for d in relevant if d['cls'] == 'fire')
                    smoke_c = sum(1 for d in relevant if d['cls'] == 'smoke')
                    fire_max = max((d['conf'] for d in relevant if d['cls'] == 'fire'), default=0)
                    smoke_max = max((d['conf'] for d in relevant if d['cls'] == 'smoke'), default=0)
                    alert_moments.append({
                        "frame": fr['frame'],
                        "time": fr['time'],
                        "fire": fire_c,
                        "smoke": smoke_c,
                        "fire_conf": fire_max,
                        "smoke_conf": smoke_max,
                        "confirmed": confirmed,
                        "inference_time": fr['infer_ms']
                    })

        # 保存标注帧（取有高置信检出的帧）
        for fr in all_frame_results:
            high_conf_dets = [d for d in fr['detections'] if d['conf'] >= confidence]
            if high_conf_dets:
                # 重跑一次带标注的图
                cap2 = cv2.VideoCapture(video_path)
                cap2.set(cv2.CAP_PROP_POS_FRAMES, fr['frame'])
                ret2, frame2 = cap2.read()
                cap2.release()
                if ret2:
                    fused2 = self._infer_fused(frame2, confidence, iou_threshold)
                    annotated = draw_detections(frame2, fused2)
                    fname = f"det_{fr['frame']:04d}.jpg"
                    cv2.imwrite(str(out_dir / fname), annotated)
                    result_frames.append(f"/static/{out_dir.name}/{fname}")

        # ── 风险评估：基于跟踪目标持续时长 ──
        risk_score = 0
        risk_reasons = []

        # 1. 跟踪目标持续时长（核心）
        max_track_duration_sec = 0
        longest_track = None
        for t in valid_tracks:
            dur = (t['last_frame'] - t['first_frame']) / fps
            if dur > max_track_duration_sec:
                max_track_duration_sec = dur
                longest_track = t

        if longest_track:
            dur = max_track_duration_sec
            cls = longest_track['cls']
            hits = longest_track['hit_count']
            cmax = longest_track['conf_max']
            if dur >= 1.0:
                risk_score += 40
                risk_reasons.append(f"{cls}目标持续{dur:.1f}s/{hits}帧(+40)")
            elif dur >= 0.5:
                risk_score += 25
                risk_reasons.append(f"{cls}目标持续{dur:.1f}s/{hits}帧(+25)")

        # 2. 多目标跟踪贡献
        if len(smoke_tracks) >= 3:
            risk_score += 20
            risk_reasons.append(f"跟踪到{len(smoke_tracks)}个烟雾目标(+20)")
        elif len(smoke_tracks) >= 1:
            risk_score += 10
            risk_reasons.append(f"跟踪到{len(smoke_tracks)}个烟雾目标(+10)")
        if len(fire_tracks) >= 1:
            risk_score += 15
            risk_reasons.append(f"跟踪到{len(fire_tracks)}个火焰目标(+15)")

        # 3. 持续低置信目标贡献（模型不确定但目标持续存在）
        if len(sustained_low_conf_tracks) >= 1:
            risk_score += 20
            risk_reasons.append(f"{len(sustained_low_conf_tracks)}个低置信但持续≥5帧的目标(+20)")

        # 4. 最高置信度贡献
        if max_fire_conf > 0.5:
            risk_score += 15
            risk_reasons.append(f"火焰高置信{max_fire_conf:.0%}(+15)")
        if max_smoke_conf > 0.5:
            risk_score += 10
            risk_reasons.append(f"烟雾高置信{max_smoke_conf:.0%}(+10)")

        risk_score = min(risk_score, 100)

        # ── 直接升级规则：跟踪目标持续 ≥1 秒 → 高风险 ──
        if max_track_duration_sec >= 2.0:
            risk_score = max(risk_score, 90)
            risk_reasons.append(f"目标持续{max_track_duration_sec:.1f}s≥2s→确认火灾")
        elif max_track_duration_sec >= 1.0:
            risk_score = max(risk_score, 75)
            risk_reasons.append(f"目标持续{max_track_duration_sec:.1f}s≥1s→高风险")
        elif max_track_duration_sec >= 0.5:
            risk_score = max(risk_score, 50)
            risk_reasons.append(f"目标持续{max_track_duration_sec:.1f}s≥0.5s→中风险")

        if risk_score >= 70:
            risk_level = "高风险 - 确认火灾"
        elif risk_score >= 40:
            risk_level = "中风险 - 疑似火灾"
        elif risk_score > 15:
            risk_level = "低风险 - 需人工确认"
        else:
            risk_score = 0
            risk_level = "无风险 - 未检测到异常"
            risk_reasons = []

        # ── 跟踪目标详情 ──
        track_details = []
        for i, t in enumerate(sorted(valid_tracks, key=lambda x: x['hit_count'], reverse=True)):
            dur = (t['last_frame'] - t['first_frame']) / fps
            avg_conf = t['conf_sum'] / t['hit_count']
            track_details.append({
                "id": i + 1,
                "class": t['cls'],
                "hit_count": t['hit_count'],
                "duration_sec": round(dur, 2),
                "first_frame": t['first_frame'],
                "last_frame": t['last_frame'],
                "conf_avg": round(avg_conf, 3),
                "conf_max": round(t['conf_max'], 3),
                "conf_min": round(t['conf_min'], 3),
                "above_thresh": t['above_thresh']
            })

        return {
            "total_frames": total_frames,
            "sampled_frames": sampled_frames,
            "detected_frames": detected_frames,
            "fire_total": fire_total,
            "smoke_total": smoke_total,
            "max_fire_conf": round(max_fire_conf, 3),
            "max_smoke_conf": round(max_smoke_conf, 3),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "duration": round(duration, 1),
            "fps": round(fps, 1),
            "width": width,
            "height": height,
            # 跟踪统计
            "total_tracks": len(valid_tracks),
            "fire_tracks": len(fire_tracks),
            "smoke_tracks": len(smoke_tracks),
            "sustained_low_conf_tracks": len(sustained_low_conf_tracks),
            "max_track_duration_sec": round(max_track_duration_sec, 2),
            "detection_ratio": round(detected_frames / sampled_frames, 3) if sampled_frames > 0 else 0,
            "track_details": track_details,
            "alert_moments": alert_moments,
            "result_frames": result_frames
        }

    async def detect_bytes(self, image_bytes: bytes, confidence: float = None, iou_threshold: float = None) -> DetectionResult:
        """字节流检测"""
        if self.model is None:
            await self.load_model()
        
        # 默认值走运行时配置（管理员在「系统设置」改的值优先于 .env）
        if confidence is None:
            confidence = runtime_config.default_confidence()
        if iou_threshold is None:
            iou_threshold = runtime_config.default_iou()
        
        # 解码图像
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise ValueError("无法解码图像")
        
        image_height, image_width = image.shape[:2]
        
        # 执行检测（多尺度融合）
        start_time = time.time()
        fused = await asyncio.to_thread(
            self._infer_fused, image, confidence, iou_threshold
        )
        inference_time = (time.time() - start_time) * 1000

        # 解析结果 — 与 detect_image 保持一致，严格白名单过滤
        detections, fire_count, smoke_count = self._to_detections(fused)
        
        # 生成检测ID
        detection_id = f"det_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # 构建结果
        result = DetectionResult(
            detection_id=detection_id,
            detections=detections,
            fire_count=fire_count,
            smoke_count=smoke_count,
            inference_time=inference_time,
            image_width=image_width,
            image_height=image_height,
            timestamp=datetime.now(),
            model_name=self.model_name or settings.DEFAULT_MODEL,
            confidence_threshold=confidence,
            iou_threshold=iou_threshold,
            risk=RiskAssessment(**assess_image_risk(fused, image_width, image_height)),
        )
        
        return result
    
    async def _check_alert(self, result: DetectionResult):
        """检查是否需要告警

        规则取运行时配置 —— 管理员在「系统设置→告警规则」改的值会立即生效，
        不必重启后端。
        """
        if not runtime_config.alert_enabled():
            return

        rules = runtime_config.alert_rules()
        alert_level = None
        alert_message = None

        # 火焰优先
        if result.fire_count >= rules.get('fire_count_threshold', 1):
            alert_level = 'critical'
            alert_message = f"【图像检测】发现 {result.fire_count} 处火焰，疑似明火"
        # 其次烟雾
        elif result.smoke_count >= rules.get('smoke_count_threshold', 1):
            alert_level = 'high'
            alert_message = f"【图像检测】发现 {result.smoke_count} 处烟雾，需人工确认"
        # 兜底：高置信目标（其他类别，仅在无 fire/smoke 时可达）
        else:
            max_conf = max((d.confidence for d in result.detections), default=0.0)
            if max_conf >= rules.get('confidence_threshold', 0.75):
                alert_level = 'medium'
                alert_message = f"【图像检测】检测到高置信目标（{max_conf:.0%}），需人工确认"

        # 把风险分级一并写进告警文案：告警中心不点开详情也能判断严重程度
        if alert_level and result.risk:
            alert_message = f"{alert_message}｜风险 {result.risk.score}/100（{result.risk.level}）"

        if alert_level:
            db = SessionLocal()
            try:
                db.add(AlertRecord(
                    alert_id=f"alert_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                    detection_id=result.detection_id,
                    level=alert_level,
                    message=alert_message,
                    fire_count=result.fire_count,
                    smoke_count=result.smoke_count,
                    is_read=False,
                    status="pending",
                    created_at=datetime.now(),
                ))
                db.commit()
                logger.warning(f"告警 [{alert_level}] {alert_message}")
            except Exception as e:
                db.rollback()
                logger.error(f"创建告警失败: {e}")
            finally:
                db.close()


class ModelService:
    """模型服务"""
    
    def __init__(self, detection_service: Optional[DetectionService] = None):
        # 复用外部注入的检测服务实例，避免同一模型被加载两次（8GB 显存下影响明显）
        self.detection_service = detection_service or DetectionService()
        self.models_info = []
    
    async def load_default_model(self):
        """加载默认模型"""
        try:
            await self.detection_service.load_model(settings.DEFAULT_MODEL)
            await self._load_models_info()
        except Exception as e:
            logger.error(f"加载默认模型失败: {e}")
    
    async def _load_models_info(self):
        """加载模型信息"""
        model_dir = Path(settings.MODEL_DIR)
        self.models_info = []
        
        for model_file in model_dir.glob("*.pt"):
            is_current = model_file.stem == self.detection_service.model_name
            model_info = ModelInfo(
                name=model_file.stem,
                version="1.0",
                path=str(model_file),
                size=f"{model_file.stat().st_size / (1024*1024):.1f}MB",
                description=f"YOLOv8 {model_file.stem} 模型",
                is_loaded=is_current,
                load_time=datetime.now() if is_current else None
            )
            self.models_info.append(model_info)
    
    async def list_models(self) -> List[ModelInfo]:
        """获取模型列表"""
        await self._load_models_info()
        return self.models_info
    
    async def load_model(self, model_name: str):
        """加载指定模型"""
        await self.detection_service.load_model(model_name)
        await self._load_models_info()
    
    async def get_current_model(self) -> Optional[ModelInfo]:
        """获取当前模型信息"""
        if self.detection_service.model_name:
            for model in self.models_info:
                if model.name == self.detection_service.model_name:
                    return model
        return None
    
    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self.detection_service.model is not None


class HistoryService:
    """历史记录服务"""

    def add_alert(self, level: str, message: str, fire_count: int = 0,
                  smoke_count: int = 0, ref_id: str = "") -> Optional[str]:
        """通用告警写入（返回 alert_id）

        实时流 / 视频检测 / 图像检测共用此入口，保证告警只落一张表 alert_records。
        """
        alert_id = f"alert_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(AlertRecord(
                alert_id=alert_id,
                detection_id=ref_id or "",
                level=level,
                message=message,
                fire_count=fire_count,
                smoke_count=smoke_count,
                is_read=False,
                status="pending",
                created_at=datetime.now(),
            ))
            db.commit()
            logger.warning(f"告警写入 [{level}] {message}")
            return alert_id
        except Exception as e:
            db.rollback()
            logger.error(f"写入告警失败: {e}")
            return None
        finally:
            db.close()

    def create_alert(self, source, level: str, message: str,
                     fire_count: int, smoke_count: int) -> None:
        """实时流告警回调（source 为 StreamSource 对象，兼容字符串）"""
        ref_id = getattr(source, "source_id", "") or ""
        location = getattr(source, "location", "") or ""
        if location:
            message = f"{message} @{location}"
        self.add_alert(level, message, fire_count, smoke_count, ref_id)

    async def save_detection(self, result: DetectionResult):
        """保存检测结果"""
        db = SessionLocal()
        try:
            record = DetectionRecord(
                detection_id=result.detection_id,
                image_path=result.image_path,
                fire_count=result.fire_count,
                smoke_count=result.smoke_count,
                total_detections=len(result.detections),
                inference_time=result.inference_time,
                model_name=result.model_name,
                confidence_threshold=result.confidence_threshold,
                iou_threshold=result.iou_threshold,
                created_at=result.timestamp
            )
            db.add(record)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"保存检测记录失败: {e}")
        finally:
            db.close()
    
    async def get_history(self, page: int = 1, page_size: int = 20, 
                          start_date: str = None, end_date: str = None) -> List[DetectionHistory]:
        """获取检测历史"""
        db = SessionLocal()
        try:
            query = db.query(DetectionRecord)
            
            # 日期过滤
            if start_date:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(DetectionRecord.created_at >= start)
            if end_date:
                end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(DetectionRecord.created_at < end)
            
            # 分页
            records = query.order_by(DetectionRecord.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
            
            # 转换为响应模型
            history = []
            for record in records:
                history.append(DetectionHistory(
                    detection_id=record.detection_id,
                    image_path=record.image_path or "",
                    fire_count=record.fire_count,
                    smoke_count=record.smoke_count,
                    total_detections=record.total_detections,
                    inference_time=record.inference_time,
                    timestamp=record.created_at,
                    model_name=record.model_name,
                    has_alert=False,  # 简化处理
                    alert_level=None
                ))
            
            return history
        finally:
            db.close()
    
    async def get_detection(self, detection_id: str) -> Optional[DetectionRecord]:
        """获取检测详情"""
        db = SessionLocal()
        try:
            return db.query(DetectionRecord).filter(DetectionRecord.detection_id == detection_id).first()
        finally:
            db.close()
    
    async def get_statistics(self, days: int = 7) -> Statistics:
        """获取统计数据

        同时给出「检测次数」与「火/烟目标数」两套按天/按小时聚合：
        前者看系统使用强度，后者看火情趋势，数据分析页两者都要用。
        """
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)

            # 查询记录
            records = db.query(DetectionRecord).filter(DetectionRecord.created_at >= start_date).all()

            # 计算统计
            total_detections = len(records)
            total_fire = sum(r.fire_count for r in records)
            total_smoke = sum(r.smoke_count for r in records)
            avg_inference_time = sum(r.inference_time for r in records) / total_detections if total_detections > 0 else 0

            # 按天/按小时聚合
            detection_by_day: dict = {}
            detection_by_hour: dict = {}
            fire_by_day: dict = {}
            smoke_by_day: dict = {}
            fire_by_hour: dict = {}
            smoke_by_hour: dict = {}

            for record in records:
                if not record.created_at:
                    continue
                day = record.created_at.strftime("%Y-%m-%d")
                hour = record.created_at.strftime("%H")

                detection_by_day[day] = detection_by_day.get(day, 0) + 1
                detection_by_hour[hour] = detection_by_hour.get(hour, 0) + 1
                fire_by_day[day] = fire_by_day.get(day, 0) + (record.fire_count or 0)
                smoke_by_day[day] = smoke_by_day.get(day, 0) + (record.smoke_count or 0)
                fire_by_hour[hour] = fire_by_hour.get(hour, 0) + (record.fire_count or 0)
                smoke_by_hour[hour] = smoke_by_hour.get(hour, 0) + (record.smoke_count or 0)

            # 真实告警数（原先写死 0）
            alert_count = db.query(AlertRecord).filter(
                AlertRecord.created_at >= start_date
            ).count()

            return Statistics(
                total_detections=total_detections,
                total_fire=total_fire,
                total_smoke=total_smoke,
                avg_inference_time=avg_inference_time,
                alert_count=alert_count,
                detection_by_day=detection_by_day,
                detection_by_hour=detection_by_hour,
                fire_by_day=fire_by_day,
                smoke_by_day=smoke_by_day,
                fire_by_hour=fire_by_hour,
                smoke_by_hour=smoke_by_hour,
            )
        finally:
            db.close()