@echo off
chcp 65001 >nul

echo ==========================================
echo 森林火灾烟雾检测系统启动脚本
echo ==========================================

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python环境
    pause
    exit /b 1
)

REM 检查Node.js环境
node --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Node.js环境
    pause
    exit /b 1
)

REM 创建必要目录
echo 创建必要目录...
if not exist "backend\models" mkdir "backend\models"
if not exist "backend\data" mkdir "backend\data"
if not exist "backend\uploads" mkdir "backend\uploads"
if not exist "backend\logs" mkdir "backend\logs"
if not exist "frontend\node_modules" mkdir "frontend\node_modules"

REM 初始化数据库
echo 初始化数据库...
cd backend
python init_db.py

REM 安装后端依赖
echo 安装后端依赖...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

REM 安装前端依赖
echo 安装前端依赖...
cd ..\frontend
npm install --registry https://registry.npmmirror.com

REM 启动后端服务
echo 启动后端服务...
cd ..\backend
start "后端服务" cmd /k "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

REM 启动前端服务
echo 启动前端服务...
cd ..\frontend
start "前端服务" cmd /k "npm run dev"

echo ==========================================
echo 系统启动完成！
echo 前端地址: http://localhost:3000
echo 后端地址: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo ==========================================

pause