import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { 
  DetectionResult, 
  DetectionHistory, 
  ModelInfo, 
  Statistics, 
  SystemStatus,
  Alert
} from '@/types'
import { detectionApi, modelApi, statisticsApi, systemApi } from '@/api'

// 检测状态管理
export const useDetectionStore = defineStore('detection', () => {
  const currentResult = ref<DetectionResult | null>(null)
  const history = ref<DetectionHistory[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 图像检测
  const detectImage = async (file: File, params: { confidence: number; iouThreshold: number }) => {
    loading.value = true
    error.value = null
    try {
      const result = await detectionApi.detectImage(file, params)
      currentResult.value = result
      return result
    } catch (err: any) {
      error.value = err.message || '检测失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  // 获取检测历史
  const fetchHistory = async (params: { page: number; pageSize: number; startDate?: string; endDate?: string }) => {
    loading.value = true
    try {
      const response = await detectionApi.getHistory(params)
      history.value = response.list
      return response
    } catch (err: any) {
      error.value = err.message || '获取历史失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  // 清除当前结果
  const clearResult = () => {
    currentResult.value = null
  }

  return {
    currentResult,
    history,
    loading,
    error,
    detectImage,
    fetchHistory,
    clearResult
  }
})

// 模型状态管理
export const useModelStore = defineStore('model', () => {
  const models = ref<ModelInfo[]>([])
  const currentModel = ref<ModelInfo | null>(null)
  const loading = ref(false)

  // 获取模型列表
  const fetchModels = async () => {
    loading.value = true
    try {
      const result = await modelApi.getModels()
      models.value = result
      return result
    } catch (err: any) {
      console.error('获取模型列表失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 加载模型
  const loadModel = async (modelName: string) => {
    loading.value = true
    try {
      await modelApi.loadModel(modelName)
      // 重新获取模型列表
      await fetchModels()
      // 更新当前模型
      const model = models.value.find(m => m.name === modelName)
      if (model) {
        currentModel.value = model
      }
    } catch (err: any) {
      console.error('加载模型失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 获取当前模型
  const fetchCurrentModel = async () => {
    try {
      const result = await modelApi.getCurrentModel()
      currentModel.value = result
      return result
    } catch (err: any) {
      console.error('获取当前模型失败:', err)
      throw err
    }
  }

  return {
    models,
    currentModel,
    loading,
    fetchModels,
    loadModel,
    fetchCurrentModel
  }
})

// 统计状态管理
export const useStatisticsStore = defineStore('statistics', () => {
  const statistics = ref<Statistics | null>(null)
  const loading = ref(false)

  // 获取统计数据
  const fetchStatistics = async (days: number = 7) => {
    loading.value = true
    try {
      const result = await statisticsApi.getStatistics(days)
      statistics.value = result
      return result
    } catch (err: any) {
      console.error('获取统计数据失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    statistics,
    loading,
    fetchStatistics
  }
})

// 系统状态管理
export const useSystemStore = defineStore('system', () => {
  const status = ref<SystemStatus | null>(null)
  const loading = ref(false)

  // 获取系统状态
  const fetchStatus = async () => {
    loading.value = true
    try {
      const result = await systemApi.getStatus()
      status.value = result
      return result
    } catch (err: any) {
      console.error('获取系统状态失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 健康检查
  const healthCheck = async () => {
    try {
      const result = await systemApi.healthCheck()
      return result
    } catch (err: any) {
      console.error('健康检查失败:', err)
      throw err
    }
  }

  return {
    status,
    loading,
    fetchStatus,
    healthCheck
  }
})

// 告警状态管理
export const useAlertStore = defineStore('alert', () => {
  const alerts = ref<Alert[]>([])
  const unreadCount = computed(() => alerts.value.filter(a => !a.isRead).length)

  // 模拟告警数据
  const mockAlerts: Alert[] = [
    {
      alertId: 'alert_001',
      detectionId: 'det_001',
      level: 'critical',
      message: '监控点A发现明火，火势较大',
      fireCount: 3,
      smokeCount: 5,
      timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
      isRead: false
    },
    {
      alertId: 'alert_002',
      detectionId: 'det_002',
      level: 'high',
      message: '监控点B烟雾浓度超标',
      fireCount: 0,
      smokeCount: 8,
      timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      isRead: false
    },
    {
      alertId: 'alert_003',
      detectionId: 'det_003',
      level: 'medium',
      message: '航拍图C疑似火点，需人工确认',
      fireCount: 1,
      smokeCount: 2,
      timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      isRead: true
    }
  ]

  // 初始化告警
  const initAlerts = () => {
    alerts.value = mockAlerts
  }

  // 标记已读
  const markAsRead = (alertId: string) => {
    const alert = alerts.value.find(a => a.alertId === alertId)
    if (alert) {
      alert.isRead = true
    }
  }

  // 全部标记已读
  const markAllAsRead = () => {
    alerts.value.forEach(alert => {
      alert.isRead = true
    })
  }

  return {
    alerts,
    unreadCount,
    initAlerts,
    markAsRead,
    markAllAsRead
  }
})