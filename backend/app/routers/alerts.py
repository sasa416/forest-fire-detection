#!/usr/bin/env python3
"""
告警中心 API
提供告警记录的查询、未读统计、处置（确认/忽略）、标记已读与删除

说明：告警由三处产生并统一写入 alert_records 表
  1. 图像检测  DetectionService._check_alert
  2. 视频检测  main.detect_video（按 risk_score 分级）
  3. 实时流    StreamWorker._maybe_alert（跨帧跟踪确认后回调）

处置闭环：
  status = pending（待处置） → confirmed（已确认处置）/ ignored（已忽略）
  前端轮询 /api/alerts/pending 弹出确认框，管理人员点「确认」或「忽略」后
  通过 PUT /api/alerts/{id}/handle 落库，记录处置人与时间。
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from loguru import logger

from app.services import AlertRecord, SessionLocal
from app.security import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["告警中心"])

VALID_LEVELS = ("critical", "high", "medium", "low")
VALID_STATUS = ("pending", "confirmed", "ignored")
# 需要弹窗要求人工确认的级别（火灾/烟雾确认类）
POPUP_LEVELS = ("critical", "high")


def _serialize(a: AlertRecord) -> Dict[str, Any]:
    return {
        "alert_id": a.alert_id,
        "detection_id": a.detection_id or "",
        "level": a.level or "low",
        "message": a.message or "",
        "fire_count": a.fire_count or 0,
        "smoke_count": a.smoke_count or 0,
        "is_read": bool(a.is_read),
        "status": a.status or "pending",
        "handled_by": a.handled_by or "",
        "handled_at": a.handled_at.strftime("%Y-%m-%d %H:%M:%S") if a.handled_at else "",
        "handled_note": a.handled_note or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
    }


def _get_or_404(db, alert_id: str) -> AlertRecord:
    alert = db.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(404, "告警不存在")
    return alert


# ── 统计类接口（必须声明在 /{alert_id} 之前，避免被路径参数吞掉）──

@router.get("/unread-count", summary="未读告警数（供顶栏铃铛轮询）")
def unread_count() -> Dict[str, int]:
    db = SessionLocal()
    try:
        total = db.query(AlertRecord).count()
        unread = (db.query(AlertRecord)
                  .filter(AlertRecord.is_read == False)  # noqa: E712
                  .count())
        pending = (db.query(AlertRecord)
                   .filter(AlertRecord.status == "pending")
                   .count())
        return {"unread_count": unread, "total": total, "pending_count": pending}
    finally:
        db.close()


@router.get("/stats", summary="告警统计（分级 / 处置状态计数）")
def alert_stats() -> Dict[str, int]:
    db = SessionLocal()
    try:
        def _count(level: Optional[str] = None, status: Optional[str] = None,
                   unread_only: bool = False) -> int:
            q = db.query(AlertRecord)
            if level:
                q = q.filter(AlertRecord.level == level)
            if status:
                q = q.filter(AlertRecord.status == status)
            if unread_only:
                q = q.filter(AlertRecord.is_read == False)  # noqa: E712
            return q.count()

        return {
            "total": _count(),
            "unread_count": _count(unread_only=True),
            "pending": _count(status="pending"),
            "confirmed": _count(status="confirmed"),
            "ignored": _count(status="ignored"),
            "critical": _count("critical", "pending"),
            "high": _count("high", "pending"),
            "medium": _count("medium", "pending"),
            "low": _count("low", "pending"),
        }
    finally:
        db.close()


@router.get("/latest", summary="最新告警（供前端增量提醒）")
def latest_alert(limit: int = Query(1, ge=1, le=20)) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = (db.query(AlertRecord)
                .order_by(AlertRecord.created_at.desc(), AlertRecord.id.desc())
                .limit(limit).all())
        return [_serialize(r) for r in rows]
    finally:
        db.close()


@router.get("/pending", summary="待处置告警（供前端弹窗排队）")
def pending_alerts(
    limit: int = Query(20, ge=1, le=100),
    popup_levels_only: bool = Query(False, description="仅返回需要弹窗的级别 critical/high"),
) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        q = db.query(AlertRecord).filter(AlertRecord.status == "pending")
        if popup_levels_only:
            q = q.filter(AlertRecord.level.in_(POPUP_LEVELS))
        total = (db.query(AlertRecord)
                 .filter(AlertRecord.status == "pending")
                 .count())
        rows = (q.order_by(AlertRecord.created_at.desc(), AlertRecord.id.desc())
                 .limit(limit).all())
        return {"total": total, "list": [_serialize(r) for r in rows]}
    finally:
        db.close()


# ── 详情接口：必须注册在 /{alert_id} 通用路由之前 ──────────────

@router.get("/{alert_id}/detail", summary="告警详情（含检测结果与关联事件）")
def alert_detail(alert_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """返回告警基础信息 + 关联 detection_records 的检测结果 + 关联事件的媒体与时间线

    供后台管理门户"点开告警看详情"使用。
    """
    db = SessionLocal()
    try:
        from sqlalchemy import text
        from app.services import DetectionRecord
        from app.event_service import FireEvent, EventMedia, EventLog

        alert = db.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).first()
        if not alert:
            raise HTTPException(404, f"告警不存在: {alert_id}")

        data = _serialize(alert)
        data["source_type"] = "image"

        # 关联检测记录
        detection_info: Dict[str, Any] = {}
        alert_moments: List[Dict[str, Any]] = []
        if alert.detection_id:
            det_row = db.query(DetectionRecord).filter(
                DetectionRecord.detection_id == alert.detection_id
            ).first()
            if det_row:
                detection_info = {
                    "detection_id": det_row.detection_id,
                    "image_path": det_row.image_path or "",
                    "image_url": f"/static/results/{det_row.detection_id}/result.jpg",
                    "fire_count": det_row.fire_count or 0,
                    "smoke_count": det_row.smoke_count or 0,
                    "total_detections": det_row.total_detections or 0,
                    "inference_time": det_row.inference_time or 0,
                    "model_name": det_row.model_name or "",
                    "risk_score": 0,
                    "risk_level": "",
                    "advice": "",
                    "detections": [],
                }
                # 推断来源类型
                if det_row.image_path and det_row.image_path.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
                    data["source_type"] = "video"

                # 视频帧：直接从 video_* 目录扫出告警对应的标注帧
                if data["source_type"] == "video":
                    import os
                    from pathlib import Path as _Path
                    up_path = _Path(det_row.image_path)
                    name = up_path.stem
                    # 名称通常是 {ts}_{原名}，取 {原名} 作为标识
                    base = name.split("_", 1)[1] if "_" in name else name
                    base_prefix = base.split(".")[0]
                    static_root = _Path(__file__).resolve().parent.parent / "static"
                    for sub in static_root.iterdir():
                        if sub.is_dir() and sub.name.startswith("video_"):
                            for f in sub.glob("det_*.jpg"):
                                if base_prefix in f.name or f.name.startswith("det_"):
                                    alert_moments.append({"frame_url": f"/static/{sub.name}/{f.name}"})

        data["detection"] = detection_info
        data["alert_moments"] = alert_moments

        # 关联事件
        event_data = None
        event_id = None
        if alert.detection_id:
            row = db.execute(
                text("SELECT event_id FROM detection_records WHERE detection_id = :d"),
                {"d": alert.detection_id},
            ).fetchone()
            if row and row[0]:
                event_id = row[1] if isinstance(row, tuple) else row[0]
        if event_id:
            ev = db.query(FireEvent).filter(FireEvent.id == event_id).first()
            if ev:
                media = db.query(EventMedia).filter(EventMedia.event_id == ev.id).all()
                logs = db.query(EventLog).filter(EventLog.event_id == ev.id).order_by(EventLog.created_at.desc()).all()
                event_data = {
                    "id": ev.id,
                    "event_no": ev.event_no,
                    "level": ev.level,
                    "status": ev.status,
                    "source_type": ev.source_type,
                    "source_ref": ev.source_ref,
                    "first_seen_at": ev.first_seen_at.strftime("%Y-%m-%d %H:%M:%S") if ev.first_seen_at else "",
                    "last_seen_at": ev.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if ev.last_seen_at else "",
                    "fire_count": ev.fire_count,
                    "smoke_count": ev.smoke_count,
                    "max_confidence": ev.max_confidence,
                    "risk_score": ev.risk_score,
                    "hit_count": ev.hit_count,
                    "location": ev.location or "",
                    "handled_by": ev.handled_by or "",
                    "handled_at": ev.handled_at.strftime("%Y-%m-%d %H:%M:%S") if ev.handled_at else "",
                    "handled_note": ev.handled_note or "",
                    "media": [{
                        "id": m.id,
                        "media_type": m.media_type,
                        "role": m.role,
                        "file_url": m.file_url,
                        "file_size": m.file_size,
                        "width": m.width,
                        "height": m.height,
                    } for m in media],
                    "logs": [{
                        "id": l.id,
                        "action": l.action,
                        "operator": l.operator,
                        "note": l.note or "",
                        "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "",
                    } for l in logs],
                }
        data["event"] = event_data
        return data
    finally:
        db.close()


# ── 列表 / 处置 / 操作 ──────────────────────────────────

@router.get("", summary="获取告警列表")
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    level: Optional[str] = Query(None, description="critical / high / medium / low"),
    status: Optional[str] = Query(None, description="pending / confirmed / ignored"),
    is_read: Optional[bool] = Query(None, description="是否已读"),
    keyword: Optional[str] = Query(None, description="消息关键字"),
) -> Dict[str, Any]:
    if level and level not in VALID_LEVELS:
        raise HTTPException(400, f"非法告警级别: {level}")
    if status and status not in VALID_STATUS:
        raise HTTPException(400, f"非法处置状态: {status}")

    db = SessionLocal()
    try:
        q = db.query(AlertRecord)
        if level:
            q = q.filter(AlertRecord.level == level)
        if status:
            q = q.filter(AlertRecord.status == status)
        if is_read is not None:
            q = q.filter(AlertRecord.is_read == is_read)
        if keyword:
            q = q.filter(AlertRecord.message.contains(keyword))

        total = q.count()
        unread = (db.query(AlertRecord)
                  .filter(AlertRecord.is_read == False)  # noqa: E712
                  .count())
        pending = (db.query(AlertRecord)
                   .filter(AlertRecord.status == "pending")
                   .count())
        rows = (q.order_by(AlertRecord.created_at.desc(), AlertRecord.id.desc())
                 .offset((page - 1) * page_size)
                 .limit(page_size)
                 .all())
        return {
            "total": total,
            "unread_count": unread,
            "pending_count": pending,
            "page": page,
            "page_size": page_size,
            "list": [_serialize(r) for r in rows],
        }
    finally:
        db.close()


class HandleRequest(BaseModel):
    """处置告警请求"""
    action: str = Field(..., description="confirm 确认处置 / ignore 忽略")
    operator: str = Field("管理员", max_length=100, description="处置人")
    note: str = Field("", max_length=500, description="处置备注")


@router.put("/{alert_id}/handle", summary="处置告警（确认 / 忽略）")
def handle_alert(alert_id: str, req: HandleRequest) -> Dict[str, Any]:
    action = (req.action or "").strip().lower()
    if action not in ("confirm", "ignore"):
        raise HTTPException(400, "action 仅支持 confirm 或 ignore")

    status = "confirmed" if action == "confirm" else "ignored"
    db = SessionLocal()
    try:
        alert = _get_or_404(db, alert_id)
        alert.status = status
        alert.handled_by = req.operator or "管理员"
        alert.handled_at = datetime.now()
        alert.handled_note = req.note or ""
        # 处置后视为已读，顶栏红点同步消失
        alert.is_read = True
        db.commit()
        db.refresh(alert)
        label = "确认处置" if action == "confirm" else "已忽略"
        logger.info(f"告警处置 [{label}] {alert_id} by {alert.handled_by}")
        return {"message": f"告警已{label}", "alert": _serialize(alert)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(500, f"处置失败: {exc}")
    finally:
        db.close()


@router.put("/{alert_id}/read", summary="标记单条告警已读/未读")
def mark_read(alert_id: str, is_read: bool = Query(True)) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        alert = _get_or_404(db, alert_id)
        alert.is_read = is_read
        db.commit()
        return {"message": "已更新", "alert_id": alert_id, "is_read": is_read}
    finally:
        db.close()


@router.put("/read-all", summary="全部标记为已读")
def mark_all_read() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        updated = (db.query(AlertRecord)
                   .filter(AlertRecord.is_read == False)  # noqa: E712
                   .update({AlertRecord.is_read: True}, synchronize_session=False))
        db.commit()
        logger.info(f"告警全部标记已读: {updated} 条")
        return {"message": f"已标记 {updated} 条为已读", "updated": updated}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(500, f"操作失败: {exc}")
    finally:
        db.close()


@router.delete("/clear", summary="清空全部告警")
def clear_alerts() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        count = db.query(AlertRecord).count()
        db.query(AlertRecord).delete()
        db.commit()
        logger.warning(f"清空告警记录: {count} 条")
        return {"message": f"已清空 {count} 条告警", "deleted": count}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(500, f"清空失败: {exc}")
    finally:
        db.close()


@router.delete("/{alert_id}", summary="删除单条告警")
def delete_alert(alert_id: str) -> Dict[str, str]:
    db = SessionLocal()
    try:
        alert = _get_or_404(db, alert_id)
        db.delete(alert)
        db.commit()
        return {"message": "已删除"}
    finally:
        db.close()
