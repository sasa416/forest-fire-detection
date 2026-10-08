#!/usr/bin/env python3
"""
实时监控流 API
提供监控源管理、MJPEG 推流、实时检测结果查询与 WebSocket 推送
"""

import asyncio
import json
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.stream_service import stream_manager
from loguru import logger

router = APIRouter(prefix="/api/stream", tags=["实时监控"])


class CreateSourceRequest(BaseModel):
    """新增监控源请求"""
    name: str = Field(..., description="监控点名称，如 1号瞭望塔")
    url: str = Field(..., description="流地址，如 rtsp://admin:pwd@192.168.1.64:554/Streaming/Channels/101")
    source_type: str = Field("rtsp", description="rtsp / rtmp / http / file")
    frame_interval: int = Field(3, ge=1, le=30, description="每 N 帧推理一次")
    confidence: float = Field(0.3, ge=0.0, le=1.0, description="置信度阈值")
    iou_threshold: float = Field(0.45, ge=0.0, le=1.0, description="IOU 阈值")
    location: str = Field("", description="点位描述，用于告警定位")


@router.get("/sources", summary="获取所有监控源")
async def list_sources() -> List[Dict[str, Any]]:
    return stream_manager.list_sources()


@router.post("/sources", summary="新增监控源")
async def create_source(req: CreateSourceRequest) -> Dict[str, Any]:
    try:
        source = stream_manager.add_source(
            name=req.name,
            url=req.url,
            source_type=req.source_type,
            frame_interval=req.frame_interval,
            confidence=req.confidence,
            iou_threshold=req.iou_threshold,
            location=req.location,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("新增监控源失败")
        raise HTTPException(status_code=500, detail=f"新增监控源失败: {exc}")

    return {"message": "监控源已创建", "source": source.to_dict()}


@router.delete("/sources/{source_id}", summary="删除监控源")
async def delete_source(source_id: str) -> Dict[str, str]:
    if not stream_manager.remove_source(source_id):
        raise HTTPException(status_code=404, detail="监控源不存在")
    return {"message": "监控源已删除"}


@router.post("/sources/{source_id}/start", summary="启动监控源")
async def start_source(source_id: str) -> Dict[str, str]:
    if not stream_manager.start_source(source_id):
        raise HTTPException(status_code=404, detail="监控源不存在")
    return {"message": "监控源已启动"}


@router.post("/sources/{source_id}/stop", summary="停止监控源")
async def stop_source(source_id: str) -> Dict[str, str]:
    if not stream_manager.stop_source(source_id):
        raise HTTPException(status_code=404, detail="监控源不存在")
    return {"message": "监控源已停止"}


@router.get("/sources/{source_id}/detections", summary="获取最新检测结果")
async def get_detections(source_id: str) -> Dict[str, Any]:
    worker = stream_manager.get_worker(source_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="监控源不存在")
    return worker.latest_detections()


class UpdateParamsRequest(BaseModel):
    """运行时参数调整"""
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="置信度阈值")
    iou_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="IOU 阈值")
    frame_interval: Optional[int] = Field(None, ge=1, le=30, description="推理跳帧间隔")


@router.patch("/sources/{source_id}/params", summary="运行时调整检测参数")
async def update_params(source_id: str, req: UpdateParamsRequest) -> Dict[str, Any]:
    """无需重启流即可生效（Worker 每帧读取最新参数）"""
    source = stream_manager.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="监控源不存在")

    if req.confidence is not None:
        source.confidence = req.confidence
    if req.iou_threshold is not None:
        source.iou_threshold = req.iou_threshold
    if req.frame_interval is not None:
        source.frame_interval = req.frame_interval

    return {"message": "参数已更新", "source": source.to_dict()}


@router.get("/sources/{source_id}/mjpeg", summary="MJPEG 实时视频流")
async def mjpeg_stream(source_id: str):
    """
    返回 multipart/x-mixed-replace 视频流。
    前端直接使用 <img src="..."> 即可播放，检测框已由后端绘制完成。
    """
    worker = stream_manager.get_worker(source_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="监控源不存在")

    return StreamingResponse(
        worker.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.websocket("/ws/{source_id}")
async def ws_detections(websocket: WebSocket, source_id: str):
    """WebSocket 推送实时检测结果（JSON），供右侧数据面板使用"""
    worker = stream_manager.get_worker(source_id)
    if worker is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    try:
        while True:
            await websocket.send_text(json.dumps(worker.latest_detections(),
                                                 ensure_ascii=False))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.debug(f"WebSocket 断开: {source_id}")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"WebSocket 异常: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
