# 森林火灾烟雾检测系统 - 项目结构说明

## 项目概述

本项目是一个基于YOLOv8的森林火灾烟雾检测系统，包含后端API服务和前端Web界面，支持实时图像/视频检测、航拍图分析、智能告警等功能。

## 完整项目结构

```
forest-fire-detection/
├── README.md                          # 项目说明文档
├── PRD.md                            # 产品需求文档
├── UI_DESIGN.md                      # UI设计规范
├── PROGRESS.md                       # 进度报告
├── PROJECT_STRUCTURE.md              # 项目结构说明（本文件）
├── .gitignore                        # Git忽略配置
├── docker-compose.yml                # Docker编排配置
├── start.sh                          # Linux/macOS启动脚本
├── start.bat                         # Windows启动脚本
│
├── backend/                          # 后端服务
│   ├── app/                         # 应用代码
│   │   ├── __init__.py              # 包初始化
│   │   ├── main.py                  # FastAPI主程序
│   │   ├── models.py                # 数据模型定义
│   │   ├── services.py              # 业务逻辑服务
│   │   ├── stream_service.py        # 实时流处理服务（RTSP/MJPEG）
│   │   ├── config.py                # 配置文件
│   │   └── routers/                 # API路由
│   │       └── stream.py            # 实时监控接口
│   ├── convert_xml_to_yolo.py       # 数据格式转换脚本
│   ├── train_yolo.py                # 模型训练脚本
│   ├── init_db.py                   # 数据库初始化脚本
│   ├── dataset.yaml                 # 数据集配置文件
│   ├── requirements.txt             # Python依赖
│   ├── Dockerfile                   # Docker配置
│   └── .env                         # 环境变量配置
│
├── frontend/                         # 前端应用
│   ├── src/                         # 源代码
│   │   ├── api/                     # API服务
│   │   │   └── index.ts             # API接口定义
│   │   ├── assets/                  # 静态资源
│   │   │   └── logo.svg             # Logo图标
│   │   ├── layouts/                 # 布局组件
│   │   │   └── MainLayout.vue       # 主布局
│   │   ├── router/                  # 路由配置
│   │   │   └── index.ts             # 路由定义
│   │   ├── stores/                  # 状态管理
│   │   │   └── index.ts             # Pinia状态
│   │   ├── styles/                  # 样式文件
│   │   │   └── index.css            # 全局样式
│   │   ├── types/                   # 类型定义
│   │   │   └── index.ts             # TypeScript类型
│   │   ├── views/                   # 页面组件
│   │   │   ├── Dashboard.vue        # 首页仪表盘
│   │   │   ├── LiveMonitor.vue      # 实时监控
│   │   │   ├── ImageDetect.vue      # 图像检测
│   │   │   ├── VideoDetect.vue      # 视频检测
│   │   │   ├── AerialDetect.vue     # 航拍分析
│   │   │   ├── AlertCenter.vue      # 告警中心
│   │   │   ├── DataAnalysis.vue     # 数据分析
│   │   │   ├── ModelManage.vue      # 模型管理
│   │   │   ├── SystemSettings.vue   # 系统设置
│   │   │   ├── Login.vue            # 登录页
│   │   │   └── NotFound.vue         # 404页面
│   │   ├── App.vue                  # 根组件
│   │   ├── main.ts                  # 入口文件
│   │   └── env.d.ts                 # 环境类型声明
│   ├── package.json                 # Node.js依赖
│   ├── vite.config.ts               # Vite配置
│   ├── tsconfig.json                # TypeScript配置
│   ├── tsconfig.node.json           # Node.js TypeScript配置
│   ├── tailwind.config.js           # Tailwind CSS配置
│   ├── postcss.config.js            # PostCSS配置
│   ├── nginx.conf                   # Nginx配置
│   ├── Dockerfile                   # Docker配置
│   └── index.html                   # HTML入口
│
├── models/                           # 模型文件目录
│   └── .gitkeep                     # 保持目录结构
│
├── data/                            # 数据文件目录
│   └── .gitkeep                     # 保持目录结构
│
├── uploads/                         # 上传文件目录
│   └── .gitkeep                     # 保持目录结构
│
└── static/                          # 静态文件目录
    └── results/                     # 检测结果
        └── .gitkeep                 # 保持目录结构
```

## 核心模块说明

### 1. 后端模块 (backend/)

#### 1.1 FastAPI应用 (app/main.py)
- RESTful API接口设计
- 支持图像检测、视频检测、WebSocket实时检测
- 健康检查、模型管理、历史记录查询
- CORS跨域支持

#### 1.2 数据模型 (app/models.py)
- Pydantic数据验证
- 检测结果、历史记录、模型信息等数据结构
- 告警系统数据模型

#### 1.3 业务服务 (app/services.py)
- **DetectionService**: 检测服务，实现图像/视频检测
- **ModelService**: 模型管理服务
- **HistoryService**: 历史记录服务
- SQLAlchemy ORM数据库操作

#### 1.4 配置管理 (app/config.py)
- 环境变量配置
- 模型路径、检测参数配置
- 告警规则配置

#### 1.5 数据处理脚本
- **convert_xml_to_yolo.py**: XML标注转YOLO格式
- **train_yolo.py**: YOLOv8模型训练
- **init_db.py**: 数据库初始化

### 2. 前端模块 (frontend/)

#### 2.1 Vue3应用架构
- Vue 3 + Composition API
- TypeScript类型安全
- Pinia状态管理
- Vue Router路由管理

#### 2.2 页面组件
- **Dashboard**: 首页仪表盘，展示统计信息
- **ImageDetect**: 图像检测页面
- **VideoDetect**: 视频检测页面
- **AerialDetect**: 航拍分析页面
- **AlertCenter**: 告警中心
- **DataAnalysis**: 数据分析
- **ModelManage**: 模型管理
- **SystemSettings**: 系统设置

#### 2.3 API服务 (api/index.ts)
- Axios HTTP客户端
- 请求/响应拦截器
- 类型安全的API接口

#### 2.4 状态管理 (stores/index.ts)
- 检测状态管理
- 模型状态管理
- 统计状态管理
- 系统状态管理
- 告警状态管理

#### 2.5 样式系统
- Tailwind CSS工具类
- Element Plus组件库
- 自定义主题变量

### 3. 部署配置

#### 3.1 Docker部署
- **docker-compose.yml**: 多容器编排
- **backend/Dockerfile**: 后端镜像
- **frontend/Dockerfile**: 前端镜像
- **nginx.conf**: Nginx反向代理配置

#### 3.2 启动脚本
- **start.sh**: Linux/macOS启动脚本
- **start.bat**: Windows启动脚本

## 数据流

```
用户上传 → 前端界面 → API请求 → FastAPI后端 → YOLOv8推理 → 结果返回
                                    ↓
                              数据库存储 → 历史记录
                                    ↓
                              告警判断 → 告警通知
                                    ↓
                              结果展示 → 数据可视化
```

## 技术栈详情

### 后端技术栈
| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.12+ | 主要开发语言 |
| FastAPI | 0.100+ | Web框架 |
| PyTorch | 2.0+ | 深度学习框架 |
| Ultralytics | 8.0+ | YOLOv8实现 |
| OpenCV | 4.8+ | 图像处理 |
| SQLAlchemy | 2.0+ | ORM框架 |
| SQLite | - | 数据存储 |
| Pydantic | 2.0+ | 数据验证 |
| Loguru | 0.7+ | 日志管理 |

### 前端技术栈
| 技术 | 版本 | 用途 |
|------|------|------|
| Vue.js | 3.x | 前端框架 |
| TypeScript | 5.x | 类型系统 |
| Vite | 4.x | 构建工具 |
| Tailwind CSS | 3.x | CSS框架 |
| Element Plus | 2.x | UI组件库 |
| ECharts | 5.x | 数据可视化 |
| Axios | 1.x | HTTP客户端 |
| Pinia | 2.x | 状态管理 |

### AI模型
| 模型 | 参数量 | mAP@0.5 | 推理速度 | 适用场景 |
|------|--------|---------|----------|----------|
| YOLOv8n | 3.2M | 37.3% | 最快 | 边缘设备 |
| YOLOv8s | 11.2M | 44.9% | 快 | 实时检测（推荐） |
| YOLOv8m | 25.9M | 50.2% | 中等 | 平衡精度与速度 |
| YOLOv8l | 43.7M | 52.9% | 较慢 | 高精度检测 |
| YOLOv8x | 68.2M | 53.9% | 慢 | 最高精度 |

## API接口文档

### 核心接口

#### 实时监控接口
```http
GET    /api/stream/sources                  # 获取所有监控点位
POST   /api/stream/sources                  # 新增点位 (rtsp/rtmp/http/file)
DELETE /api/stream/sources/{id}             # 删除点位
POST   /api/stream/sources/{id}/start       # 启动流
POST   /api/stream/sources/{id}/stop        # 停止流
PATCH  /api/stream/sources/{id}/params      # 运行时调参（实时生效）
GET    /api/stream/sources/{id}/detections  # 最新检测结果
GET    /api/stream/sources/{id}/mjpeg       # MJPEG 实时视频流
WS     /api/stream/ws/{id}                  # WebSocket 实时检测数据
```

#### 检测接口
```http
POST /api/detect/image
Content-Type: multipart/form-data

参数:
- file: 图像文件 (必填)
- confidence: 置信度阈值 (可选, 默认0.5)
- iou_threshold: IOU阈值 (可选, 默认0.45)
```

#### 视频检测接口
```http
POST /api/detect/video
Content-Type: multipart/form-data

参数:
- file: 视频文件 (必填)
- confidence: 置信度阈值 (可选)
- iou_threshold: IOU阈值 (可选)
- frame_interval: 帧间隔 (可选, 默认30)
```

#### 模型管理接口
```http
GET /api/models
GET /api/models/current
POST /api/models/load/{model_name}
```

#### 历史记录接口
```http
GET /api/history
GET /api/history/{detection_id}
GET /api/statistics
```

## 部署方案

### 开发环境部署
```bash
# 1. 克隆项目
git clone <repository-url>
cd forest-fire-detection

# 2. 启动后端
cd backend
pip install -r requirements.txt
python init_db.py
uvicorn app.main:app --reload

# 3. 启动前端
cd frontend
npm install
npm run dev
```

### Docker部署
```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 生产环境部署
```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
vim backend/.env

# 2. 构建前端
cd frontend
npm run build

# 3. 部署到Nginx
cp -r dist/* /var/www/html/

# 4. 配置Nginx
cp nginx.conf /etc/nginx/conf.d/fire-detection.conf
nginx -t && systemctl reload nginx
```

## 开发指南

### 添加新功能

#### 后端添加新接口
1. 在 `app/models.py` 中定义数据模型
2. 在 `app/services.py` 中实现业务逻辑
3. 在 `app/main.py` 中添加API路由

#### 前端添加新页面
1. 在 `src/views/` 中创建页面组件
2. 在 `src/router/index.ts` 中添加路由配置
3. 在 `src/api/index.ts` 中添加API接口

### 代码规范

#### Python代码规范
- 遵循 PEP 8 规范
- 使用类型注解
- 编写文档字符串
- 使用 Loguru 记录日志

#### TypeScript代码规范
- 遵循 ESLint 规范
- 使用接口定义数据结构
- 使用组合式API
- 组件命名使用PascalCase

### 测试

#### 后端测试
```bash
cd backend
pytest tests/
```

#### 前端测试
```bash
cd frontend
npm run test
```

## 性能优化

### 模型优化
1. **模型选择**: 根据场景选择合适的模型变体
2. **模型导出**: 导出为ONNX格式提升推理速度
3. **量化压缩**: 使用INT8量化减少模型大小
4. **TensorRT**: 使用NVIDIA TensorRT加速推理

### 推理优化
1. **批处理**: 批量处理多张图片
2. **异步推理**: 使用异步接口提升并发性能
3. **GPU加速**: 确保使用GPU进行推理
4. **缓存机制**: 缓存常用模型和检测结果

### 前端优化
1. **代码分割**: 使用动态导入进行代码分割
2. **图片优化**: 压缩图片，使用WebP格式
3. **缓存策略**: 合理设置缓存策略
4. **CDN加速**: 使用CDN加速静态资源

## 常见问题

### Q: 如何提高检测精度？
A:
1. 增加训练数据量
2. 调整训练参数（epochs、lr0等）
3. 使用更大的模型（YOLOv8m/l/x）
4. 进行数据增强
5. 调整置信度阈值

### Q: 如何减少误报？
A:
1. 提高置信度阈值
2. 增加后处理规则
3. 使用多模型融合
4. 结合时序信息判断

### Q: 视频流延迟高怎么办？
A:
1. 降低输入分辨率
2. 使用轻量级模型（YOLOv8s）
3. 优化推理流程
4. 使用GPU加速
5. 减少帧间隔

### Q: 如何扩展新数据源？
A:
1. 在 `DetectionService` 中添加新的检测方法
2. 实现数据源接入接口
3. 添加相应的API接口
4. 前端添加对应的界面

## 版本历史

### v1.0.0 (2024-09-14)
- 初始版本发布
- 支持图像检测
- 支持视频检测
- 支持航拍分析
- 支持智能告警
- 支持数据分析

## 许可证

MIT License

## 联系方式

- 项目地址: [GitHub Repository]
- 问题反馈: [Issues]
- 邮箱: [Email]