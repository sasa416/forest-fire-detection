import axios from 'axios'
import type { 
  DetectionResult, 
  DetectionHistory, 
  ModelInfo, 
  Statistics, 
  SystemStatus,
  PaginationParams,
  PaginatedResponse
} from '@/types'

// 创建axios实例
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 可以在这里添加token等认证信息
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败'
    console.error('API错误:', message)
    return Promise.reject(error)
  }
)

// 检测相关API
export const detectionApi = {
  // 图像检测
  detectImage: (file: File, params: { confidence: number; iouThreshold: number }) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('confidence', params.confidence.toString())
    formData.append('iou_threshold', params.iouThreshold.toString())
    return api.post<any, DetectionResult>('/detect/image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // 视频检测
  detectVideo: (file: File, params: { confidence: number; iouThreshold: number; frameInterval: number }) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('confidence', params.confidence.toString())
    formData.append('iou_threshold', params.iouThreshold.toString())
    formData.append('frame_interval', params.frameInterval.toString())
    return api.post<any, Blob>('/detect/video', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob'
    })
  },

  // 获取检测历史
  getHistory: (params: PaginationParams) => {
    return api.get<any, PaginatedResponse<DetectionHistory>>('/history', { params })
  },

  // 获取检测详情
  getDetection: (detectionId: string) => {
    return api.get<any, DetectionResult>(`/history/${detectionId}`)
  }
}

// 模型相关API
export const modelApi = {
  // 获取模型列表
  getModels: () => {
    return api.get<any, ModelInfo[]>('/models')
  },

  // 加载模型
  loadModel: (modelName: string) => {
    return api.post<any, { message: string }>(`/models/load/${modelName}`)
  },

  // 获取当前模型
  getCurrentModel: () => {
    return api.get<any, ModelInfo>('/models/current')
  }
}

// 统计相关API
export const statisticsApi = {
  // 获取统计数据
  getStatistics: (days: number = 7) => {
    return api.get<any, Statistics>('/statistics', { params: { days } })
  }
}

// 系统相关API
export const systemApi = {
  // 健康检查
  healthCheck: () => {
    return api.get<any, { status: string; timestamp: string; modelLoaded: boolean }>('/health')
  },

  // 获取系统状态
  getStatus: () => {
    return api.get<any, SystemStatus>('/status')
  }
}

export default api