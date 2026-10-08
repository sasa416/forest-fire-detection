#!/bin/bash

# 森林火灾烟雾检测系统启动脚本

echo "=========================================="
echo "森林火灾烟雾检测系统启动脚本"
echo "=========================================="

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "错误: 未找到Python环境"
    exit 1
fi

# 检查Node.js环境
if ! command -v node &> /dev/null; then
    echo "错误: 未找到Node.js环境"
    exit 1
fi

# 创建必要目录
echo "创建必要目录..."
mkdir -p backend/models backend/data backend/uploads backend/logs
mkdir -p frontend/node_modules

# 初始化数据库
echo "初始化数据库..."
cd backend
python init_db.py

# 安装后端依赖
echo "安装后端依赖..."
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装前端依赖
echo "安装前端依赖..."
cd ../frontend
npm install --registry https://registry.npmmirror.com

# 启动后端服务
echo "启动后端服务..."
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# 启动前端服务
echo "启动前端服务..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo "=========================================="
echo "系统启动完成！"
echo "前端地址: http://localhost:3000"
echo "后端地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo "=========================================="

# 等待用户中断
echo "按 Ctrl+C 停止服务"
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait