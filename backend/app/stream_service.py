#!/usr/bin/env python3
"""
实时流处理服务
负责监控摄像头(RTSP/RTMP)、视频文件、网络流的接入、抽帧、YOLOv8 推理与 MJPEG 推流

设计要点：
- 每一路流由独立线程读取，避免阻塞 asyncio 事件循环
- 推理按 frame_interval 跳帧执行，非推理帧复用最近一次检测结果画框，保证画面流畅
- 通过线程锁保护共享帧，支持多客户端同时拉取同一路流
"""

import os
import cv2

# RTSP 使用 TCP 传输避免 UDP 丢包；stimeout 单位为微秒。必须在创建 VideoCapture 前设置
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000|max_delay;500000",
)

import time
import uuid
import threading
from typing import Dict, List, Optional, Generator, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

import numpy as np
from ultralytics import YOLO
from loguru import logger

from app.config import settings
from app.inference import fuse_multiscale, raw_detect
from app import runtime_config

# 类别配色 (BGR)：火焰红色、烟雾橙色
CLASS_COLORS = {
    "fire": (48, 68, 239),
    "smoke": (11, 158, 245),
}


@dataclass
class StreamSource:
    """流数据源定义"""
    source_id: str
    name: str
    url: str
    source_type: str = "rtsp"          # rtsp / file / http
    enabled: bool = True
    frame_interval: int = 3            # 每 N 帧做一次推理
    confidence: float = 0.3            # v3 模型 AP 偏低，0.5 会大量漏检
    iou_threshold: float = 0.45
    location: str = ""                 # 地理/点位描述，用于告警定位
    # 运行时状态（不参与创建入参）
    status: str = "idle"               # idle / connecting / running / error / stopped
    fps: float = 0.0
    fire_count: int = 0
    smoke_count: int = 0
    frame_count: int = 0
    inference_time: float = 0.0
    last_frame_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StreamWorker:
    """单路视频流的读取 + 推理线程"""

    def __init__(self, source: StreamSource, model: YOLO, device: str = "cpu",
                 on_alert=None):
        self.source = source
        self.model = model
        self.device = device
        self.on_alert = on_alert

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        self._jpeg: Optional[bytes] = None          # 最近一帧（已画框）
        self._detections: List[Dict[str, Any]] = []  # 最近一次检测结果
        self._last_boxes: List[Dict[str, Any]] = []  # 供非推理帧复用
        self._tracks: List[Dict[str, Any]] = []      # 跨帧 IOU 跟踪轨迹（用于告警确认）

        self._fps_t0 = time.time()
        self._fps_counter = 0
        self._alert_cooldown = 0.0

        # 告警规则取运行时配置（管理员可在「系统设置」实时调整）
        _rules = runtime_config.alert_rules()
        try:
            self._alert_cooldown = float(_rules.get("alert_cooldown", 30))
        except Exception:  # noqa: BLE001
            self._alert_cooldown = 30.0
        # 同一目标需连续命中的推理次数（抑制单帧误报）
        try:
            self._track_confirm_hits = int(_rules.get("track_confirm_hits", 3))
        except Exception:  # noqa: BLE001
            self._track_confirm_hits = 3
        self._last_alert_at = 0.0

    # ---------- 生命周期 ----------

    def start(self) -> bool:
        """启动读取线程"""
        if self._running:
            return True
        self._running = True
        self.source.status = "connecting"
        self._thread = threading.Thread(
            target=self._loop, name=f"stream-{self.source.source_id}", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """停止读取线程"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.source.status = "stopped"

    # ---------- 内部实现 ----------

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """打开视频源"""
        url = self.source.url
        cap = None
        if self.source.source_type == "file":
            cap = cv2.VideoCapture(url)
        else:
            # RTSP / RTMP / HTTP 强制走 FFMPEG 后端
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            return None

        # 缓冲区设为 1，尽量取最新帧，降低延迟
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def _loop(self) -> None:
        """主循环：读帧 -> 抽帧推理 -> 画框 -> 编码"""
        cap = self._open_capture()
        if cap is None:
            self.source.status = "error"
            self.source.error = f"无法打开视频源: {self.source.url}"
            logger.error(f"[{self.source.name}] {self.source.error}")
            self._running = False
            return

        self.source.status = "running"
        self.source.error = None
        logger.info(f"[{self.source.name}] 流已连接: {self.source.url}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        is_file = self.source.source_type == "file"
        frame_delay = 1.0 / fps if (is_file and fps and fps > 0) else 0.0

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok or frame is None:
                    if is_file:
                        # 视频文件播完，循环回到开头
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    # 网络流读取失败：重连
                    logger.warning(f"[{self.source.name}] 读帧失败，尝试重连...")
                    cap.release()
                    time.sleep(2)
                    cap = self._open_capture()
                    if cap is None:
                        continue
                    continue

                self.source.frame_count += 1

                # 按间隔执行推理
                if self.source.frame_count % self.source.frame_interval == 1:
                    boxes = self._infer(frame)
                    self._last_boxes = boxes
                    self._detections = boxes
                else:
                    boxes = self._last_boxes

                annotated = self._draw(frame, boxes)
                ok_enc, buf = cv2.imencode(
                    ".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
                )
                if not ok_enc:
                    continue

                with self._lock:
                    self._jpeg = buf.tobytes()

                # FPS 统计
                self._fps_counter += 1
                elapsed = time.time() - self._fps_t0
                if elapsed >= 1.0:
                    self.source.fps = round(self._fps_counter / elapsed, 1)
                    self._fps_counter = 0
                    self._fps_t0 = time.time()

                self.source.last_frame_at = datetime.now().isoformat()

                if frame_delay > 0:
                    time.sleep(frame_delay)

        except Exception as exc:  # noqa: BLE001
            self.source.status = "error"
            self.source.error = str(exc)
            logger.exception(f"[{self.source.name}] 流处理异常")
        finally:
            cap.release()
            with self._lock:
                self._jpeg = None
            if self.source.status != "error":
                self.source.status = "stopped"
            logger.info(f"[{self.source.name}] 流已停止")

    def _infer(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """执行推理，返回检测结果列表

        走多尺度融合：单尺度下 960 只出火焰、1280 只出烟雾，
        固定单尺度必然整类漏检（表现为"画面里浓烟滚滚却 smoke:0"）。
        """
        t0 = time.time()
        try:
            if settings.FUSION_ENABLED:
                fused = fuse_multiscale(
                    self.model, frame,
                    scales=settings.MULTI_SCALE_SIZES,
                    confidence=self.source.confidence,
                    iou=self.source.iou_threshold,
                    device=self.device,
                    class_relax=settings.CLASS_CONF_RELAX,
                    candidate_conf=settings.FUSION_CANDIDATE_CONF,
                    final_threshold=True,
                )
            else:
                fused = raw_detect(
                    self.model, frame, runtime_config.default_image_size(),
                    self.source.confidence, self.source.iou_threshold,
                    device=self.device,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[{self.source.name}] 推理失败: {exc}")
            return []

        self.source.inference_time = round((time.time() - t0) * 1000, 2)

        boxes: List[Dict[str, Any]] = []
        fire_count = 0
        smoke_count = 0

        for d in fused:
            cls_name = d["cls"]
            x1, y1, x2, y2 = d["xyxy"]
            boxes.append({
                "class_id": 0 if cls_name == "fire" else 1,
                "class_name": cls_name,
                "confidence": round(d["conf"], 4),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            })
            if cls_name == "fire":
                fire_count += 1
            elif cls_name == "smoke":
                smoke_count += 1

        self.source.fire_count = fire_count
        self.source.smoke_count = smoke_count

        if boxes:
            # 跨帧 IOU 跟踪：只有持续命中的目标才确认告警，单帧误报直接被滤掉
            confirmed = self._update_tracks(boxes)
            if confirmed:
                self._maybe_alert(fire_count, smoke_count, confirmed)

        return boxes

    @staticmethod
    def _iou(box_a: List[float], box_b: List[float]) -> float:
        """计算两个 [x1,y1,x2,y2] 框的 IOU"""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _update_tracks(self, boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把本帧检测框匹配到已有的跨帧轨迹，返回"已确认"的目标列表

        匹配规则：同类 + IOU ≥ 0.3。命中次数 ≥ track_confirm_hits 视为确认。
        """
        new_tracks: List[Dict[str, Any]] = []
        for det in boxes:
            best_iou = 0.0
            best_track = None
            for track in self._tracks:
                if track["cls"] != det["class_name"]:
                    continue
                iou_val = self._iou(det["bbox"], track["bbox"])
                if iou_val > best_iou:
                    best_iou = iou_val
                    best_track = track

            if best_track is not None and best_iou >= 0.3:
                best_track["bbox"] = det["bbox"]
                best_track["hits"] += 1
                best_track["conf_max"] = max(best_track["conf_max"], det["confidence"])
            else:
                new_tracks.append({
                    "cls": det["class_name"],
                    "bbox": det["bbox"],
                    "hits": 1,
                    "conf_max": det["confidence"],
                })

        # 轨迹池上限，避免长时间运行后无限增长
        self._tracks = (self._tracks + new_tracks)[-80:]
        return [t for t in self._tracks if t["hits"] >= self._track_confirm_hits]

    def _maybe_alert(self, fire_count: int, smoke_count: int,
                     confirmed: Optional[List[Dict[str, Any]]] = None) -> None:
        """跟踪确认后触发告警（带冷却，避免刷屏）"""
        if not runtime_config.alert_enabled() or self.on_alert is None:
            return

        now = time.time()
        if now - self._last_alert_at < self._alert_cooldown:
            return

        confirmed = confirmed or []
        conf_fire = sum(1 for t in confirmed if t["cls"] == "fire")
        conf_smoke = sum(1 for t in confirmed if t["cls"] == "smoke")

        level = None
        message = None

        if conf_fire >= 1:
            level = "critical"
            message = f"{self.source.name} 持续检测到火焰（跟踪确认 {conf_fire} 处）"
        elif conf_smoke >= 1:
            level = "high"
            message = f"{self.source.name} 持续检测到烟雾（跟踪确认 {conf_smoke} 处）"

        if level:
            self._last_alert_at = now
            try:
                self.on_alert(self.source, level, message, fire_count, smoke_count)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"告警回调失败: {exc}")

    def _draw(self, frame: np.ndarray, boxes: List[Dict[str, Any]]) -> np.ndarray:
        """在帧上绘制检测框与标签"""
        canvas = frame.copy()
        for item in boxes:
            x1, y1, x2, y2 = (int(v) for v in item["bbox"])
            color = CLASS_COLORS.get(item["class_name"], (200, 200, 200))
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)

            label = f'{item["class_name"]} {item["confidence"] * 100:.1f}%'
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            ty = y1 - 6 if y1 - th - 8 > 0 else y2 + th + 8
            cv2.rectangle(canvas, (x1, ty - th - 4), (x1 + tw + 6, ty + 4), color, -1)
            cv2.putText(canvas, label, (x1 + 3, ty - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # 左上角状态信息
        info = f"{self.source.name}  fire:{self.source.fire_count}  smoke:{self.source.smoke_count}  {self.source.fps:.1f}fps"
        cv2.putText(canvas, info, (10, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, info, (10, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (30, 30, 30), 1, cv2.LINE_AA)
        return canvas

    # ---------- 对外接口 ----------

    def mjpeg_generator(self) -> Generator[bytes, None, None]:
        """MJPEG 多段流生成器（每个客户端独立调用）"""
        boundary = b"--frame\r\n"
        while self._running:
            with self._lock:
                jpeg = self._jpeg
            if jpeg is None:
                time.sleep(0.03)
                continue
            yield boundary + b"Content-Type: image/jpeg\r\nContent-Length: " \
                + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.03)

    def latest_detections(self) -> Dict[str, Any]:
        """获取最新检测结果"""
        return {
            "source_id": self.source.source_id,
            "name": self.source.name,
            "status": self.source.status,
            "fire_count": self.source.fire_count,
            "smoke_count": self.source.smoke_count,
            "fps": self.source.fps,
            "frame_count": self.source.frame_count,
            "inference_time": self.source.inference_time,
            "detections": self._detections,
            "timestamp": self.source.last_frame_at,
        }


class StreamManager:
    """多路流管理器（单例）"""

    def __init__(self):
        self._workers: Dict[str, StreamWorker] = {}
        self._sources: Dict[str, StreamSource] = {}
        self._model: Optional[YOLO] = None
        self._device = "cuda" if _cuda_available() else "cpu"
        self._lock = threading.Lock()
        self.on_alert = None

    def bind_model(self, model: YOLO) -> None:
        """绑定已加载的 YOLO 模型（同时回填给已创建但未拿到模型的流线程）"""
        self._model = model
        if model is None:
            return
        for worker in self._workers.values():
            if worker.model is None:
                worker.model = model

    def _ensure_model(self) -> None:
        """确保模型可用：启动顺序异常时按需兜底加载

        历史问题：main 中 model_service 持有独立的 DetectionService 实例，
        导致 startup 时 detection_service.model 仍为 None，流线程拿到 None 模型后
        每帧推理静默失败 —— 表现为"画面里火焰烟雾很明显却一个都检测不出来"。
        """
        if self._model is not None:
            return
        try:
            from app.config import get_model_path
            self._model = YOLO(get_model_path(settings.DEFAULT_MODEL))
            self._model.to(self._device)
            logger.info(f"实时流服务按需加载模型: {settings.DEFAULT_MODEL} ({self._device})")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"实时流服务加载模型失败: {exc}")

    def set_alert_callback(self, callback) -> None:
        """设置告警回调"""
        self.on_alert = callback

    # ---------- 源管理 ----------

    def add_source(self, name: str, url: str, source_type: str = "rtsp",
                   frame_interval: int = 3, confidence: float = 0.3,
                   iou_threshold: float = 0.45, location: str = "") -> StreamSource:
        """新增数据源并自动启动"""
        if source_type not in ("rtsp", "rtmp", "http", "file"):
            raise ValueError(f"不支持的数据源类型: {source_type}")

        source = StreamSource(
            source_id=f"src_{uuid.uuid4().hex[:8]}",
            name=name,
            url=url,
            source_type=source_type,
            frame_interval=max(1, int(frame_interval)),
            confidence=confidence,
            iou_threshold=iou_threshold,
            location=location,
        )

        with self._lock:
            self._sources[source.source_id] = source
            worker = StreamWorker(source, self._model, self._device,
                                  on_alert=self.on_alert)
            self._workers[source.source_id] = worker
            worker.start()

        logger.info(f"新增数据源 [{source.name}] {source.source_id}")
        return source

    def remove_source(self, source_id: str) -> bool:
        """删除数据源"""
        with self._lock:
            worker = self._workers.pop(source_id, None)
            source = self._sources.pop(source_id, None)
        if source is None:
            return False
        if worker:
            worker.stop()
        logger.info(f"删除数据源 [{source.name}]")
        return True

    def start_source(self, source_id: str) -> bool:
        worker = self._workers.get(source_id)
        if worker is None:
            return False
        return worker.start()

    def stop_source(self, source_id: str) -> bool:
        worker = self._workers.get(source_id)
        if worker is None:
            return False
        worker.stop()
        return True

    def list_sources(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._sources.values()]

    def get_worker(self, source_id: str) -> Optional[StreamWorker]:
        return self._workers.get(source_id)

    def get_source(self, source_id: str) -> Optional[StreamSource]:
        return self._sources.get(source_id)

    def shutdown(self) -> None:
        """关闭所有流"""
        for source_id in list(self._workers.keys()):
            self.remove_source(source_id)


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# 全局单例
stream_manager = StreamManager()
