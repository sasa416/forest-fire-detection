#!/usr/bin/env python3
"""
创建项目必要目录
"""

import os
from pathlib import Path

def create_directories():
    """创建项目必要目录"""
    directories = [
        "models",
        "data",
        "uploads",
        "logs",
        "static/results",
        "app/__pycache__",
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"创建目录: {directory}")
    
    # 创建.gitkeep文件
    gitkeep_dirs = [
        "models",
        "data",
        "uploads",
        "logs",
        "static/results"
    ]
    
    for directory in gitkeep_dirs:
        gitkeep_path = Path(directory) / ".gitkeep"
        if not gitkeep_path.exists():
            gitkeep_path.touch()
            print(f"创建文件: {gitkeep_path}")
    
    print("目录创建完成！")

if __name__ == "__main__":
    create_directories()