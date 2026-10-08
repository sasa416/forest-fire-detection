<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, VideoPlay, Download, Delete } from '@element-plus/icons-vue'

interface Detection {
  class_name: string
  confidence: number
  bbox: number[]
}

interface DetectionSummary {
  frame: number
  time: number
  fire: number
  smoke: number
  fire_conf: number
  smoke_conf: number
}

const videoSrc = ref('')
const resultVideoSrc = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const uploadedFile = ref<File | null>(null)
const detecting = ref(false)
const detected = ref(false)
const progress = ref(0)
const resultImages = ref<string[]>([])

const params = reactive({
  confidence: 0.25,
  iouThreshold: 0.45,
  frameInterval: 3
})

const summary = reactive({
  totalFrames: 0,
  sampledFrames: 0,
  detectedFrames: 0,
  fireTotal: 0,
  smokeTotal: 0,
  maxFireConf: 0,
  maxSmokeConf: 0,
  riskLevel: '',
  riskScore: 0,
  duration: 0,
  fps: 0,
  width: 0,
  height: 0
})

const alertMoments = ref<DetectionSummary[]>([])

const handleFileChange = (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['mp4', 'avi', 'mov', 'mkv'].includes(ext || '')) {
    ElMessage.error('仅支持 mp4/avi/mov/mkv 格式')
    return
  }
  uploadedFile.value = file
  videoSrc.value = URL.createObjectURL(file)
  detected.value = false
  resultVideoSrc.value = ''
  resultImages.value = []
  alertMoments.value = []
}

const startDetection = async () => {
  if (!uploadedFile.value) {
    ElMessage.warning('请先上传视频文件')
    return
  }
  detecting.value = true
  progress.value = 0
  detected.value = false

  const formData = new FormData()
  formData.append('file', uploadedFile.value)
  formData.append('confidence', String(params.confidence))
  formData.append('iou_threshold', String(params.iouThreshold))
  formData.append('frame_interval', String(params.frameInterval))

  try {
    const res = await fetch('/api/detect/video', {
      method: 'POST',
      body: formData
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()

    summary.totalFrames = data.total_frames || 0
    summary.sampledFrames = data.sampled_frames || 0
    summary.detectedFrames = data.detected_frames || 0
    summary.fireTotal = data.fire_total || 0
    summary.smokeTotal = data.smoke_total || 0
    summary.maxFireConf = data.max_fire_conf || 0
    summary.maxSmokeConf = data.max_smoke_conf || 0
    summary.riskLevel = data.risk_level || '无风险'
    summary.riskScore = data.risk_score || 0
    summary.duration = data.duration || 0
    summary.fps = data.fps || 0
    summary.width = data.width || 0
    summary.height = data.height || 0
    alertMoments.value = data.alert_moments || []
    if (data.result_video_url) {
      resultVideoSrc.value = data.result_video_url
    }
    if (data.result_frames) {
      resultImages.value = data.result_frames
    }
    detected.value = true
    ElMessage.success('检测完成')
  } catch (err: any) {
    ElMessage.error(`检测失败: ${err.message}`)
  } finally {
    detecting.value = false
  }
}

const getRiskColor = (score: number) => {
  if (score >= 70) return '#ef4444'
  if (score >= 40) return '#f59e0b'
  if (score > 0) return '#22c55e'
  return '#94a3b8'
}

const formatTime = (sec: number) => {
  const m = Math.floor(sec / 60)
  const s = (sec % 60).toFixed(1)
  return `${String(m).padStart(2, '0')}:${s.padStart(4, '0')}`
}

const clearAll = () => {
  videoSrc.value = ''
  resultVideoSrc.value = ''
  uploadedFile.value = null
  detected.value = false
  resultImages.value = []
  alertMoments.value = []
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<template>
  <div class="video-detect">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="card-title">视频检测</span>
          <div class="header-actions">
            <el-button type="primary" :icon="VideoPlay" :loading="detecting" @click="startDetection">
              {{ detecting ? '检测中...' : '开始检测' }}
            </el-button>
            <el-button :icon="Delete" @click="clearAll">清除</el-button>
          </div>
        </div>
      </template>

      <div class="detect-layout">
        <div class="upload-section">
          <div class="upload-area" @click="($refs.fileInput as HTMLInputElement)?.click()">
            <input ref="fileInput" type="file" accept=".mp4,.avi,.mov,.mkv" hidden @change="handleFileChange" />
            <template v-if="!videoSrc">
              <el-icon :size="48" class="upload-icon"><Upload /></el-icon>
              <p class="upload-text">点击或拖拽视频文件到此处</p>
              <p class="upload-hint">支持 MP4、AVI、MOV、MKV 格式</p>
            </template>
            <video v-else :src="videoSrc" controls class="preview-video" />
          </div>

          <div class="param-bar">
            <div class="param-item">
              <label>置信度</label>
              <el-slider v-model="params.confidence" :min="0.1" :max="0.9" :step="0.05" size="small" style="width:140px" />
              <span class="param-val">{{ params.confidence.toFixed(2) }}</span>
            </div>
            <div class="param-item">
              <label>IOU</label>
              <el-slider v-model="params.iouThreshold" :min="0.1" :max="0.9" :step="0.05" size="small" style="width:140px" />
              <span class="param-val">{{ params.iouThreshold.toFixed(2) }}</span>
            </div>
            <div class="param-item">
              <label>采样间隔</label>
              <el-input-number v-model="params.frameInterval" :min="1" :max="30" size="small" controls-position="right" style="width:100px" />
              <span class="param-val">帧</span>
            </div>
          </div>
        </div>

        <div class="result-section" v-if="detected">
          <div class="risk-banner" :style="{ borderColor: getRiskColor(summary.riskScore) }">
            <div class="risk-score" :style="{ color: getRiskColor(summary.riskScore) }">
              {{ summary.riskScore }}
            </div>
            <div class="risk-info">
              <div class="risk-level" :style="{ color: getRiskColor(summary.riskScore) }">
                {{ summary.riskLevel }}
              </div>
              <div class="risk-desc">
                {{ summary.smokeTotal > 0 ? `检出 ${summary.smokeTotal} 处烟雾` : '' }}
                {{ summary.fireTotal > 0 ? `，${summary.fireTotal} 处火焰` : '' }}
                {{ summary.riskScore === 0 ? '未检测到异常' : '' }}
              </div>
            </div>
          </div>

          <div class="stat-grid">
            <div class="stat-box">
              <div class="stat-num">{{ summary.totalFrames }}</div>
              <div class="stat-label">总帧数</div>
            </div>
            <div class="stat-box">
              <div class="stat-num">{{ summary.detectedFrames }}</div>
              <div class="stat-label">检出帧</div>
            </div>
            <div class="stat-box fire">
              <div class="stat-num">{{ summary.fireTotal }}</div>
              <div class="stat-label">火焰</div>
            </div>
            <div class="stat-box smoke">
              <div class="stat-num">{{ summary.smokeTotal }}</div>
              <div class="stat-label">烟雾</div>
            </div>
          </div>

          <div class="meta-list">
            <div class="meta-row">
              <span>视频信息</span>
              <span>{{ summary.width }}×{{ summary.height }} · {{ summary.fps.toFixed(1) }}fps · {{ summary.duration.toFixed(1) }}秒</span>
            </div>
            <div class="meta-row">
              <span>火焰最高置信度</span>
              <span>{{ (summary.maxFireConf * 100).toFixed(1) }}%</span>
            </div>
            <div class="meta-row">
              <span>烟雾最高置信度</span>
              <span>{{ (summary.maxSmokeConf * 100).toFixed(1) }}%</span>
            </div>
          </div>

          <div v-if="alertMoments.length" class="alert-moments">
            <div class="section-title">关键检测时刻 ({{ alertMoments.length }})</div>
            <div class="moment-list">
              <div v-for="(m, i) in alertMoments.slice(0, 15)" :key="i" class="moment-item">
                <span class="moment-time">{{ formatTime(m.time) }}</span>
                <span v-if="m.fire" class="tag fire">火焰 {{ m.fire }} ({{ (m.fire_conf * 100).toFixed(0) }}%)</span>
                <span v-if="m.smoke" class="tag smoke">烟雾 {{ m.smoke }} ({{ (m.smoke_conf * 100).toFixed(0) }}%)</span>
              </div>
              <div v-if="alertMoments.length > 15" class="moment-more">
                ... 共 {{ alertMoments.length }} 个检测时刻
              </div>
            </div>
          </div>

          <div v-if="resultImages.length" class="result-images">
            <div class="section-title">检测结果帧</div>
            <div class="image-grid">
              <div v-for="(img, i) in resultImages.slice(0, 6)" :key="i" class="image-item">
                <img :src="img" alt="检测帧" />
              </div>
            </div>
          </div>
        </div>

        <div v-else class="result-placeholder">
          <el-icon :size="64" class="placeholder-icon"><VideoPlay /></el-icon>
          <p>上传视频并点击「开始检测」查看结果</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.video-detect { height: 100%; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 12px; }

.detect-layout { display: flex; gap: 20px; min-height: 500px; }
.upload-section { flex: 1; display: flex; flex-direction: column; gap: 16px; }

.upload-area {
  flex: 1; min-height: 300px;
  border: 2px dashed #dcdfe6; border-radius: 8px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  cursor: pointer; transition: border-color 0.3s;
}
.upload-area:hover { border-color: #16a34a; }
.upload-icon { color: #c0c4cc; margin-bottom: 12px; }
.upload-text { color: #606266; font-size: 14px; }
.upload-hint { color: #909399; font-size: 12px; margin-top: 4px; }
.preview-video { width: 100%; max-height: 360px; border-radius: 8px; }

.param-bar {
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
  padding: 12px 16px; background: #fafafa; border-radius: 8px;
}
.param-item { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #606266; }
.param-val { font-family: ui-monospace, Menlo, Consolas, monospace; color: #303133; min-width: 32px; }

.result-section { flex: 1; display: flex; flex-direction: column; gap: 16px; }

.risk-banner {
  display: flex; align-items: center; gap: 16px;
  padding: 16px 20px; border-radius: 8px;
  border-left: 4px solid; background: #fafafa;
}
.risk-score { font-size: 36px; font-weight: 600; line-height: 1; }
.risk-level { font-size: 16px; font-weight: 600; }
.risk-desc { font-size: 13px; color: #909399; margin-top: 4px; }

.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat-box {
  text-align: center; padding: 14px; border-radius: 8px; background: #fafafa;
}
.stat-box.fire { background: #fef2f2; }
.stat-box.smoke { background: #fffbeb; }
.stat-num { font-size: 24px; font-weight: 600; color: #303133; }
.stat-box.fire .stat-num { color: #dc2626; }
.stat-box.smoke .stat-num { color: #d97706; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }

.meta-list { display: flex; flex-direction: column; }
.meta-row {
  display: flex; justify-content: space-between;
  font-size: 13px; color: #606266; padding: 8px 0;
  border-bottom: 1px dashed #f0f0f0;
}

.section-title { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 8px; }

.moment-list { max-height: 200px; overflow-y: auto; }
.moment-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.moment-time { font-family: ui-monospace, monospace; color: #909399; min-width: 50px; }
.tag { padding: 2px 8px; border-radius: 4px; font-size: 12px; color: #fff; }
.tag.fire { background: #ef4444; }
.tag.smoke { background: #f59e0b; }
.moment-more { color: #909399; font-size: 12px; padding: 4px 0; }

.image-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.image-item img { width: 100%; border-radius: 6px; }

.result-placeholder {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: #c0c4cc; font-size: 14px;
}
.placeholder-icon { margin-bottom: 12px; }
</style>