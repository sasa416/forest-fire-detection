<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, VideoPlay, VideoPause, Delete, VideoCamera } from '@element-plus/icons-vue'

interface StreamSource {
  source_id: string
  name: string
  url: string
  source_type: string
  location: string
  status: string
  fps: number
  fire_count: number
  smoke_count: number
  inference_time: number
  frame_count: number
  confidence: number
  iou_threshold: number
  frame_interval: number
  error?: string
}

interface LiveData {
  source_id: string
  name: string
  status: string
  fire_count: number
  smoke_count: number
  fps: number
  frame_count: number
  inference_time: number
  detections: Array<{
    class_id: number
    class_name: string
    confidence: number
    bbox: number[]
  }>
  timestamp: string | null
}

const sources = ref<StreamSource[]>([])
const currentId = ref<string>('')
const liveData = ref<LiveData | null>(null)
const loading = ref(false)
const showAddDialog = ref(false)
const streamKey = ref(0)

const form = reactive({
  name: '',
  url: '',
  source_type: 'rtsp',
  location: '',
  confidence: 0.3,
  iou_threshold: 0.45,
  frame_interval: 3
})

const params = reactive({
  confidence: 0.3,
  iou_threshold: 0.45,
  frame_interval: 3
})

const currentSource = computed(() =>
  sources.value.find(s => s.source_id === currentId.value) || null
)
const isRunning = computed(() => currentSource.value?.status === 'running')

const mjpegUrl = computed(() =>
  currentId.value
    ? `/api/stream/sources/${currentId.value}/mjpeg?t=${streamKey.value}`
    : ''
)

const statusText = (status: string) => {
  const map: Record<string, string> = {
    idle: '待机', connecting: '连接中', running: '运行中',
    error: '异常', stopped: '已停止'
  }
  return map[status] || status
}

let pollTimer: number | undefined
let ws: WebSocket | null = null

const fetchSources = async (silent = false) => {
  if (!silent) loading.value = true
  try {
    const res = await fetch('/api/stream/sources')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    sources.value = await res.json()
    // 首次加载自动选中第一路
    if (!currentId.value && sources.value.length) {
      selectSource(sources.value[0].source_id)
    }
  } catch (err) {
    if (!silent) ElMessage.error(`获取监控点位失败: ${err}`)
  } finally {
    loading.value = false
  }
}

const selectSource = (id: string) => {
  if (currentId.value === id) return
  currentId.value = id
  liveData.value = null
  streamKey.value++

  const src = sources.value.find(s => s.source_id === id)
  if (src) {
    params.confidence = src.confidence
    params.iou_threshold = src.iou_threshold
    params.frame_interval = src.frame_interval
  }
  connectWs(id)
}

const connectWs = (id: string) => {
  closeWs()
  // 仅在流运行时建立连接，避免无效重连
  const src = sources.value.find(s => s.source_id === id)
  if (!src || src.status !== 'running') return

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  try {
    ws = new WebSocket(`${proto}://${location.host}/api/stream/ws/${id}`)
    ws.onmessage = (e) => {
      try {
        liveData.value = JSON.parse(e.data)
      } catch {
        /* 忽略解析失败 */
      }
    }
    ws.onerror = () => { /* 静默重试由轮询接管 */ }
    ws.onclose = () => { ws = null }
  } catch {
    ws = null
  }
}

const closeWs = () => {
  if (ws) {
    ws.onclose = null
    ws.onerror = null
    ws.close()
    ws = null
  }
}

const handleStreamError = () => {
  // MJPEG 断流后 1.5 秒重连
  window.setTimeout(() => { streamKey.value++ }, 1500)
}

const addSource = async () => {
  if (!form.name.trim() || !form.url.trim()) {
    ElMessage.warning('请填写点位名称与流地址')
    return
  }
  try {
    const res = await fetch('/api/stream/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form)
    })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || `HTTP ${res.status}`)
    }
    ElMessage.success('监控点位已添加')
    showAddDialog.value = false
    Object.assign(form, {
      name: '', url: '', source_type: 'rtsp', location: '',
      confidence: 0.3, iou_threshold: 0.45, frame_interval: 3
    })
    await fetchSources(true)
  } catch (err) {
    ElMessage.error(`添加失败: ${err}`)
  }
}

const toggleSource = async (src: StreamSource) => {
  const action = src.status === 'running' ? 'stop' : 'start'
  try {
    const res = await fetch(`/api/stream/sources/${src.source_id}/${action}`, {
      method: 'POST'
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    ElMessage.success(action === 'start' ? '已启动' : '已停止')
    await fetchSources(true)
    if (action === 'start' && currentId.value === src.source_id) {
      streamKey.value++
      connectWs(src.source_id)
    }
    if (action === 'stop') closeWs()
  } catch (err) {
    ElMessage.error(`操作失败: ${err}`)
  }
}

const removeSource = async (src: StreamSource) => {
  try {
    await ElMessageBox.confirm(`确认删除监控点位「${src.name}」？`, '提示', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res = await fetch(`/api/stream/sources/${src.source_id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    ElMessage.success('已删除')
    if (currentId.value === src.source_id) {
      currentId.value = ''
      liveData.value = null
      closeWs()
    }
    await fetchSources(true)
  } catch (err) {
    ElMessage.error(`删除失败: ${err}`)
  }
}

const applyParams = async () => {
  if (!currentId.value) return
  try {
    const res = await fetch(`/api/stream/sources/${currentId.value}/params`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    ElMessage.success('参数已生效')
  } catch (err) {
    ElMessage.error(`参数更新失败: ${err}`)
  }
}

onMounted(() => {
  fetchSources()
  pollTimer = window.setInterval(() => fetchSources(true), 2000)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
  closeWs()
})
</script>

<template>
  <div class="live-monitor">
    <div class="monitor-layout">
      <div class="source-panel">
        <div class="panel-header">
          <span class="panel-title">监控点位</span>
          <el-button size="small" type="primary" :icon="Plus" @click="showAddDialog = true">
            添加
          </el-button>
        </div>

        <div class="source-list" v-loading="loading">
          <div
            v-for="s in sources"
            :key="s.source_id"
            class="source-item"
            :class="{ active: s.source_id === currentId }"
            @click="selectSource(s.source_id)"
          >
            <span class="status-dot" :class="s.status"></span>
            <div class="source-info">
              <div class="source-name">{{ s.name }}</div>
              <div class="source-meta">
                {{ statusText(s.status) }} · {{ s.fps }} fps
              </div>
            </div>
            <div class="source-actions" @click.stop>
              <el-button
                size="small"
                text
                :icon="s.status === 'running' ? VideoPause : VideoPlay"
                @click="toggleSource(s)"
              />
              <el-button size="small" text :icon="Delete" @click="removeSource(s)" />
            </div>
          </div>

          <el-empty
            v-if="!sources.length && !loading"
            description="暂无监控点位"
            :image-size="60"
          />
        </div>
      </div>

      <div class="video-panel">
        <div class="video-stage">
          <img
            v-if="currentId && isRunning"
            :key="streamKey"
            :src="mjpegUrl"
            class="video-stream"
            alt="实时监控画面"
            @error="handleStreamError"
          />
          <div v-else class="video-empty">
            <el-icon :size="48"><VideoCamera /></el-icon>
            <p v-if="!sources.length">请先添加监控点位</p>
            <p v-else-if="!currentId">请选择左侧监控点位</p>
            <p v-else-if="currentSource?.status === 'error'">
              连接失败：{{ currentSource.error || '请检查流地址' }}
            </p>
            <p v-else>该点位未启动，请点击播放按钮</p>
          </div>

          <div v-if="currentId && isRunning" class="video-hud">
            <span class="hud-item">{{ liveData?.fps ?? 0 }} FPS</span>
            <span class="hud-item fire">火焰 {{ liveData?.fire_count ?? 0 }}</span>
            <span class="hud-item smoke">烟雾 {{ liveData?.smoke_count ?? 0 }}</span>
          </div>
        </div>

        <div class="param-bar">
          <div class="param-item">
            <label>置信度</label>
            <el-slider
              v-model="params.confidence"
              :min="0.05" :max="0.9" :step="0.05"
              size="small" style="width: 140px"
            />
            <span class="param-value">{{ params.confidence.toFixed(2) }}</span>
          </div>
          <div class="param-item">
            <label>IOU</label>
            <el-slider
              v-model="params.iou_threshold"
              :min="0.05" :max="0.9" :step="0.05"
              size="small" style="width: 140px"
            />
            <span class="param-value">{{ params.iou_threshold.toFixed(2) }}</span>
          </div>
          <div class="param-item">
            <label>跳帧</label>
            <el-input-number
              v-model="params.frame_interval"
              :min="1" :max="30" size="small"
              controls-position="right" style="width: 100px"
            />
          </div>
          <el-button type="primary" size="small" @click="applyParams">应用</el-button>
        </div>
      </div>

      <div class="detect-panel">
        <div class="panel-header">
          <span class="panel-title">实时检测</span>
          <span class="ws-status" :class="{ on: !!liveData }">
            {{ liveData ? '已连接' : '未连接' }}
          </span>
        </div>

        <div class="stat-row">
          <div class="stat-box fire">
            <div class="stat-num">{{ liveData?.fire_count ?? 0 }}</div>
            <div class="stat-label">火焰</div>
          </div>
          <div class="stat-box smoke">
            <div class="stat-num">{{ liveData?.smoke_count ?? 0 }}</div>
            <div class="stat-label">烟雾</div>
          </div>
        </div>

        <div class="meta-list">
          <div class="meta-row">
            <span>推理耗时</span>
            <span>{{ liveData?.inference_time ?? 0 }} ms</span>
          </div>
          <div class="meta-row">
            <span>已处理帧数</span>
            <span>{{ liveData?.frame_count ?? 0 }}</span>
          </div>
          <div class="meta-row">
            <span>最近更新</span>
            <span class="mono">{{ (liveData?.timestamp || '--').slice(11, 19) }}</span>
          </div>
        </div>

        <div class="detect-list-title">检测目标</div>
        <div class="detect-list">
          <div
            v-for="(d, i) in (liveData?.detections || [])"
            :key="i"
            class="detect-item"
          >
            <span class="tag" :class="d.class_name">
              {{ d.class_name === 'fire' ? '火焰' : '烟雾' }}
            </span>
            <span class="conf">{{ (d.confidence * 100).toFixed(1) }}%</span>
            <span class="coord mono">
              {{ d.bbox[0] }},{{ d.bbox[1] }}
            </span>
          </div>
          <div v-if="!liveData?.detections?.length" class="detect-empty">
            当前画面未检测到目标
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="showAddDialog" title="添加监控点位" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="点位名称">
          <el-input v-model="form.name" placeholder="如：1号瞭望塔" />
        </el-form-item>
        <el-form-item label="流地址">
          <el-input
            v-model="form.url"
            placeholder="rtsp://admin:pwd@192.168.1.64:554/Streaming/Channels/101"
          />
        </el-form-item>
        <el-form-item label="数据类型">
          <el-select v-model="form.source_type" style="width: 100%">
            <el-option label="RTSP 摄像头" value="rtsp" />
            <el-option label="RTMP 推流" value="rtmp" />
            <el-option label="HTTP 流" value="http" />
            <el-option label="本地视频文件" value="file" />
          </el-select>
        </el-form-item>
        <el-form-item label="点位描述">
          <el-input v-model="form.location" placeholder="如：林场东侧北纬23.5°" />
        </el-form-item>
        <el-form-item label="置信度">
          <el-slider v-model="form.confidence" :min="0.05" :max="0.9" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="IOU 阈值">
          <el-slider v-model="form.iou_threshold" :min="0.05" :max="0.9" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="推理跳帧">
          <el-input-number v-model="form.frame_interval" :min="1" :max="30" />
          <span class="form-hint">每 N 帧推理一次，值越大越省算力</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addSource">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.live-monitor {
  height: 100%;
}

.monitor-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 140px);
  min-height: 520px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.source-panel {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.source-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.source-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.source-item:hover {
  background: #f5f7fa;
}

.source-item.active {
  background: #ecfdf5;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #c0c4cc;
}

.status-dot.running { background: #16a34a; }
.status-dot.connecting { background: #e6a23c; }
.status-dot.error { background: #f56c6c; }

.source-info {
  flex: 1;
  min-width: 0;
}

.source-name {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.source-actions {
  display: flex;
  gap: 0;
  flex-shrink: 0;
}

.video-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.video-stage {
  flex: 1;
  position: relative;
  background: #1a1a1a;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.video-stream {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.video-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #8a8a8a;
  font-size: 14px;
}

.video-hud {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 8px;
}

.hud-item {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
}

.hud-item.fire { background: rgba(239, 68, 68, 0.9); }
.hud-item.smoke { background: rgba(245, 158, 11, 0.9); }

.param-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  flex-wrap: wrap;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}

.param-value {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  color: #303133;
  min-width: 32px;
}

.detect-panel {
  width: 320px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ws-status {
  font-size: 12px;
  color: #909399;
}

.ws-status.on { color: #16a34a; }

.stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 16px;
}

.stat-box {
  border-radius: 8px;
  padding: 14px;
  text-align: center;
}

.stat-box.fire { background: #fef2f2; }
.stat-box.smoke { background: #fffbeb; }

.stat-num {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.1;
}

.stat-box.fire .stat-num { color: #dc2626; }
.stat-box.smoke .stat-num { color: #d97706; }

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.meta-list {
  padding: 0 16px 12px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #606266;
  padding: 6px 0;
  border-bottom: 1px dashed #f0f0f0;
}

.detect-list-title {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  border-top: 1px solid #ebeef5;
}

.detect-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 16px;
}

.detect-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fafafa;
  margin-bottom: 6px;
  font-size: 13px;
}

.tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #fff;
}

.tag.fire { background: #ef4444; }
.tag.smoke { background: #f59e0b; }

.conf {
  color: #16a34a;
  font-weight: 500;
}

.coord {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}

.detect-empty {
  text-align: center;
  color: #c0c4cc;
  font-size: 13px;
  padding: 24px 0;
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}

.form-hint {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}
</style>