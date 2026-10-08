# 森林火灾烟雾检测系统

基于YOLOv8的森林火灾烟雾检测系统，支持实时图像/视频检测、航拍图分析、智能告警等功能。

## 功能特性

- **图像检测**：上传图片，快速识别火焰和烟雾目标
- **视频检测**：支持视频文件和实时摄像头流检测
- **航拍分析**：大范围森林监控，火点定位与热力图生成
- **智能告警**：多级告警机制，支持短信、邮件、钉钉通知
- **数据分析**：检测统计、趋势分析、报表生成
- **模型管理**：多模型切换、版本管理、性能监控

## 技术栈

### 后端
- Python 3.12+
- FastAPI
- PyTorch / Ultralytics YOLOv8
- OpenCV
- SQLAlchemy / SQLite

### 前端
- Vue.js 3
- TypeScript
- Vite
- Tailwind CSS
- Element Plus
- ECharts

### AI模型
- YOLOv8 (COCO预训练)
- 支持多种模型变体：YOLOv8s/m/l/x

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- NVIDIA GPU (推荐RTX 3060+)
- 显存 ≥ 6GB

### 1. 克隆项目

```bash
git clone <repository-url>
cd forest-fire-detection
```

### 2. 数据准备

#### 转换数据集格式
```bash
cd backend
python convert_xml_to_yolo.py
```

#### 训练模型
```bash
python train_yolo.py
```

### 3. 启动后端服务

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 启动前端服务

```bash
cd frontend
npm install
npm run dev
```

### 5. 访问系统

- 前端地址：http://localhost:3000
- API文档：http://localhost:8000/docs
- API备用文档：http://localhost:8000/redoc

## Docker部署

### 1. 构建镜像

```bash
# 构建后端镜像
docker build -t fire-detection-backend ./backend

# 构建前端镜像
docker build -t fire-detection-frontend ./frontend
```

### 2. 启动服务

```bash
docker-compose up -d
```

### 3. 访问系统

- 前端地址：http://localhost
- API地址：http://localhost:8000

## 项目结构

```
forest-fire-detection/
├── backend/                    # 后端服务
│   ├── app/                   # 应用代码
│   │   ├── main.py           # FastAPI主程序
│   │   ├── models.py         # 数据模型
│   │   ├── services.py       # 业务逻辑
│   │   └── config.py         # 配置文件
│   ├── convert_xml_to_yolo.py # 数据转换脚本
│   ├── train_yolo.py         # 模型训练脚本
│   ├── dataset.yaml          # 数据集配置
│   ├── requirements.txt      # Python依赖
│   └── Dockerfile            # Docker配置
├── frontend/                   # 前端应用
│   ├── src/                  # 源代码
│   │   ├── views/            # 页面组件
│   │   ├── layouts/          # 布局组件
│   │   ├── router/           # 路由配置
│   │   ├── styles/           # 样式文件
│   │   └── main.ts           # 入口文件
│   ├── package.json          # Node依赖
│   ├── vite.config.ts        # Vite配置
│   ├── tailwind.config.js    # Tailwind配置
│   └── Dockerfile            # Docker配置
├── models/                     # 模型文件
├── data/                      # 数据文件
├── uploads/                   # 上传文件
├── docker-compose.yml         # Docker编排
├── PRD.md                     # 产品需求文档
└── README.md                  # 项目说明
```

## API接口

### 检测接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/detect/image` | POST | 图像检测 |
| `/api/detect/video` | POST | 视频检测 |
| `/ws/detect` | WebSocket | 实时流检测 |

### 管理接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/models` | GET | 获取模型列表 |
| `/api/models/load/{name}` | POST | 加载模型 |
| `/api/history` | GET | 获取检测历史 |
| `/api/statistics` | GET | 获取统计数据 |

### 系统接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/status` | GET | 系统状态 |

## 配置说明

### 环境变量

创建 `.env` 文件：

```env
# 模型配置
MODEL_PATH=./models/best.pt
DEFAULT_CONFIDENCE=0.5
DEFAULT_IOU_THRESHOLD=0.45

# 数据库配置
DATABASE_URL=sqlite:///./data/detection.db

# 服务配置
HOST=0.0.0.0
PORT=8000
WORKERS=4

# 告警配置
ALERT_ENABLED=true
ALERT_CHANNELS=email,sms,dingtalk
```

### 告警配置

在 `config.py` 中配置告警规则：

```python
ALERT_RULES = {
    "fire_count_threshold": 3,      # 火焰数量阈值
    "smoke_count_threshold": 5,     # 烟雾数量阈值
    "confidence_threshold": 0.8,    # 置信度阈值
    "alert_cooldown": 300,          # 告警冷却时间(秒)
}
```

## 性能优化

### 模型优化

1. **模型选择**：根据场景选择合适的模型变体
   - YOLOv8s：实时检测，速度优先
   - YOLOv8m：平衡精度与速度
   - YOLOv8l：高精度检测

2. **模型导出**：导出为ONNX格式提升推理速度
   ```bash
   python -c "from ultralytics import YOLO; model = YOLO('best.pt'); model.export(format='onnx')"
   ```

3. **量化压缩**：使用INT8量化减少模型大小
   ```bash
   yolo export model=best.pt format=onnx int8=True
   ```

### 推理优化

1. **批处理**：批量处理多张图片
2. **异步推理**：使用异步接口提升并发性能
3. **GPU加速**：确保使用GPU进行推理
4. **缓存机制**：缓存常用模型和检测结果

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

## 开发指南

### 添加新功能

1. 后端：在 `app/services.py` 中添加业务逻辑
2. 前端：在 `src/views/` 中添加页面组件
3. 路由：在 `src/router/index.ts` 中添加路由配置

### 代码规范

- Python：遵循 PEP 8 规范
- TypeScript：遵循 ESLint 规范
- Vue：遵循 Vue 3 组合式API规范

### 测试

```bash
# 后端测试
cd backend
pytest tests/

# 前端测试
cd frontend
npm run test
```

## 部署说明

### 生产环境部署

1. **服务器配置**
   - CPU：8核+
   - 内存：32GB+
   - GPU：NVIDIA Tesla T4/A10
   - 显存：16GB+
   - 磁盘：500GB+ SSD

2. **域名配置**
   - 配置域名解析
   - 申请SSL证书
   - 配置Nginx反向代理

3. **监控配置**
   - 配置Prometheus监控
   - 配置Grafana可视化
   - 配置告警通知

### 扩展部署

1. **负载均衡**：使用Nginx负载均衡
2. **数据库**：迁移到PostgreSQL
3. **缓存**：使用Redis缓存
4. **存储**：使用对象存储（OSS/S3）

## 许可证

MIT License

## 联系方式

- 项目地址：[GitHub Repository]
- 问题反馈：[Issues]
- 邮箱：[Email]

## 更新日志

### v1.0.0 (2024-09-14)
- 初始版本发布
- 支持图像检测
- 支持视频检测
- 支持航拍分析
- 支持智能告警
- 支持数据分析