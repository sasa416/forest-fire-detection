# 森林火灾烟雾检测系统 - UI设计规范

## 设计原则

### 1. 视觉风格
- **主题色**：森林绿 (#16a34a) + 深蓝 (#001529)
- **辅助色**：火焰红 (#ef4444)、烟雾橙 (#f59e0b)、警告黄 (#eab308)
- **中性色**：灰色系 (#f8fafc, #e2e8f0, #94a3b8, #64748b, #334155, #1e293b)
- **圆角**：8px (卡片)、6px (按钮)、4px (输入框)
- **阴影**：0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)

### 2. 布局规范
- **侧边栏宽度**：220px (展开) / 64px (收起)
- **顶部栏高度**：60px
- **内容区间距**：24px
- **卡片内边距**：20px
- **响应式断点**：768px (移动端)、1024px (平板)、1280px (桌面)

### 3. 字体规范
- **主字体**：-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif
- **标题字号**：28px (H1)、24px (H2)、20px (H3)、16px (H4)
- **正文字号**：14px
- **辅助文字**：12px
- **字体粗细**：600 (标题)、400 (正文)

### 4. 组件规范
- **按钮**：高度 36px，圆角 6px
- **输入框**：高度 36px，圆角 4px
- **卡片**：圆角 8px，阴影 0 1px 3px rgba(0,0,0,0.1)
- **表格**：行高 48px，表头背景 #f8fafc

---

## 页面设计

### 1. 登录页
**设计要点**：
- 居中卡片布局
- 背景：森林/山脉渐变背景
- Logo + 系统名称
- 表单：用户名、密码、记住我、登录按钮
- 底部版权信息

### 2. 主布局
**结构**：
- 左侧边栏：Logo + 导航菜单
- 顶部栏：面包屑 + 用户信息 + 通知
- 内容区：路由视图

### 3. 首页仪表盘
**模块**：
- 统计卡片：今日检测、火焰数量、烟雾数量、告警数量
- 快捷操作：图像检测、视频检测、航拍分析、告警中心
- 最近检测记录表格
- 最新告警列表
- 模型状态信息

### 4. 实时监控页
**布局**：
- 左侧：监控点位列表（多路 RTSP 摄像头，显示连接状态与 FPS）
- 中间：MJPEG 实时画面 + 检测框叠加 + 参数调整栏
- 右侧：WebSocket 实时检测数据面板（火焰/烟雾计数、推理耗时、目标列表）

**关键设计**：
- 视频区域自适应，`object-fit: contain` 避免画面拉伸
- 断流自动重连（1.5 秒间隔），切换点位强制刷新画面
- 参数（置信度/IOU/跳帧）调整实时生效，无需重启流
- 状态点区分：运行中（绿）/ 连接中（橙）/ 异常（红）/ 待机（灰）

### 5. 图像检测页
**布局**：
- 左侧：上传区域 + 参数配置
- 右侧：检测结果展示
- 底部：检测详情表格

### 6. 视频检测页
**布局**：
- 视频源选择：本地文件 / 摄像头流 / URL
- 视频预览窗口
- 检测控制面板
- 检测日志

### 7. 后台管理系统
**功能模块**：
- 用户管理
- 角色权限管理
- 系统配置
- 告警规则配置
- 模型管理
- 数据备份与恢复
- 系统日志
- 数据统计

---

## 组件库

### 按钮类型
```html
<!-- 主要按钮 -->
<button class="btn btn-primary">主要操作</button>

<!-- 次要按钮 -->
<button class="btn btn-secondary">次要操作</button>

<!-- 危险按钮 -->
<button class="btn btn-danger">删除</button>

<!-- 文字按钮 -->
<button class="btn btn-text">查看详情</button>
```

### 卡片组件
```html
<div class="card">
  <div class="card-header">
    <h3>卡片标题</h3>
    <button class="btn btn-text">操作</button>
  </div>
  <div class="card-body">
    卡片内容
  </div>
</div>
```

### 表格组件
```html
<table class="table">
  <thead>
    <tr>
      <th>列标题</th>
      <th>列标题</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>数据</td>
      <td>数据</td>
    </tr>
  </tbody>
</table>
```

### 表单组件
```html
<div class="form-group">
  <label class="form-label">标签</label>
  <input type="text" class="form-input" placeholder="请输入">
  <span class="form-hint">提示信息</span>
</div>
```

---

## 图标系统

使用 Element Plus Icons Vue 图标库

### 常用图标
- 首页：House
- 图像检测：Picture
- 视频检测：VideoCamera
- 航拍分析：Location
- 告警中心：Bell
- 数据分析：DataAnalysis
- 模型管理：Setting
- 系统设置：Tools
- 用户管理：User
- 角色管理：UserFilled
- 日志管理：Document
- 数据备份：Download
- 数据恢复：Upload

---

## 响应式设计

### 移动端 (< 768px)
- 侧边栏隐藏，显示汉堡菜单
- 内容区单列布局
- 统计卡片垂直堆叠
- 表格横向滚动

### 平板 (768px - 1023px)
- 侧边栏收起为图标模式
- 内容区两列布局
- 统计卡片两列显示

### 桌面 (≥ 1024px)
- 侧边栏完整显示
- 内容区多列布局
- 统计卡片四列显示

---

## 交互动效

### 页面切换
- 淡入淡出效果
- 持续时间：300ms
- 缓动函数：ease-in-out

### 按钮交互
- 悬停：颜色变深 10%
- 点击：颜色变深 20%
- 禁用：透明度 50%

### 卡片交互
- 悬停：阴影增强
- 点击：轻微缩放 (0.98)

### 加载状态
- 骨架屏加载
- 旋转加载图标
- 进度条

---

## 颜色系统

### 主色调
```css
:root {
  --primary-50: #f0fdf4;
  --primary-100: #dcfce7;
  --primary-200: #bbf7d0;
  --primary-300: #86efac;
  --primary-400: #4ade80;
  --primary-500: #22c55e;
  --primary-600: #16a34a;
  --primary-700: #15803d;
  --primary-800: #166534;
  --primary-900: #14532d;
}
```

### 语义色
```css
:root {
  --danger: #ef4444;
  --warning: #f59e0b;
  --success: #22c55e;
  --info: #3b82f6;
}
```

### 中性色
```css
:root {
  --gray-50: #f8fafc;
  --gray-100: #f1f5f9;
  --gray-200: #e2e8f0;
  --gray-300: #cbd5e1;
  --gray-400: #94a3b8;
  --gray-500: #64748b;
  --gray-600: #475569;
  --gray-700: #334155;
  --gray-800: #1e293b;
  --gray-900: #0f172a;
}
```

---

## 设计资源

### 设计工具
- Figma (推荐)
- Sketch
- Adobe XD

### 图标库
- Element Plus Icons
- Heroicons
- Lucide Icons

### 图片资源
- Unsplash (免费高质量图片)
- Pexels (免费图片)
- Pixabay (免费图片)

---

## 设计交付物

### 1. 设计稿
- 登录页设计
- 主布局设计
- 各页面详细设计
- 组件库设计

### 2. 切图资源
- Logo (SVG/PNG)
- 图标 (SVG)
- 背景图 (JPG/PNG)

### 3. 设计规范文档
- 颜色规范
- 字体规范
- 组件规范
- 间距规范

### 4. 交互原型
- 页面跳转逻辑
- 交互流程图
- 动效说明