<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Refresh, Switch, Delete, Download, Document } from '@element-plus/icons-vue'

interface ModelInfo {
  name: string
  version: string
  path: string
  size: string
  description: string
  is_loaded: boolean
  load_time: string | null
}

const models = ref<ModelInfo[]>([])
const loading = ref(false)
const switching = ref('')          // 正在切换的模型名
const currentModel = ref('')
const showUploadDialog = ref(false)
const uploading = ref(false)

const uploadForm = reactive({
  description: '',
  file: null as File | null,
  fileName: ''
})

// 模型列表来自后端 /api/models（真实扫描 models 目录）
const fetchModels = async () => {
  loading.value = true
  try {
    const res = await fetch('/api/models')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const list: ModelInfo[] = await res.json()
    models.value = list
    const cur = list.find(m => m.is_loaded)
    currentModel.value = cur ? cur.name : ''
  } catch (e: any) {
    ElMessage.error('读取模型列表失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

const fmtTime = (t: string | null) => {
  if (!t) return '--'
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return t
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 切换模型：调后端真实加载权重
const handleSwitchModel = async (model: ModelInfo) => {
  try {
    await ElMessageBox.confirm(
      `确认切换到模型「${model.name}」？加载需要数秒，期间检测接口会短暂不可用。`,
      '切换模型', { type: 'warning' }
    )
  } catch { return }

  switching.value = model.name
  try {
    const res = await fetch(`/api/models/load/${encodeURIComponent(model.name)}`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    ElMessage.success(data.message || `已切换到 ${model.name}`)
    await fetchModels()
  } catch (e: any) {
    ElMessage.error('切换失败: ' + (e.message || e))
  } finally {
    switching.value = ''
  }
}

// 删除模型文件（后端会拒绝删除默认模型/正在使用的模型）
const handleDeleteModel = async (model: ModelInfo) => {
  if (model.is_loaded) {
    ElMessage.warning('不能删除当前正在使用的模型，请先切换到其它模型')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除模型「${model.name}」？文件将从磁盘移除，不可恢复。`,
      '删除模型', { type: 'error', confirmButtonText: '确认删除' }
    )
  } catch { return }

  try {
    const res = await fetch(`/api/admin/models/${encodeURIComponent(model.name)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    ElMessage.success(data.message || '已删除')
    await fetchModels()
  } catch (e: any) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

// 下载权重文件
const handleDownload = (model: ModelInfo) => {
  window.open(`/api/admin/models/${encodeURIComponent(model.name)}/download`, '_blank')
}

const onFileChange = (f: any) => {
  uploadForm.file = f.raw
  uploadForm.fileName = f.name || f.raw?.name || ''
}

const handleUpload = async () => {
  if (!uploadForm.file) {
    ElMessage.warning('请选择模型文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', uploadForm.file)
    const res = await fetch('/api/admin/models/upload', { method: 'POST', body: fd })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    ElMessage.success(data.message || '上传成功')
    showUploadDialog.value = false
    uploadForm.description = ''
    uploadForm.file = null
    uploadForm.fileName = ''
    await fetchModels()
  } catch (e: any) {
    ElMessage.error('上传失败: ' + (e.message || e))
  } finally {
    uploading.value = false
  }
}

onMounted(() => { fetchModels() })
</script>

<template>
  <div class="model-manage">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">模型管理</span>
            <el-tag v-if="currentModel" type="success" size="small" effect="dark">
              当前: {{ currentModel }}
            </el-tag>
          </div>
          <div class="header-actions">
            <el-button type="primary" :icon="Upload" @click="showUploadDialog = true">上传模型</el-button>
            <el-button :icon="Refresh" @click="fetchModels">刷新</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="!loading && models.length === 0" description="models 目录下暂无模型文件" />

      <div class="model-grid" v-loading="loading">
        <div
          v-for="model in models"
          :key="model.name"
          class="model-card"
          :class="{ active: model.is_loaded }"
        >
          <div class="model-header">
            <div class="model-icon" :class="{ active: model.is_loaded }">
              <el-icon :size="24"><Document /></el-icon>
            </div>
            <div class="model-info">
              <div class="model-name">{{ model.name }}</div>
              <div class="model-version">版本 {{ model.version }} · {{ model.size }}</div>
            </div>
            <el-tag v-if="model.is_loaded" type="success" size="small" effect="dark">已加载</el-tag>
          </div>

          <div class="model-desc" :title="model.path">{{ model.description }}</div>

          <div class="model-metrics">
            <div class="metric">
              <span class="metric-value" style="color:#64748b;">{{ fmtTime(model.load_time) }}</span>
              <span class="metric-label">加载时间</span>
            </div>
          </div>

          <div class="model-actions">
            <el-button
              v-if="!model.is_loaded"
              type="primary"
              size="small"
              :icon="Switch"
              :loading="switching === model.name"
              @click="handleSwitchModel(model)"
            >
              切换使用
            </el-button>
            <el-button v-else type="success" size="small" disabled>当前使用中</el-button>

            <el-button size="small" :icon="Download" @click="handleDownload(model)">导出</el-button>
            <el-button
              size="small"
              type="danger"
              text
              :icon="Delete"
              :disabled="model.is_loaded"
              @click="handleDeleteModel(model)"
            />
          </div>
        </div>
      </div>
    </el-card>

    <el-dialog v-model="showUploadDialog" title="上传模型" width="480px">
      <el-form :model="uploadForm" label-width="80px">
        <el-form-item label="模型文件">
          <el-upload
            action="#"
            :auto-upload="false"
            :limit="1"
            accept=".pt,.onnx,.engine,.tflite"
            :on-change="onFileChange"
          >
            <el-button :icon="Upload">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">
                支持 .pt / .onnx / .engine / .tflite；文件名即模型名（同名会被拒绝）
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadForm.description" type="textarea" :rows="3"
                    placeholder="训练参数、数据集信息等（仅界面展示，不落库）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.model-manage { height: 100%; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 12px; }
.card-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }

.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }

.model-card {
  padding: 20px; border-radius: 12px;
  border: 1.5px solid #e5e7eb; background: #fff;
  transition: all 0.3s;
}
.model-card:hover { border-color: #a7f3d0; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.model-card.active { border-color: #16a34a; background: #f0fdf4; }

.model-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.model-icon {
  width: 48px; height: 48px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  background: #f3f4f6; color: #6b7280;
}
.model-icon.active { background: #dcfce7; color: #16a34a; }
.model-info { flex: 1; min-width: 0; }
.model-name { font-size: 15px; font-weight: 600; color: #303133; word-break: break-all; }
.model-version { font-size: 12px; color: #909399; margin-top: 2px; }

.model-desc {
  font-size: 13px; color: #606266; margin-bottom: 16px; line-height: 1.5;
  min-height: 38px; overflow: hidden; text-overflow: ellipsis;
}

.model-metrics { display: flex; gap: 20px; margin-bottom: 16px; }
.metric { display: flex; flex-direction: column; }
.metric-value { font-size: 14px; font-weight: 600; }
.metric-label { font-size: 11px; color: #909399; margin-top: 2px; }

.model-actions { display: flex; gap: 8px; }
</style>
