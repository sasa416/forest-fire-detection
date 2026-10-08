"""
安全与鉴权模块
token 签发/校验、角色依赖注入、密码哈希
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

TOKEN_EXPIRE_DAYS = 30  # 「记住我」有效期


# ── 数据库模型 ──────────────────────────────────────────

class UserToken(Base):
    __tablename__ = "user_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    username = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    revoked = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)


# ── 密码哈希（pbkdf2_hmac, stdlib, 无第三方依赖）──

def hash_password(pwd: str, salt: Optional[str] = None) -> str:
    """返回 'salt$hash' 格式；salt 为 16 字节 hex"""
    if salt is None:
        salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), iterations=100_000)
    return f"{salt}${dk.hex()}"


def verify_password(pwd: str, stored: str) -> bool:
    """验证密码；兼容旧版 sha256（无盐）格式"""
    if "$" in stored:
        salt, _ = stored.split("$", 1)
        return hash_password(pwd, salt) == stored
    # 旧格式：纯 sha256
    return hashlib.sha256(pwd.encode()).hexdigest() == stored


def needs_upgrade(stored: str) -> bool:
    """判断是否需要升级为 pbkdf2"""
    return "$" not in stored


# ── token 签发 / 校验 / 作废 ──────────────────────────────

def create_token(user_id: str, username: str, role: str) -> str:
    """签发新 token，写入 user_tokens 表"""
    db = SessionLocal()
    try:
        tok = uuid.uuid4().hex
        expires = datetime.now() + timedelta(days=TOKEN_EXPIRE_DAYS)
        db.add(UserToken(
            token=tok,
            user_id=user_id,
            username=username,
            role=role,
            expires_at=expires,
        ))
        db.commit()
        return tok
    finally:
        db.close()


def validate_token(tok: str) -> Optional[dict]:
    """校验 token，返回 {user_id, username, role} 或 None"""
    db = SessionLocal()
    try:
        row = db.query(UserToken).filter(
            UserToken.token == tok,
            UserToken.revoked == False,
        ).first()
        if not row:
            return None
        if row.expires_at < datetime.now():
            return None
        return {"user_id": row.user_id, "username": row.username, "role": row.role}
    finally:
        db.close()


def revoke_token(tok: str) -> bool:
    """作废 token（退出登录）"""
    db = SessionLocal()
    try:
        row = db.query(UserToken).filter(UserToken.token == tok).first()
        if not row:
            return False
        row.revoked = True
        db.commit()
        return True
    finally:
        db.close()


# ── FastAPI 依赖：从请求中提取当前用户 ──────────────────────

def _extract_token(request: Request) -> str:
    """从 Authorization: Bearer <token> 或 query param 提取 token"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # 兼容 query param（某些场景方便）
    return request.query_params.get("token", "")


def get_current_user(request: Request) -> dict:
    """FastAPI 依赖：要求登录，返回 {user_id, username, role}"""
    tok = _extract_token(request)
    if not tok:
        raise HTTPException(401, "未登录，请先登录")
    user = validate_token(tok)
    if not user:
        raise HTTPException(401, "登录已过期或已失效，请重新登录")
    return user


def require_role(*roles: str):
    """FastAPI 依赖工厂：要求用户角色在指定列表中

    用法：
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        def admin_page(): ...
    """
    def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, f"权限不足，需要角色：{'、'.join(roles)}")
        return user
    return checker
