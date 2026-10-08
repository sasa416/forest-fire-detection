#!/usr/bin/env python3
"""
数据库初始化脚本
创建数据库表结构
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.config import settings
from app.services import Base, engine

def init_database():
    """初始化数据库"""
    print("正在初始化数据库...")
    
    # 确保数据目录存在
    data_dir = Path("./data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    print("数据库初始化完成！")
    print(f"数据库文件: {settings.DATABASE_URL}")

if __name__ == "__main__":
    init_database()