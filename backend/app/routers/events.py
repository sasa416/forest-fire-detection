"""
险情事件 API
事件列表、详情、处置、统计
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel

from app.event_service import event_service
from app.security import get_current_user, require_role

router = APIRouter(prefix="/api/events", tags=["险情事件"])


class HandleRequest(BaseModel):
    action: str  # confirm / ignore / close / false_alarm
    operator: str = "管理员"
    note: str = ""


@router.get("", summary="事件列表")
def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = "",
    level: str = "",
    status: str = "",
    source_type: str = "",
    start_date: str = "",
    end_date: str = "",
    user: dict = Depends(get_current_user),
):
    return event_service.list_events(
        page=page, page_size=page_size, keyword=keyword,
        level=level, status=status, source_type=source_type,
        start_date=start_date, end_date=end_date,
    )


@router.get("/stats", summary="事件统计")
def event_stats(user: dict = Depends(get_current_user)):
    return event_service.get_stats()


@router.get("/{event_no}", summary="事件详情")
def get_event(event_no: str, user: dict = Depends(get_current_user)):
    ev = event_service.get_event(event_no)
    if not ev:
        raise HTTPException(404, f"事件不存在: {event_no}")
    return ev


@router.put("/{event_no}/handle", summary="处置事件")
def handle_event(event_no: str, req: HandleRequest, user: dict = Depends(get_current_user)):
    valid = ("confirm", "ignore", "close", "false_alarm")
    if req.action not in valid:
        raise HTTPException(400, f"无效操作: {req.action}，支持: {valid}")
    ok = event_service.handle_event(event_no, req.action, req.operator, req.note)
    if not ok:
        raise HTTPException(404, f"事件不存在或处置失败: {event_no}")
    return {"message": f"事件已处置: {req.action}", "event_no": event_no}
