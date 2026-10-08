"""
险情事件服务
负责事件编号生成、时间窗口合并、媒体归集
"""

import os
import shutil
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Text, Float,
    ForeignKey, text, event,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from loguru import logger

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 事件时间窗口（分钟）：同来源 N 分钟内的连续告警合并为 1 个事件
EVENT_MERGE_WINDOW_MINUTES = 10


# ── 数据库模型 ──────────────────────────────────────────

class FireEvent(Base):
    """险情事件主表"""
    __tablename__ = "fire_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_no = Column(String(32), unique=True, nullable=False, index=True)
    level = Column(String(20), default="low", index=True)
    status = Column(String(20), default="open", index=True)
    source_type = Column(String(20), default="image", index=True)
    source_ref = Column(String(200), default="")
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    fire_count = Column(Integer, default=0)
    smoke_count = Column(Integer, default=0)
    max_confidence = Column(Float, default=0.0)
    risk_score = Column(Integer, default=0)
    hit_count = Column(Integer, default=1)
    location = Column(String(200), default="")
    longitude = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    handled_by = Column(String(100), default="")
    handled_at = Column(DateTime, nullable=True)
    handled_note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    media = relationship("EventMedia", back_populates="event", cascade="all, delete-orphan")
    logs = relationship("EventLog", back_populates="event", cascade="all, delete-orphan")


class EventMedia(Base):
    """事件媒体附件"""
    __tablename__ = "event_media"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("fire_events.id"), nullable=False, index=True)
    media_type = Column(String(10), default="image")
    role = Column(String(20), default="original")
    file_path = Column(String(500), default="")
    file_url = Column(String(500), default="")
    file_size = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    sha256 = Column(String(64), default="")
    captured_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    event = relationship("FireEvent", back_populates="media")


class EventLog(Base):
    """事件处置流水"""
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("fire_events.id"), nullable=False, index=True)
    action = Column(String(30), nullable=False)
    operator = Column(String(100), default="")
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    event = relationship("FireEvent", back_populates="logs")


Base.metadata.create_all(bind=engine)


def _ensure_event_columns() -> None:
    """为既有表补充 event_id 外键（可空，向后兼容）"""
    from sqlalchemy import inspect as sa_inspect
    try:
        with engine.begin() as conn:
            insp = sa_inspect(conn)
            for table in ("detection_records", "alert_records"):
                cols = {c["name"] for c in insp.get_columns(table)}
                if "event_id" not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN event_id INTEGER"))
                    logger.info(f"{table} 补充字段: event_id")
    except Exception as exc:
        logger.warning(f"event_id 迁移跳过（不影响功能）: {exc}")

_ensure_event_columns()


# ── 编号生成器 ──────────────────────────────────────────

def _generate_event_no(db) -> str:
    """生成事件编号：XF-YYYYMMDD-HHMMSS-NNN

    NNN 为当日流水号（3 位补零），事务内保证唯一。
    """
    now = datetime.now()
    prefix = f"XF-{now.strftime('%Y%m%d')}-"
    # 计算今日已有事件数
    like_pattern = f"{prefix}%"
    count = db.query(FireEvent).filter(FireEvent.event_no.like(like_pattern)).count()
    seq = count + 1
    event_no = f"{prefix}{now.strftime('%H%M%S')}-{seq:03d}"
    return event_no


def _generate_event_no_with_retry(db, max_retries: int = 3) -> str:
    """带撞号重试的编号生成"""
    for attempt in range(max_retries):
        event_no = _generate_event_no(db)
        # 检查唯一性（理论上不会撞，但防御性检查）
        exists = db.query(FireEvent).filter(FireEvent.event_no == event_no).first()
        if not exists:
            return event_no
        logger.warning(f"事件编号撞号，重试 {attempt + 1}/{max_retries}: {event_no}")
    # 兜底：加随机后缀
    import uuid
    return f"{event_no}-{uuid.uuid4().hex[:4]}"


# ── 媒体目录 ──────────────────────────────────────────

MEDIA_ROOT = Path(settings.DATABASE_URL.replace("sqlite:///", "")).parent / "data" / "media"


def _media_dir(event_no: str, created_at: datetime = None) -> Path:
    """返回事件媒体目录：data/media/YYYY/MM/DD/{事件号}/"""
    dt = created_at or datetime.now()
    d = MEDIA_ROOT / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d") / event_no
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_sha256(path: str) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 事件服务 ──────────────────────────────────────────

class EventService:
    """险情事件管理"""

    @staticmethod
    def attach_detection(
        detection_id: str,
        image_path: str,
        source_type: str = "image",
        source_ref: str = "",
        fire_count: int = 0,
        smoke_count: int = 0,
        max_confidence: float = 0.0,
        risk_score: int = 0,
        annotated_path: str = "",
        location: str = "",
    ) -> Optional[Dict[str, Any]]:
        """将检测结果关联到险情事件

        时间窗口合并逻辑：
        1. 查找最近 EVENT_MERGE_WINDOW_MINUTES 分钟内、同来源、未关闭的事件
        2. 有 → 复用（更新 last_seen/计数）
        3. 无 → 新建事件，生成编号
        """
        db = SessionLocal()
        try:
            now = datetime.now()
            window_start = now - timedelta(minutes=EVENT_MERGE_WINDOW_MINUTES)

            # 确定风险级别
            level = _calc_level(risk_score, fire_count, smoke_count, max_confidence)

            # 查找可合并的事件
            event = db.query(FireEvent).filter(
                FireEvent.source_type == source_type,
                FireEvent.source_ref == source_ref,
                FireEvent.first_seen_at >= window_start,
                FireEvent.status.in_(["open", "handling"]),
            ).order_by(FireEvent.first_seen_at.desc()).first()

            if event:
                # 复用
                event.last_seen_at = now
                event.hit_count += 1
                event.fire_count = max(event.fire_count, fire_count)
                event.smoke_count = max(event.smoke_count, smoke_count)
                event.max_confidence = max(event.max_confidence, max_confidence)
                event.risk_score = max(event.risk_score, risk_score)
                if _level_priority(level) > _level_priority(event.level):
                    event.level = level
                event.updated_at = now
                event_id = event.id
                event_no = event.event_no
            else:
                # 新建
                event_no = _generate_event_no_with_retry(db)
                event = FireEvent(
                    event_no=event_no,
                    level=level,
                    status="open",
                    source_type=source_type,
                    source_ref=source_ref,
                    first_seen_at=now,
                    last_seen_at=now,
                    fire_count=fire_count,
                    smoke_count=smoke_count,
                    max_confidence=max_confidence,
                    risk_score=risk_score,
                    hit_count=1,
                    location=location,
                    created_at=now,
                    updated_at=now,
                )
                db.add(event)
                db.flush()  # 获取 event.id
                event_id = event.id

            # 关联检测记录
            try:
                db.execute(
                    text("UPDATE detection_records SET event_id = :eid WHERE detection_id = :did"),
                    {"eid": event_id, "did": detection_id},
                )
            except Exception as exc:
                logger.warning(f"关联 detection_records.event_id 失败: {exc}")

            # 媒体归集
            media_dir = _media_dir(event_no, event.first_seen_at)
            _collect_media(db, event_id, image_path, annotated_path, media_dir, now)

            db.commit()
            logger.info(f"事件关联: {event_no} (hit={event.hit_count}, level={level})")
            return {"event_id": event_id, "event_no": event_no, "level": level, "hit_count": event.hit_count}

        except Exception as exc:
            db.rollback()
            logger.error(f"事件关联失败: {exc}")
            return None
        finally:
            db.close()

    @staticmethod
    def handle_event(event_no: str, action: str, operator: str, note: str = "") -> bool:
        """处置事件（确认/忽略/结案/误报）"""
        db = SessionLocal()
        try:
            event = db.query(FireEvent).filter(FireEvent.event_no == event_no).first()
            if not event:
                return False
            status_map = {"confirm": "closed", "ignore": "false_alarm", "close": "closed", "false_alarm": "false_alarm"}
            new_status = status_map.get(action)
            if not new_status:
                return False
            event.status = new_status
            event.handled_by = operator
            event.handled_at = datetime.now()
            event.handled_note = note
            event.updated_at = datetime.now()
            # 写处置流水
            db.add(EventLog(
                event_id=event.id,
                action=action,
                operator=operator,
                note=note,
                created_at=datetime.now(),
            ))
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.error(f"处置事件失败: {exc}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_event(event_no: str) -> Optional[Dict[str, Any]]:
        """获取事件详情（含媒体、关联检测、处置流水）"""
        db = SessionLocal()
        try:
            event = db.query(FireEvent).filter(FireEvent.event_no == event_no).first()
            if not event:
                return None
            return _event_to_dict(event, db)
        finally:
            db.close()

    @staticmethod
    def list_events(
        page: int = 1,
        page_size: int = 20,
        keyword: str = "",
        level: str = "",
        status: str = "",
        source_type: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> Dict[str, Any]:
        """事件列表 + 筛选"""
        db = SessionLocal()
        try:
            q = db.query(FireEvent)
            if keyword:
                q = q.filter(FireEvent.event_no.contains(keyword))
            if level:
                q = q.filter(FireEvent.level == level)
            if status:
                q = q.filter(FireEvent.status == status)
            if source_type:
                q = q.filter(FireEvent.source_type == source_type)
            if start_date:
                q = q.filter(FireEvent.first_seen_at >= datetime.strptime(start_date, "%Y-%m-%d"))
            if end_date:
                q = q.filter(FireEvent.first_seen_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
            total = q.count()
            events = q.order_by(FireEvent.first_seen_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "list": [_event_summary(e) for e in events],
            }
        finally:
            db.close()

    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """事件统计"""
        db = SessionLocal()
        try:
            total = db.query(FireEvent).count()
            by_level = {}
            for lvl in ("critical", "high", "medium", "low"):
                by_level[lvl] = db.query(FireEvent).filter(FireEvent.level == lvl).count()
            by_status = {}
            for st in ("open", "handling", "closed", "false_alarm"):
                by_status[st] = db.query(FireEvent).filter(FireEvent.status == st).count()
            return {"total": total, "by_level": by_level, "by_status": by_status}
        finally:
            db.close()


# ── 辅助函数 ──────────────────────────────────────────

def _calc_level(risk_score: int, fire_count: int, smoke_count: int, max_confidence: float) -> str:
    if risk_score >= 70 or fire_count >= 3:
        return "critical"
    if risk_score >= 40 or fire_count >= 1:
        return "high"
    if risk_score >= 20 or smoke_count >= 3:
        return "medium"
    return "low"


def _level_priority(level: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(level, 0)


def _collect_media(db, event_id: int, image_path: str, annotated_path: str, media_dir: Path, now: datetime):
    """收集媒体文件到事件目录"""
    import cv2
    # 原图
    if image_path and os.path.isfile(image_path):
        src = Path(image_path)
        dst = media_dir / f"original{src.suffix}"
        if not dst.exists():
            shutil.copy2(str(src), str(dst))
        sz = dst.stat().st_size
        sha = _file_sha256(str(dst))
        w, h = _img_size(str(dst))
        db.add(EventMedia(
            event_id=event_id, media_type="image", role="original",
            file_path=str(dst), file_url=f"/media/{media_dir.relative_to(MEDIA_ROOT)}/original{src.suffix}",
            file_size=sz, width=w, height=h, sha256=sha, captured_at=now,
        ))
    # 标注图
    if annotated_path and os.path.isfile(annotated_path):
        src = Path(annotated_path)
        dst = media_dir / f"annotated{src.suffix}"
        if not dst.exists():
            shutil.copy2(str(src), str(dst))
        sz = dst.stat().st_size
        sha = _file_sha256(str(dst))
        w, h = _img_size(str(dst))
        db.add(EventMedia(
            event_id=event_id, media_type="image", role="annotated",
            file_path=str(dst), file_url=f"/media/{media_dir.relative_to(MEDIA_ROOT)}/annotated{src.suffix}",
            file_size=sz, width=w, height=h, sha256=sha, captured_at=now,
        ))


def _img_size(path: str):
    """读取图片尺寸"""
    try:
        import cv2
        img = cv2.imread(path)
        if img is not None:
            return img.shape[1], img.shape[0]
    except Exception:
        pass
    return 0, 0


def _event_summary(e: FireEvent) -> Dict[str, Any]:
    return {
        "id": e.id,
        "event_no": e.event_no,
        "level": e.level,
        "status": e.status,
        "source_type": e.source_type,
        "source_ref": e.source_ref,
        "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else "",
        "last_seen_at": e.last_seen_at.isoformat() if e.last_seen_at else "",
        "fire_count": e.fire_count,
        "smoke_count": e.smoke_count,
        "max_confidence": e.max_confidence,
        "risk_score": e.risk_score,
        "hit_count": e.hit_count,
        "handled_by": e.handled_by or "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
    }


def _event_to_dict(e: FireEvent, db) -> Dict[str, Any]:
    d = _event_summary(e)
    d["location"] = e.location or ""
    d["longitude"] = e.longitude
    d["latitude"] = e.latitude
    d["handled_at"] = e.handled_at.isoformat() if e.handled_at else ""
    d["handled_note"] = e.handled_note or ""
    d["updated_at"] = e.updated_at.isoformat() if e.updated_at else ""
    # 媒体
    d["media"] = [
        {
            "id": m.id,
            "media_type": m.media_type,
            "role": m.role,
            "file_url": m.file_url,
            "file_size": m.file_size,
            "width": m.width,
            "height": m.height,
        }
        for m in db.query(EventMedia).filter(EventMedia.event_id == e.id).all()
    ]
    # 处置流水
    d["logs"] = [
        {
            "id": l.id,
            "action": l.action,
            "operator": l.operator,
            "note": l.note or "",
            "created_at": l.created_at.isoformat() if l.created_at else "",
        }
        for l in db.query(EventLog).filter(EventLog.event_id == e.id).order_by(EventLog.created_at.desc()).all()
    ]
    return d


# 模块级实例
event_service = EventService()
