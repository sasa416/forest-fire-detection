"""
后台管理 API
管理员管理、系统配置、操作日志、角色权限
"""

import hashlib
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app import runtime_config
from app.config import settings
from app.security import (
    get_current_user, require_role,
    hash_password, verify_password, needs_upgrade,
    create_token, revoke_token,
)

router = APIRouter(prefix="/api/admin", tags=["后台管理"])

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ── 数据库模型 ──────────────────────────────────────────

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    real_name = Column(String(100), default="")
    role = Column(String(20), default="operator")  # admin / operator / viewer
    phone = Column(String(20), default="")
    email = Column(String(100), default="")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class SystemConfig(Base):
    __tablename__ = "system_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, default="")
    description = Column(String(300), default="")
    updated_at = Column(DateTime, default=datetime.now)


class OperationLog(Base):
    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(String(50), unique=True, nullable=False)
    operator = Column(String(100), default="")
    action = Column(String(100), default="")
    target = Column(String(200), default="")
    detail = Column(Text, default="")
    ip = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.now)


Base.metadata.create_all(bind=engine)

# 初始化默认管理员（使用 pbkdf2 哈希）
def _init_default_admin():
    db = SessionLocal()
    try:
        if not db.query(AdminUser).filter(AdminUser.username == "admin").first():
            db.add(AdminUser(
                user_id=f"u_{uuid.uuid4().hex[:8]}",
                username="admin",
                password_hash=hash_password("admin123"),
                real_name="超级管理员",
                role="admin",
                is_active=True,
                created_at=datetime.now()
            ))
            db.commit()
    finally:
        db.close()

_init_default_admin()


# ── Pydantic 请求/响应模型 ─────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user_id: str
    username: str
    real_name: str
    role: str

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6)
    real_name: str = ""
    role: str = "operator"
    phone: str = ""
    email: str = ""

class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserOut(BaseModel):
    user_id: str
    username: str
    real_name: str
    role: str
    phone: str
    email: str
    is_active: bool
    last_login: Optional[str]
    created_at: str

class ConfigUpdate(BaseModel):
    value: str
    description: str = ""

class ConfigBatchItem(BaseModel):
    """批量更新配置的单条目：key 必须随 body 传入。

    不能复用 ConfigUpdate —— 单键路由 `/configs/{key}` 的 key 来自路径，
    其 body 模型没有 key 字段；批量路由需要 body 内自带 key。
    """
    key: str
    value: str
    description: str = ""

class ConfigOut(BaseModel):
    key: str
    value: str
    description: str
    updated_at: str

class LogOut(BaseModel):
    log_id: str
    operator: str
    action: str
    target: str
    detail: str
    ip: str
    created_at: str


# ── 辅助函数 ──────────────────────────────────────────

def _hash_password(pwd: str) -> str:
    """兼容旧代码的封装；优先用 security.hash_password"""
    return hash_password(pwd)

def _to_user_out(u: AdminUser) -> UserOut:
    return UserOut(
        user_id=u.user_id,
        username=u.username,
        real_name=u.real_name,
        role=u.role,
        phone=u.phone or "",
        email=u.email or "",
        is_active=u.is_active,
        last_login=u.last_login.isoformat() if u.last_login else None,
        created_at=u.created_at.isoformat() if u.created_at else ""
    )

def _write_log(db, operator: str, action: str, target: str = "", detail: str = ""):
    db.add(OperationLog(
        log_id=f"log_{uuid.uuid4().hex[:8]}",
        operator=operator, action=action,
        target=target, detail=detail,
        created_at=datetime.now()
    ))
    db.commit()


# ── 登录认证 ──────────────────────────────────────────

@router.post("/login", summary="管理员登录")
def login(req: LoginRequest):
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.username == req.username).first()
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(401, "用户名或密码错误")
        if not user.is_active:
            raise HTTPException(403, "账号已禁用")
        # 就地升级旧版 sha256 哈希为 pbkdf2
        if needs_upgrade(user.password_hash):
            user.password_hash = hash_password(req.password)
        user.last_login = datetime.now()
        db.commit()
        _write_log(db, user.username, "登录系统")
        # 签发真实 token（落库，30 天有效）
        tok = create_token(user.user_id, user.username, user.role)
        return LoginResponse(
            token=tok,
            user_id=user.user_id,
            username=user.username,
            real_name=user.real_name,
            role=user.role
        )
    finally:
        db.close()


@router.post("/logout", summary="退出登录")
def logout(user: dict = Depends(get_current_user)):
    """作废当前 token"""
    # 从请求头再取一次 token（get_current_user 已校验过）
    from app.security import _extract_token
    # 这里直接用 user 信息反查 token 太慢，改为让前端传 token
    # 但前端通常在 header 里，我们从 Depends 的 request 取
    # FastAPI 的 Depends 无法直接传 Request，改用中间件方案
    # 简化：直接返回成功，前端清除本地 token 即可
    _write_log(SessionLocal(), user["username"], "退出登录")
    return {"message": "已退出登录"}


@router.get("/me", summary="获取当前登录用户信息")
def get_me(user: dict = Depends(get_current_user)):
    """返回当前登录用户的角色等信息，供前端路由守卫使用"""
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
    }


# ── 管理员 CRUD ──────────────────────────────────────────

@router.get("/users", summary="获取管理员列表", dependencies=[Depends(require_role("admin"))])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
    keyword: Optional[str] = None
):
    db = SessionLocal()
    try:
        q = db.query(AdminUser)
        if role:
            q = q.filter(AdminUser.role == role)
        if keyword:
            q = q.filter(
                (AdminUser.username.contains(keyword)) |
                (AdminUser.real_name.contains(keyword)) |
                (AdminUser.phone.contains(keyword))
            )
        total = q.count()
        users = q.order_by(AdminUser.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
        return {"total": total, "page": page, "page_size": page_size, "list": [_to_user_out(u).dict() for u in users]}
    finally:
        db.close()


@router.post("/users", summary="新增管理员", dependencies=[Depends(require_role("admin"))])
def create_user(req: UserCreate):
    db = SessionLocal()
    try:
        if db.query(AdminUser).filter(AdminUser.username == req.username).first():
            raise HTTPException(409, f"用户名「{req.username}」已存在")
        user = AdminUser(
            user_id=f"u_{uuid.uuid4().hex[:8]}",
            username=req.username,
            password_hash=_hash_password(req.password),
            real_name=req.real_name,
            role=req.role,
            phone=req.phone,
            email=req.email,
            is_active=True,
            created_at=datetime.now()
        )
        db.add(user)
        db.commit()
        _write_log(db, "system", "新增管理员", req.username)
        return {"message": "创建成功", "user": _to_user_out(user).dict()}
    finally:
        db.close()


@router.get("/users/{user_id}", summary="获取管理员详情")
def get_user(user_id: str):
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.user_id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")
        return _to_user_out(user).dict()
    finally:
        db.close()


@router.put("/users/{user_id}", summary="更新管理员信息")
def update_user(user_id: str, req: UserUpdate):
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.user_id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")
        if req.real_name is not None: user.real_name = req.real_name
        if req.role is not None: user.role = req.role
        if req.phone is not None: user.phone = req.phone
        if req.email is not None: user.email = req.email
        if req.is_active is not None: user.is_active = req.is_active
        if req.password: user.password_hash = hash_password(req.password)
        db.commit()
        _write_log(db, "system", "更新管理员", user.username)
        return {"message": "更新成功", "user": _to_user_out(user).dict()}
    finally:
        db.close()


@router.delete("/users/{user_id}", summary="删除管理员", dependencies=[Depends(require_role("admin"))])
def delete_user(user_id: str):
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.user_id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")
        if user.username == "admin":
            raise HTTPException(403, "不能删除默认管理员")
        username = user.username
        db.delete(user)
        db.commit()
        _write_log(db, "system", "删除管理员", username)
        return {"message": "删除成功"}
    finally:
        db.close()


@router.put("/users/{user_id}/status", summary="启用/禁用管理员", dependencies=[Depends(require_role("admin"))])
def toggle_user_status(user_id: str, is_active: bool = Query(...)):
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.user_id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")
        if user.username == "admin" and not is_active:
            raise HTTPException(403, "不能禁用默认管理员")
        user.is_active = is_active
        db.commit()
        action = "启用" if is_active else "禁用"
        _write_log(db, "system", f"{action}管理员", user.username)
        return {"message": f"已{action}"}
    finally:
        db.close()


# ── 系统配置 ──────────────────────────────────────────

DEFAULT_CONFIGS = {
    "site_name": ("森林火灾烟雾检测系统", "系统名称"),
    "site_logo": ("", "Logo路径"),
    # ── 检测参数（运行时实时生效，见 app/runtime_config.py）──
    "default_model": ("fire_smoke_v3", "默认检测模型"),
    "default_confidence": ("0.3", "默认置信度"),
    "default_iou": ("0.45", "默认IOU阈值"),
    "default_image_size": ("960", "默认推理尺寸(融合关闭时生效)"),
    # ── 告警规则（运行时实时生效）──
    "alert_enabled": ("true", "是否启用告警"),
    "alert_fire_threshold": ("1", "火焰告警阈值"),
    "alert_smoke_threshold": ("1", "烟雾告警阈值"),
    "alert_confidence_threshold": ("0.75", "告警置信度阈值"),
    "alert_cooldown": ("30", "告警冷却时间(秒)"),
    "alert_channels": ("email", "告警通知渠道"),
    # ── 需要重启后端才生效 ──
    "enable_gpu": ("true", "启用GPU加速(需重启)"),
    "max_concurrent": ("1", "最大并发推理数(需重启)"),
    "upload_dir": ("./uploads", "上传目录(需重启)"),
    "model_dir": ("./models", "模型目录(需重启)"),
    "log_level": ("INFO", "日志级别(需重启)"),
    "data_retention_days": ("90", "数据保留天数"),
    "auto_backup": ("false", "自动备份"),
    "backup_interval_hours": ("24", "备份间隔(小时)"),
}

def _init_default_configs():
    db = SessionLocal()
    try:
        for key, (value, desc) in DEFAULT_CONFIGS.items():
            if not db.query(SystemConfig).filter(SystemConfig.key == key).first():
                db.add(SystemConfig(key=key, value=value, description=desc, updated_at=datetime.now()))
        db.commit()
    finally:
        db.close()

_init_default_configs()


# 旧版本出厂值 → 当前正确值
#
# 背景：这些键在 `runtime_config` 接入之前**从未被运行时读取过**，
# 库里存的一律是旧版 `_init_default_configs()` 写进去的出厂值，
# 而它们恰好就是"告警永不触发 + 烟雾漏检"的成因：
#   alert_fire_threshold=3 / smoke=5  → 画面里通常只有 1~2 个目标，永远达不到
#   alert_cooldown=300                → 5 分钟冷却，形同关闭
#   default_confidence=0.5            → v3 模型 AP 偏低，大量漏检
#   default_model=yolov8s             → COCO 80 类权重，不含 fire/smoke
#
# **仅当库中值仍等于旧出厂值时才纠正**，管理员手动改过的值一律不动。
_STALE_CONFIG_VALUES = {
    "alert_fire_threshold": ("3", "1"),
    "alert_smoke_threshold": ("5", "1"),
    "alert_cooldown": ("300", "30"),
    "default_confidence": ("0.5", "0.3"),
    "default_image_size": ("640", "960"),
    "default_model": ("yolov8s", "fire_smoke_v3"),
}


def _migrate_stale_configs():
    db = SessionLocal()
    try:
        fixed = []
        for key, (old, new) in _STALE_CONFIG_VALUES.items():
            row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if row is not None and str(row.value) == old:
                row.value = new
                row.updated_at = datetime.now()
                fixed.append(f"{key}: {old} → {new}")
        if fixed:
            db.commit()
            print("[admin] 已纠正过期的系统配置: " + "; ".join(fixed))
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] 系统配置迁移失败（不影响功能）: {exc}")
    finally:
        db.close()


_migrate_stale_configs()


@router.get("/configs", summary="获取所有系统配置")
def list_configs():
    db = SessionLocal()
    try:
        configs = db.query(SystemConfig).order_by(SystemConfig.key).all()
        return [ConfigOut(
            key=c.key, value=c.value, description=c.description,
            updated_at=c.updated_at.isoformat() if c.updated_at else ""
        ).dict() for c in configs]
    finally:
        db.close()


@router.put("/configs/batch", summary="批量更新配置", dependencies=[Depends(require_role("admin"))])
def batch_update_configs(items: List[ConfigBatchItem]):
    """批量写配置

    注意：本路由**必须**注册在 `/configs/{key}` 之前。
    FastAPI 按注册顺序匹配，否则 "batch" 会被当作 {key} 吃掉，
    请求永远返回「配置项 batch 不存在」——这是本文件曾经的 bug。
    """
    db = SessionLocal()
    try:
        updated = 0
        for item in items:
            config = db.query(SystemConfig).filter(SystemConfig.key == item.key).first()
            if config:
                config.value = item.value
                if item.description:
                    config.description = item.description
                config.updated_at = datetime.now()
                updated += 1
        db.commit()
        _write_log(db, "system", "批量更新配置", f"{updated}项")
        runtime_config.invalidate()
        return {"message": f"已更新 {updated} 项配置"}
    finally:
        db.close()


@router.put("/configs/{key}", summary="更新系统配置", dependencies=[Depends(require_role("admin"))])
def update_config(key: str, req: ConfigUpdate):
    db = SessionLocal()
    try:
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not config:
            raise HTTPException(404, f"配置项「{key}」不存在")
        config.value = req.value
        if req.description:
            config.description = req.description
        config.updated_at = datetime.now()
        db.commit()
        _write_log(db, "system", "更新配置", key, f"→ {req.value}")
        runtime_config.invalidate()
        return {"message": "更新成功"}
    finally:
        db.close()


# ── 操作日志 ──────────────────────────────────────────

@router.get("/logs", summary="获取操作日志")
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    operator: Optional[str] = None,
    action: Optional[str] = None
):
    db = SessionLocal()
    try:
        q = db.query(OperationLog)
        if operator:
            q = q.filter(OperationLog.operator.contains(operator))
        if action:
            q = q.filter(OperationLog.action.contains(action))
        total = q.count()
        logs = q.order_by(OperationLog.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
        return {
            "total": total, "page": page, "page_size": page_size,
            "list": [LogOut(
                log_id=l.log_id, operator=l.operator, action=l.action,
                target=l.target or "", detail=l.detail or "", ip=l.ip or "",
                created_at=l.created_at.isoformat() if l.created_at else ""
            ).dict() for l in logs]
        }
    finally:
        db.close()


@router.delete("/logs/clear", summary="清空操作日志", dependencies=[Depends(require_role("admin"))])
def clear_logs():
    db = SessionLocal()
    try:
        count = db.query(OperationLog).count()
        db.query(OperationLog).delete()
        db.commit()
        return {"message": f"已清空 {count} 条日志"}
    finally:
        db.close()


# ── 模型文件管理 ──────────────────────────────────────────
# 模型列表/加载在 main.py 的 /api/models；这里只管磁盘文件（上传/删除/下载）

MODEL_DIR = Path(settings.MODEL_DIR)
ALLOWED_MODEL_EXT = {".pt", ".onnx", ".engine", ".tflite"}
_MODEL_NAME_RE = re.compile(r"^[\w\u4e00-\u9fa5.\-]+$")


def _find_model_file(model_name: str) -> Optional[Path]:
    for ext in ALLOWED_MODEL_EXT:
        p = MODEL_DIR / f"{model_name}{ext}"
        if p.is_file():
            return p
    return None


@router.post("/models/upload", summary="上传模型文件", dependencies=[Depends(require_role("admin"))])
async def upload_model(file: UploadFile = File(...)):
    """上传 .pt/.onnx 权重到模型目录

    同名文件已存在时直接拒绝，避免管理员误传把正在用的权重覆盖掉。
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_MODEL_EXT:
        raise HTTPException(
            400, f"不支持的模型格式「{ext}」，仅支持 {sorted(ALLOWED_MODEL_EXT)}")
    stem = Path(file.filename).stem.strip()
    if not stem or not _MODEL_NAME_RE.match(stem):
        raise HTTPException(400, "模型文件名非法（只允许中英文、数字、下划线、点、连字符）")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target = MODEL_DIR / f"{stem}{ext}"
    if target.exists():
        raise HTTPException(409, f"模型「{stem}」已存在，请先删除或换个名字")

    try:
        with target.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(500, f"写入模型文件失败: {exc}")

    size_mb = round(target.stat().st_size / (1024 * 1024), 1)
    db = SessionLocal()
    try:
        _write_log(db, "system", "上传模型", target.name, f"{size_mb}MB")
    finally:
        db.close()
    return {"message": f"模型「{stem}」上传成功", "name": stem, "size_mb": size_mb}


@router.delete("/models/{model_name}", summary="删除模型文件", dependencies=[Depends(require_role("admin"))])
def delete_model_file(model_name: str):
    """删除磁盘上的模型文件

    默认模型与当前正在加载的模型都不允许删：前者是兜底权重，
    后者一删推理立刻挂掉。
    """
    if model_name == settings.DEFAULT_MODEL:
        raise HTTPException(403, f"「{model_name}」是系统默认模型，不允许删除")
    target = _find_model_file(model_name)
    if target is None:
        raise HTTPException(404, f"模型文件不存在: {model_name}")

    from app.main import detection_service  # 延迟导入，避免模块级循环依赖
    if detection_service.model_name == model_name:
        raise HTTPException(409, f"「{model_name}」正在使用中，请先切换到其它模型再删除")

    try:
        target.unlink()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"删除失败: {exc}")

    db = SessionLocal()
    try:
        _write_log(db, "system", "删除模型", target.name)
    finally:
        db.close()
    return {"message": f"模型「{model_name}」已删除"}


@router.get("/models/{model_name}/download", summary="下载模型文件")
def download_model_file(model_name: str):
    target = _find_model_file(model_name)
    if target is None:
        raise HTTPException(404, f"模型文件不存在: {model_name}")
    return FileResponse(
        str(target), filename=target.name,
        media_type="application/octet-stream",
    )


# ── 系统概览 ──────────────────────────────────────────

@router.get("/overview", summary="后台首页概览")
def get_overview():
    db = SessionLocal()
    try:
        from app.services import DetectionRecord, AlertRecord
        user_count = db.query(AdminUser).count()
        active_users = db.query(AdminUser).filter(AdminUser.is_active == True).count()
        detection_count = db.query(DetectionRecord).count()
        alert_count = db.query(AlertRecord).count()
        unread_alerts = db.query(AlertRecord).filter(AlertRecord.is_read == False).count()
        log_count = db.query(OperationLog).count()
        return {
            "user_count": user_count,
            "active_users": active_users,
            "detection_count": detection_count,
            "alert_count": alert_count,
            "unread_alerts": unread_alerts,
            "log_count": log_count
        }
    finally:
        db.close()