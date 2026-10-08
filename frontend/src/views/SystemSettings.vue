<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

interface ConfigItem {
  key: string
  value: string
  description: string
  updated_at: string
}

const activeTab = ref('detection')
const loading = ref(false)
const saving = ref(false)

// 后端 system_configs 全量配置（key -> value）
const configs = ref<Record<string, string>>({})
// 修改前的快照，用于只提交有变化的项
const snapshot = ref<Record<string, string>>({})
// 可选的模型名列表（来自 /api/models）
const modelOptions = ref<string[]>([])

const detection = reactive({
  default_model: '',
  default_confidence: 0.3,
  default_iou: 0.45,
  default_image_size: 960,
  enable_gpu: true,
  max_concurrent: 1
})

const alert = reactive({
  alert_enabled: true,
  alert_fire_threshold: 1,
  alert_smoke_threshold: 1,
  alert_confidence_threshold: 0.75,
  alert_cooldown: 30,
  alert_channels: [] as string[]
})

const system = reactive({
  upload_dir: './uploads',
  model_dir: './models',
  log_level: 'INFO',
  data_retention_days: 90,
  auto_backup: false,
  backup_interval_hours: 24
})

const num = (v: string | undefined, d: number) => {
  const n = Number(v)
  return v === undefined || v === '' || Number.isNaN(n) ? d : n
}
const bool = (v: string | undefined, d: boolean) =>
  v === undefined || v === '' ? d : ['1', 'true', 'yes', 'on'].includes(v.toLowerCase())
const list = (v: string | undefined) => (v ? v.split(',').map(s => s.trim()).filter(Boolean) : [])

// 把后端配置灌进表单
const applyConfigs = (map: Record<string, string>) => {
  detection.default_model = map.default_model || ''
  detection.default_confidence = num(map.default_confidence, 0.3)
  detection.default_iou = num(map.default_iou, 0.45)
  detection.default_image_size = num(map.default_image_size, 960)
  detection.enable_gpu = bool(map.enable_gpu, true)
  detection.max_concurrent = num(map.max_concurrent, 1)

  alert.alert_enabled = bool(map.alert_enabled, true)
  alert.alert_fire_threshold = num(map.alert_fire_threshold, 1)
  alert.alert_smoke_threshold = num(map.alert_smoke_threshold, 1)
  alert.alert_confidence_threshold = num(map.alert_confidence_threshold, 0.75)
  alert.alert_cooldown = num(map.alert_cooldown, 30)
  alert.alert_channels = list(map.alert_channels)

  system.upload_dir = map.upload_dir || './uploads'
  system.model_dir = map.model_dir || './models'
  system.log_level = map.log_level || 'INFO'
  system.data_retention_days = num(map.data_retention_days, 90)
  system.auto_backup = bool(map.auto_backup, false)
  system.backup_interval_hours = num(map.backup_interval_hours, 24)
}

// 当前表单 -> 配置键值对
const currentValues = (): Record<string, string> => ({
  default_model: detection.default_model,
  default_confidence: String(detection.default_confidence),
  default_iou: String(detection.default_iou),
  default_image_size: String(detection.default_image_size),
  enable_gpu: String(detection.enable_gpu),
  max_concurrent: String(detection.max_concurrent),

  alert_enabled: String(alert.alert_enabled),
  alert_fire_threshold: String(alert.alert_fire_threshold),
  alert_smoke_threshold: String(alert.alert_smoke_threshold),
  alert_confidence_threshold: String(alert.alert_confidence_threshold),
  alert_cooldown: String(alert.alert_cooldown),
  alert_channels: alert.alert_channels.join(','),

  upload_dir: system.upload_dir,
  model_dir: system.model_dir,
  log_level: system.log_level,
  data_retention_days: String(system.data_retention_days),
  auto_backup: String(system.auto_backup),
  backup_interval_hours: String(system.backup_interval_hours)
})

const loadConfigs = async () => {
  loading.value = true
  try {
    const res = await fetch('/api/admin/configs')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const items: ConfigItem[] = await res.json()
    const map: Record<string, string> = {}
    items.forEach(it => { map[it.key] = it.value })
    configs.value = map
    snapshot.value = { ...map }
    applyConfigs(map)
  } catch (e: any) {
    ElMessage.error('读取系统配置失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

const loadModels = async () => {
  try {
    const res = await fetch('/api/models')
    if (!res.ok) return
    const list: any[] = await res.json()
    modelOptions.value = list.map(m => m.name)
  } catch {
    // 模型列表拉不到不影响配置编辑
  }
}

// 只提交发生变化的项
const saveTab = async (tab: string, keys: string[]) => {
  const values = currentValues()
  const changed = keys.filter(k => values[k] !== (snapshot.value[k] ?? ''))
  if (changed.length === 0) {
    ElMessage.info('没有需要保存的改动')
    return
  }
  saving.value = true
  try {
    const body = changed.map(k => ({ key: k, value: values[k], description: '' }))
    const res = await fetch('/api/admin/configs/batch', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    ElMessage.success(`${data.message}（${tab}）`)
    await loadConfigs()
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

const DETECTION_KEYS = ['default_model', 'default_confidence', 'default_iou',
  'default_image_size', 'enable_gpu', 'max_concurrent']
const ALERT_KEYS = ['alert_enabled', 'alert_fire_threshold', 'alert_smoke_threshold',
  'alert_confidence_threshold', 'alert_cooldown', 'alert_channels']
const SYSTEM_KEYS = ['upload_dir', 'model_dir', 'log_level',
  'data_retention_days', 'auto_backup', 'backup_interval_hours']

onMounted(() => {
  loadConfigs()
  loadModels()
})
</script>

<template>
  <div class="system-settings">
    <el-card shadow="hover" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span class="card-title">系统设置</span>
          <span class="card-hint">
            检测参数与告警规则保存后<b>立即生效</b>；标注「需重启」的项重启后端后生效
          </span>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- ── 检测参数 ── -->
        <el-tab-pane label="检测参数" name="detection">
          <div class="settings-form">
            <el-form label-width="160px">
              <el-form-item label="默认模型">
                <el-select v-model="detection.default_model" style="width:240px" filterable allow-create>
                  <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
                </el-select>
                <span class="form-hint">取自模型管理中的可用权重</span>
              </el-form-item>
              <el-form-item label="默认置信度">
                <el-slider v-model="detection.default_confidence" :min="0.05" :max="0.9" :step="0.05" show-input style="width:400px" />
              </el-form-item>
              <el-form-item label="默认 IOU 阈值">
                <el-slider v-model="detection.default_iou" :min="0.05" :max="0.9" :step="0.05" show-input style="width:400px" />
              </el-form-item>
              <el-form-item label="单尺度推理尺寸">
                <el-select v-model="detection.default_image_size" style="width:240px">
                  <el-option :value="640" label="640（火焰响应最强）" />
                  <el-option :value="960" label="960" />
                  <el-option :value="1280" label="1280" />
                  <el-option :value="1920" label="1920（高清）" />
                </el-select>
                <span class="form-hint">当前多尺度融合已启用，此项仅在关闭融合时生效</span>
              </el-form-item>
              <el-form-item label="GPU 加速">
                <el-switch v-model="detection.enable_gpu" />
                <el-tag type="warning" size="small" style="margin-left:12px">需重启</el-tag>
              </el-form-item>
              <el-form-item label="最大并发推理数">
                <el-input-number v-model="detection.max_concurrent" :min="1" :max="16" />
                <el-tag type="warning" size="small" style="margin-left:12px">需重启</el-tag>
                <span class="form-hint">8GB 显存建议保持 1，多进程会各加载一份模型</span>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="saving" @click="saveTab('检测参数', DETECTION_KEYS)">保存</el-button>
                <el-button @click="loadConfigs">重置</el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- ── 告警规则 ── -->
        <el-tab-pane label="告警规则" name="alert">
          <div class="settings-form">
            <el-form label-width="160px">
              <el-form-item label="启用告警">
                <el-switch v-model="alert.alert_enabled" />
              </el-form-item>
              <el-form-item label="火焰数量阈值">
                <el-input-number v-model="alert.alert_fire_threshold" :min="1" :max="50" />
                <span class="form-hint">达到或超过此数量触发告警</span>
              </el-form-item>
              <el-form-item label="烟雾数量阈值">
                <el-input-number v-model="alert.alert_smoke_threshold" :min="1" :max="50" />
                <span class="form-hint">达到或超过此数量触发告警</span>
              </el-form-item>
              <el-form-item label="告警置信度阈值">
                <el-slider v-model="alert.alert_confidence_threshold" :min="0.3" :max="0.95" :step="0.05" show-input style="width:400px" />
                <span class="form-hint">仅用于「无 fire/smoke 时的高置信兜底告警」</span>
              </el-form-item>
              <el-form-item label="告警冷却时间">
                <el-input-number v-model="alert.alert_cooldown" :min="5" :max="3600" :step="5" />
                <span class="form-hint">秒，同一路流两次告警的最小间隔</span>
              </el-form-item>
              <el-form-item label="通知渠道">
                <el-checkbox-group v-model="alert.alert_channels">
                  <el-checkbox label="email">邮件</el-checkbox>
                  <el-checkbox label="sms">短信</el-checkbox>
                  <el-checkbox label="dingtalk">钉钉</el-checkbox>
                  <el-checkbox label="wechat">微信</el-checkbox>
                </el-checkbox-group>
                <div class="form-hint block">
                  注意：渠道为登记项，站外真实发送通道尚未接入，目前告警只在站内（顶栏弹窗 + 告警中心）送达
                </div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="saving" @click="saveTab('告警规则', ALERT_KEYS)">保存</el-button>
                <el-button @click="loadConfigs">重置</el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- ── 系统配置 ── -->
        <el-tab-pane label="系统配置" name="system">
          <div class="settings-form">
            <el-form label-width="160px">
              <el-form-item label="上传目录">
                <el-input v-model="system.upload_dir" style="width:320px" />
                <el-tag type="warning" size="small" style="margin-left:12px">需重启</el-tag>
              </el-form-item>
              <el-form-item label="模型目录">
                <el-input v-model="system.model_dir" style="width:320px" />
                <el-tag type="warning" size="small" style="margin-left:12px">需重启</el-tag>
              </el-form-item>
              <el-form-item label="日志级别">
                <el-select v-model="system.log_level" style="width:240px">
                  <el-option label="DEBUG" value="DEBUG" />
                  <el-option label="INFO" value="INFO" />
                  <el-option label="WARNING" value="WARNING" />
                  <el-option label="ERROR" value="ERROR" />
                </el-select>
                <el-tag type="warning" size="small" style="margin-left:12px">需重启</el-tag>
              </el-form-item>
              <el-form-item label="数据保留天数">
                <el-input-number v-model="system.data_retention_days" :min="7" :max="365" />
                <span class="form-hint">检测记录超过此天数后由清理任务删除</span>
              </el-form-item>
              <el-form-item label="自动备份">
                <el-switch v-model="system.auto_backup" />
              </el-form-item>
              <el-form-item v-if="system.auto_backup" label="备份间隔">
                <el-input-number v-model="system.backup_interval_hours" :min="1" :max="168" />
                <span class="form-hint">小时</span>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="saving" @click="saveTab('系统配置', SYSTEM_KEYS)">保存</el-button>
                <el-button @click="loadConfigs">重置</el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.system-settings { height: 100%; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 16px; font-weight: 600; color: #303133; }
.card-hint { font-size: 12px; color: #909399; }
.card-hint b { color: #16a34a; }
.settings-form { max-width: 720px; padding-top: 16px; }
.form-hint { margin-left: 12px; font-size: 12px; color: #909399; }
.form-hint.block { margin-left: 0; margin-top: 6px; line-height: 1.6; }
</style>
