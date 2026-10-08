# 森林火灾烟雾检测系统 - 进度报告

> 更新时间：2026-09-14

## 一、已完成

### 1. 产品需求文档（PRD）✅
`PRD.md` — 产品定位、目标用户、6 大功能模块、非功能需求、技术架构、数据库设计、API 设计、部署方案、9 周排期、风险评估、成功指标。

### 2. UI 设计 ✅
`ui-designs/` 目录，5 个可交互设计稿：

| 文件 | 页面 | 核心内容 |
|------|------|---------|
| `login.html` | 登录页 | 森林主题背景、居中卡片 |
| `dashboard.html` | 首页仪表盘 | 统计卡片、快捷操作、检测记录、告警列表 |
| `live-monitor.html` | 实时监控 | 多路点位、MJPEG 画面、检测框叠加、实时数据面板 |
| `image-detect.html` | 图像检测 | 上传、调参、结果展示、边界框标注 |
| `admin.html` | 后台管理 | 用户/角色/权限、系统配置、告警规则、数据备份 |
| `index.html` | 设计总览 | 设计规范 + 全部页面入口 |

设计规范详见 `UI_DESIGN.md`。

### 3. 后端服务 ✅
`backend/`

| 文件 | 职责 |
|------|------|
| `app/main.py` | FastAPI 主服务，注册路由、启动/关闭钩子 |
| `app/config.py` | 配置管理（模型、检测参数、告警规则） |
| `app/models.py` | Pydantic 数据模型 |
| `app/services.py` | 检测 / 模型 / 历史记录服务 + ORM 表 |
| `app/stream_service.py` | **实时流服务**：多路 RTSP 接入、抽帧推理、MJPEG 推流 |
| `app/routers/stream.py` | 实时监控 API 路由 |
| `convert_xml_to_yolo.py` | XML → YOLO 标注转换 |
| `train_yolo.py` | YOLOv8 训练脚本 |
| `init_db.py` | 数据库初始化 |

**实时流核心设计**：
- 每路流独立线程读取，不阻塞 asyncio 事件循环
- 按 `frame_interval` 跳帧推理，非推理帧复用最近结果画框，保证画面流畅
- 线程锁保护共享帧，支持多客户端同时拉取同一路流
- RTSP 强制 TCP 传输（`rtsp_transport;tcp`）避免 UDP 丢包
- 告警带冷却时间，避免刷屏

### 4. 前端核心页面 ✅
`frontend/`

| 文件 | 职责 |
|------|------|
| `src/views/LiveMonitor.vue` | 实时监控页（多路管理 + MJPEG + WS 数据面板） |
| `src/views/Dashboard.vue` | 首页仪表盘 |
| `src/views/ImageDetect.vue` | 图像检测页 |
| `src/layouts/MainLayout.vue` | 主布局（侧边栏 + 顶栏） |
| `src/router/index.ts` | 路由配置 |
| `src/api/index.ts` | API 封装 |
| `src/stores/index.ts` | Pinia 状态管理 |
| `src/types/index.ts` | TypeScript 类型定义 |

### 5. 环境验证 ✅

| 项目 | 结果 |
|------|------|
| Python | `D:\sdxx\envs\jianxi\python.exe` |
| PyTorch | 2.6.0+cu124 |
| CUDA | 可用 |
| GPU | NVIDIA GeForce RTX 4070 Laptop GPU |
| 已有依赖 | fastapi / uvicorn / pydantic / numpy / PIL |
| 待装依赖 | ultralytics / opencv-python / sqlalchemy / loguru（纯新增，不影响现有环境） |

### 6. 数据集确认 ✅
- 位置：`D:\xiaofang\fire_smoke`
- 结构：`images/` + `annotations/`（VOC XML）+ `train_list.txt` / `val_list.txt`
- 类别：`fire`（火焰）、`smoke`（烟雾）
- 已提供转换脚本 `convert_xml_to_yolo.py`

---

## 二、待完成

| 模块 | 内容 | 状态 |
|------|------|------|
| 数据转换 | 执行 XML → YOLO 格式转换，划分训练/验证集 | 待执行 |
| 模型训练 | YOLOv8s 微调，目标 mAP@0.5 ≥ 90% | 待执行 |
| 前端剩余页面 | VideoDetect / AerialDetect / AlertCenter / DataAnalysis / ModelManage / SystemSettings / Login | 待开发 |
| 前后端联调 | 接口对接、真实数据流测试 | 待执行 |
| 系统测试 | 功能、性能、压力测试 | 待执行 |
| 部署 | Docker 编排 + Nginx | 待执行 |

---

## 三、下一步

1. **安装后端依赖**（进行中）：ultralytics / opencv-python / sqlalchemy / loguru
2. **安装前端依赖**（进行中）：npm install
3. **数据转换**：运行 `convert_xml_to_yolo.py`
4. **模型训练**：运行 `train_yolo.py`，观察 mAP 曲线
5. **启动联调**：后端 8000 + 前端 3000，跑通实时监控全链路
6. **补齐剩余前端页面**

---

## 四、需要确认

1. **UI 设计是否符合预期？**（重点看 `index.html` 总览与 `live-monitor.html`）
2. **实时监控推流方案**：当前采用「后端画框 + MJPEG 推流」（方案 A），是否满足需求？是否需要升级到 WebRTC 低延迟（方案 C）？
3. **监控源**：是否有真实 RTSP 摄像头地址可以测试？还是先用本地视频文件模拟？
4. **是否继续开发剩余前端页面？**
