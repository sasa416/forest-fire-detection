#!/usr/bin/env python3
"""
森林火灾烟雾检测系统 - FastAPI后端服务
提供RESTful API接口，支持图像/视频检测、模型管理、历史记录查询
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import shutil

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.models import DetectionResult, DetectionHistory, ModelInfo
from app.services import DetectionService, ModelService, HistoryService
from app.config import settings
from app.routers import stream as stream_router
from app.routers import admin as admin_router
from app.routers import alerts as alerts_router
from app.routers import events as events_router
from app.stream_service import stream_manager

# 创建FastAPI应用
app = FastAPI(
    title="森林火灾烟雾检测系统",
    description="基于YOLOv8的森林火灾烟雾检测API服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务（使用绝对路径，避免工作目录不一致）
_static_dir = Path(__file__).parent.parent / "static"
_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# 实时监控路由
app.include_router(stream_router.router)

# 告警中心路由
app.include_router(alerts_router.router)

# 后台管理路由
app.include_router(admin_router.router)

# 险情事件路由
app.include_router(events_router.router)

# 媒体文件静态服务（data/media/）
_media_dir = Path(__file__).parent.parent / "data" / "media"
_media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_media_dir)), name="media")

# 服务实例
# 注意：ModelService 复用同一个 DetectionService 实例，否则模型会被加载两次
# （旧写法下 detection_service.model 始终为 None，实时流拿不到模型 → 画面检测全空）
detection_service = DetectionService()
model_service = ModelService(detection_service)
history_service = HistoryService()


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    print("正在初始化森林火灾烟雾检测系统...")
    await model_service.load_default_model()

    # 将已加载的 YOLO 模型共享给实时流服务
    if detection_service.model is not None:
        stream_manager.bind_model(detection_service.model)

    # 实时流告警写入数据库
    stream_manager.set_alert_callback(history_service.create_alert)

    print("系统初始化完成")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件：释放所有视频流"""
    stream_manager.shutdown()
    print("实时视频流已全部关闭")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "森林火灾烟雾检测系统API",
        "version": "1.0.0",
        "docs": "/docs",
        "admin": "/admin"
    }


@app.get("/admin")
async def admin_portal():
    """后台管理门户"""
    admin_page = _static_dir / "admin" / "index.html"
    if admin_page.exists():
        return FileResponse(str(admin_page), media_type="text/html")
    raise HTTPException(status_code=404, detail="后台页面不存在")


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model_loaded": model_service.is_model_loaded()
    }


@app.post("/api/detect/image", response_model=DetectionResult)
async def detect_image(
    file: UploadFile = File(...),
    confidence: float = Query(0.30, ge=0.0, le=1.0, description="置信度阈值"),
    iou_threshold: float = Query(0.45, ge=0.0, le=1.0, description="IOU阈值")
):
    """
    图像检测接口
    
    Args:
        file: 上传的图像文件
        confidence: 置信度阈值
        iou_threshold: IOU阈值
    
    Returns:
        DetectionResult: 检测结果
    """
    # 验证文件类型
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}，支持: {allowed_extensions}"
        )
    
    try:
        # 保存上传文件
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        
        file_path = upload_dir / f"{int(time.time())}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 执行检测
        result = await detection_service.detect_image(
            image_path=str(file_path),
            confidence=confidence,
            iou_threshold=iou_threshold
        )
        
        # 保存到历史记录
        await history_service.save_detection(result)

        # 险情事件关联（fire≥1 或 smoke≥1 时触发）
        if result.fire_count > 0 or result.smoke_count > 0:
            from app.event_service import event_service
            annotated_url = result.image_url or ""
            annotated_path = str(Path("static") / annotated_url.lstrip("/static/")) if annotated_url.startswith("/static/") else ""
            event_service.attach_detection(
                detection_id=result.detection_id,
                image_path=str(file_path),
                source_type="image",
                source_ref=file.filename or "",
                fire_count=result.fire_count,
                smoke_count=result.smoke_count,
                max_confidence=max((d.confidence for d in result.detections), default=0.0),
                risk_score=result.risk.score if result.risk else 0,
                annotated_path=annotated_path,
            )

        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检测失败: {str(e)}")


@app.post("/api/detect/video")
async def detect_video(
    file: UploadFile = File(...),
    confidence: float = Query(0.30, ge=0.0, le=1.0, description="置信度阈值"),
    iou_threshold: float = Query(0.45, ge=0.0, le=1.0, description="IOU阈值"),
    frame_interval: int = Query(10, ge=1, le=100, description="帧间隔")
):
    """
    视频检测接口 — 逐帧检测，返回 JSON 结果 + 保存标注帧
    """
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(400, f"不支持的视频格式: {file_ext}，支持: {allowed_extensions}")

    try:
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        file_path = upload_dir / f"{int(time.time())}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 视频检测耗时长且是同步实现，必须移出事件循环：
        # 否则检测期间整个服务（实时监控轮询 / WebSocket 推送）全部卡死
        result = await asyncio.to_thread(
            detection_service.detect_video_file,
            str(file_path),
            confidence,
            iou_threshold,
            frame_interval,
        )

        # 按风险分写入告警中心（此前视频检测完全不产生告警，是"告警中心无反应"的直接原因之一）
        risk_score = int(result.get("risk_score") or 0)
        if risk_score >= 70:
            level = "critical"
        elif risk_score >= 40:
            level = "high"
        elif risk_score >= 20:
            level = "medium"
        else:
            level = None

        if level:
            history_service.add_alert(
                level=level,
                message=(f"【视频检测】{file.filename} — {result.get('risk_level', '')}"
                         f"（风险 {risk_score} 分）"),
                fire_count=int(result.get("fire_tracks") or 0),
                smoke_count=int(result.get("smoke_tracks") or 0),
                ref_id=Path(file.filename).stem,
            )

        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"视频检测失败: {str(e)}")


@app.get("/api/models", response_model=List[ModelInfo])
async def list_models():
    """获取可用模型列表"""
    return await model_service.list_models()


@app.post("/api/models/load/{model_name}")
async def load_model(model_name: str):
    """加载指定模型"""
    try:
        await model_service.load_model(model_name)
        return {"message": f"模型 {model_name} 加载成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型加载失败: {str(e)}")


@app.get("/api/models/current")
async def get_current_model():
    """获取当前使用的模型信息"""
    return await model_service.get_current_model()


@app.get("/api/history", response_model=List[DetectionHistory])
async def get_detection_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    """
    获取检测历史记录
    
    Args:
        page: 页码
        page_size: 每页数量
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
    
    Returns:
        List[DetectionHistory]: 历史记录列表
    """
    return await history_service.get_history(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date
    )


@app.get("/api/history/{detection_id}")
async def get_detection_detail(detection_id: str):
    """获取检测详情"""
    result = await history_service.get_detection(detection_id)
    if not result:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    return result


@app.get("/api/statistics")
async def get_statistics(
    days: int = Query(7, ge=1, le=365, description="统计天数")
):
    """
    获取检测统计信息
    
    Args:
        days: 统计天数
    
    Returns:
        dict: 统计信息
    """
    return await history_service.get_statistics(days)


@app.websocket("/ws/detect")
async def websocket_detect(websocket):
    """
    WebSocket实时检测接口
    支持实时视频流检测
    """
    await websocket.accept()
    try:
        while True:
            # 接收图像数据
            data = await websocket.receive_bytes()
            
            # 执行检测
            result = await detection_service.detect_bytes(data)
            
            # 发送结果
            await websocket.send_json(result.dict())
            
    except Exception as e:
        print(f"WebSocket错误: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    # 单进程运行：workers>1 会让每个进程各加载一份 YOLO，
    # 在 8GB 显存上产生多个 CUDA 上下文，既爆显存又要各自冷启动。
    # 需要多进程请改用 gunicorn + 共享模型服务，不要直接调大 workers。
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1
    )