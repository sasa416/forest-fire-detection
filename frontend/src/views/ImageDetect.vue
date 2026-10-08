<script setup lang="ts">
import { ref, reactive } from 'vue'
import { Upload, Delete, Download, ZoomIn } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

// 检测参数
const params = reactive({
  confidence: 0.3,
  iouThreshold: 0.45
})

// 上传状态
const uploading = ref(false)
const detecting = ref(false)

// 检测结果
const detectionResult = ref<any>(null)

// 上传文件列表
const fileList = ref<any[]>([])

// 图像预览
const previewVisible = ref(false)
const previewImage = ref('')

// 处理文件上传
const handleUpload = (file: any) => {
  const isImage = file.raw.type.startsWith('image/')
  const isLt10M = file.raw.size / 1024 / 1024 < 10

  if (!isImage) {
    ElMessage.error('只能上传图片文件!')
    return false
  }

  if (!isLt10M) {
    ElMessage.error('图片大小不能超过 10MB!')
    return false
  }

  return true
}

// el-upload 的 on-change 钩子：拖入或选择后触发，用于生成预览 URL
const handleChange = (file: any) => {
  if (file?.raw) {
    file.url = URL.createObjectURL(file.raw)
  }
  // 始终只保留最新一张
  if (fileList.value.length > 1) {
    fileList.value = [file]
  }
}

const handleRemove = () => {
  fileList.value = []
}

const clearFile = () => {
  fileList.value = []
}

// 开始检测 — 真实调用后端 API
const startDetection = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请先上传图片')
    return
  }

  detecting.value = true

  try {
    const formData = new FormData()
    formData.append('file', fileList.value[0].raw)

    const res = await fetch(
      `/api/detect/image?confidence=${params.confidence}&iou_threshold=${params.iouThreshold}`,
      { method: 'POST', body: formData }
    )

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }

    const data = await res.json()

    detectionResult.value = {
      detectionId: data.detection_id,
      // 后端返回标注图 URL
      imageUrl: data.image_url || '',
      detections: (data.detections || []).map((d: any) => ({
        classId: d.class_id,
        className: d.class_name,
        confidence: d.confidence,
        bbox: {
          x1: Math.round(d.bbox?.x1 || 0),
          y1: Math.round(d.bbox?.y1 || 0),
          x2: Math.round(d.bbox?.x2 || 0),
          y2: Math.round(d.bbox?.y2 || 0)
        }
      })),
      fireCount: data.fire_count || 0,
      smokeCount: data.smoke_count || 0,
      inferenceTime: data.inference_time || 0,
      imageWidth: data.image_width || 0,
      imageHeight: data.image_height || 0,
      timestamp: data.timestamp || new Date().toISOString(),
      modelName: data.model_name || 'fire_smoke_v3',
      confidenceThreshold: data.confidence_threshold || params.confidence,
      iouThreshold: data.iou_threshold || params.iouThreshold,
      // 火灾风险报告（后端 risk 字段）
      risk: data.risk || null
    }

    if (data.fire_count === 0 && data.smoke_count === 0) {
      ElMessage.success('检测完成 — 未发现火焰或烟雾')
    } else {
      ElMessage.success(`检测完成 — 火焰 ${data.fire_count}、烟雾 ${data.smoke_count}`)
    }
  } catch (error: any) {
    ElMessage.error('检测失败: ' + (error.message || error))
  } finally {
    detecting.value = false
  }
}

// 清除结果
const clearResult = () => {
  detectionResult.value = null
  fileList.value = []
}

// 预览图片
const handlePreview = (file: any) => {
  previewImage.value = URL.createObjectURL(file.raw)
  previewVisible.value = true
}

// 下载标注结果图
const downloadResult = () => {
  if (detectionResult.value?.imageUrl) {
    const a = document.createElement('a')
    a.href = detectionResult.value.imageUrl
    a.download = `detection_${detectionResult.value.detectionId}.jpg`
    a.click()
  } else {
    ElMessage.info('暂无可下载的标注图')
  }
}

// 风险等级配色：与视频检测页保持同一套色阶
const getRiskColor = (score: number) => {
  if (score >= 70) return '#f5222d'
  if (score >= 45) return '#fa8c16'
  if (score >= 20) return '#e6a23c'
  return '#52c41a'
}
</script>

<template>
  <div class="image-detect">
    <el-card class="detect-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>图像检测</span>
          <div class="header-actions">
            <el-button type="primary" @click="startDetection" :loading="detecting">
              <el-icon><Upload /></el-icon>
              开始检测
            </el-button>
            <el-button @click="clearResult">
              <el-icon><Delete /></el-icon>
              清除
            </el-button>
          </div>
        </div>
      </template>

      <div class="detect-content">
        <!-- 上传区域 -->
        <div class="upload-section">
          <el-upload
            v-model:file-list="fileList"
            class="upload-area"
            drag
            action="#"
            :auto-upload="false"
            :before-upload="handleUpload"
            :on-change="handleChange"
            :on-remove="handleRemove"
            :on-preview="handlePreview"
            :show-file-list="false"
            :limit="1"
            accept="image/*"
          >
            <!-- 没选图时显示拖拽提示 -->
            <div v-if="!fileList.length" class="upload-content">
              <el-icon :size="48" class="upload-icon"><Upload /></el-icon>
              <div class="upload-text">将图片拖到此处，或<em>点击上传</em></div>
              <div class="upload-hint">支持 JPG、PNG、BMP、WebP 格式，最大 10MB</div>
            </div>

            <!-- 选中后框里直接显示预览图 + 替换按钮 -->
            <div v-else class="upload-preview">
              <img :src="fileList[0].url || ''" alt="已选图片" class="upload-preview-img" />
              <div class="upload-preview-overlay">
                <div class="upload-preview-name">{{ fileList[0].name }}</div>
                <el-button size="small" type="danger" plain @click.stop="clearFile">重新选择</el-button>
              </div>
            </div>
          </el-upload>

          <!-- 参数配置 -->
          <div class="params-section">
            <h4>检测参数</h4>
            <el-form label-width="100px">
              <el-form-item label="置信度阈值">
                <el-slider
                  v-model="params.confidence"
                  :min="0.05"
                  :max="0.9"
                  :step="0.05"
                  show-input
                />
              </el-form-item>
              <el-form-item label="IOU阈值">
                <el-slider
                  v-model="params.iouThreshold"
                  :min="0.05"
                  :max="0.9"
                  :step="0.05"
                  show-input
                />
              </el-form-item>
            </el-form>
          </div>
        </div>

        <!-- 检测结果 -->
        <div class="result-section" v-if="detectionResult">
          <h4>检测结果</h4>

          <!-- 标注结果图 -->
          <div class="result-image-container" v-if="detectionResult.imageUrl">
            <img :src="detectionResult.imageUrl" class="result-image" alt="检测标注图" />
          </div>

          <!-- 火灾风险报告 -->
          <div class="risk-report" v-if="detectionResult.risk">
            <div class="risk-banner" :style="{ borderColor: getRiskColor(detectionResult.risk.score) }">
              <div class="risk-score" :style="{ color: getRiskColor(detectionResult.risk.score) }">
                {{ detectionResult.risk.score }}
              </div>
              <div class="risk-info">
                <div class="risk-level" :style="{ color: getRiskColor(detectionResult.risk.score) }">
                  {{ detectionResult.risk.level }}
                </div>
                <div class="risk-desc">{{ detectionResult.risk.advice }}</div>
              </div>
            </div>

            <ul class="risk-reasons" v-if="detectionResult.risk.reasons && detectionResult.risk.reasons.length">
              <li v-for="(reason, idx) in detectionResult.risk.reasons" :key="idx">{{ reason }}</li>
            </ul>

            <div class="risk-metrics">
              <span>最高置信度 <b>{{ (detectionResult.risk.max_confidence * 100).toFixed(1) }}%</b></span>
              <span>火焰占比 <b>{{ (detectionResult.risk.max_fire_area_ratio * 100).toFixed(1) }}%</b></span>
              <span>烟雾占比 <b>{{ (detectionResult.risk.max_smoke_area_ratio * 100).toFixed(1) }}%</b></span>
            </div>
          </div>

          <!-- 结果统计 -->
          <div class="result-stats">
            <div class="stat-item">
              <span class="stat-label">火焰数量</span>
              <span class="stat-value fire">{{ detectionResult.fireCount }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">烟雾数量</span>
              <span class="stat-value smoke">{{ detectionResult.smokeCount }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">推理时间</span>
              <span class="stat-value">{{ detectionResult.inferenceTime.toFixed(1) }}ms</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">图像尺寸</span>
              <span class="stat-value">{{ detectionResult.imageWidth }}×{{ detectionResult.imageHeight }}</span>
            </div>
          </div>

          <!-- 检测详情 -->
          <el-table v-if="detectionResult.detections.length" :data="detectionResult.detections" style="width: 100%; margin-top: 16px;">
            <el-table-column prop="className" label="类别" width="100">
              <template #default="{ row }">
                <el-tag :type="row.className === 'fire' ? 'danger' : 'warning'" size="small">
                  {{ row.className === 'fire' ? '火焰' : '烟雾' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="confidence" label="置信度" width="100">
              <template #default="{ row }">
                <span :style="{ color: row.confidence > 0.9 ? '#52c41a' : '#fa8c16' }">
                  {{ (row.confidence * 100).toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="位置">
              <template #default="{ row }">
                ({{ row.bbox.x1 }}, {{ row.bbox.y1 }}) - ({{ row.bbox.x2 }}, {{ row.bbox.y2 }})
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="no-detection">
            <el-icon :size="40" style="color:#52c41a"><CircleCheck /></el-icon>
            <p>未检测到火焰或烟雾</p>
          </div>

          <!-- 操作按钮 -->
          <div class="result-actions">
            <el-button type="primary" @click="downloadResult">
              <el-icon><Download /></el-icon>
              下载标注图
            </el-button>
            <el-button @click="previewVisible = true" v-if="detectionResult.imageUrl">
              <el-icon><ZoomIn /></el-icon>
              预览标注图
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 图片预览 -->
    <el-dialog v-model="previewVisible" title="图片预览" width="80%">
      <div class="preview-container">
        <img :src="previewImage" class="preview-image" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.image-detect {
  height: 100%;
}

.detect-card {
  height: 100%;
}

.detect-card :deep(.el-card__body) {
  height: calc(100% - 60px);
  padding: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.detect-content {
  display: flex;
  height: 100%;
  gap: 20px;
  padding: 20px;
}

.upload-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.upload-area {
  flex: 1;
}

.upload-area :deep(.el-upload) {
  width: 100%;
  height: 100%;
}

.upload-area :deep(.el-upload-dragger) {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  overflow: hidden;
}

.upload-preview {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
}

.upload-preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.upload-preview-overlay {
  position: absolute;
  bottom: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.upload-preview-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.upload-content {
  text-align: center;
}

.upload-icon {
  color: #c0c4cc;
  margin-bottom: 16px;
}

.upload-text {
  color: #606266;
  font-size: 14px;
  margin-bottom: 8px;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-hint {
  color: #909399;
  font-size: 12px;
}

.params-section {
  background-color: #fafafa;
  padding: 16px;
  border-radius: 8px;
}

.params-section h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.result-section {
  flex: 1;
  background-color: #fafafa;
  padding: 16px;
  border-radius: 8px;
  overflow-y: auto;
}

.result-section h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.result-image-container {
  margin-bottom: 16px;
  text-align: center;
}

.result-image {
  max-width: 100%;
  max-height: 400px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.risk-report {
  margin-bottom: 16px;
}

.risk-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  background-color: white;
  border-left: 4px solid;
  border-radius: 8px;
}

.risk-score {
  font-size: 36px;
  font-weight: 600;
  line-height: 1;
  min-width: 64px;
  text-align: center;
}

.risk-info {
  flex: 1;
}

.risk-level {
  font-size: 16px;
  font-weight: 600;
}

.risk-desc {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.risk-reasons {
  margin: 10px 0 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: #606266;
  line-height: 1.9;
}

.risk-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 10px;
  font-size: 13px;
  color: #909399;
}

.risk-metrics b {
  color: #303133;
}

.result-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background-color: white;
  border-radius: 8px;
}

.stat-label {
  font-size: 14px;
  color: #666;
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.stat-value.fire {
  color: #ef4444;
}

.stat-value.smoke {
  color: #f59e0b;
}

.no-detection {
  text-align: center;
  padding: 24px 0;
  color: #52c41a;
  font-size: 14px;
}

.result-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.preview-container {
  text-align: center;
}

.preview-image {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}
</style>