// 检测结果类型
export interface DetectionResult {
  detectionId: string
  imageUrl?: string
  imagePath?: string
  detections: Detection[]
  fireCount: number
  smokeCount: number
  inferenceTime: number
  imageWidth: number
  imageHeight: number
  timestamp: string
  modelName: string
  confidenceThreshold: number
  iouThreshold: number
}

// 检测项类型
export interface Detection {
  classId: number
  className: string
  confidence: number
  bbox: BoundingBox
}

// 边界框类型
export interface BoundingBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

// 检测历史类型
export interface DetectionHistory {
  detectionId: string
  imagePath: string
  fireCount: number
  smokeCount: number
  totalDetections: number
  inferenceTime: number
  timestamp: string
  modelName: string
  hasAlert: boolean
  alertLevel?: string
}

// 模型信息类型
export interface ModelInfo {
  name: string
  version: string
  path: string
  size: string
  description: string
  isLoaded: boolean
  loadTime?: string
}

// 告警信息类型
export interface Alert {
  alertId: string
  detectionId: string
  level: 'low' | 'medium' | 'high' | 'critical'
  message: string
  fireCount: number
  smokeCount: number
  timestamp: string
  isRead: boolean
}

// 统计信息类型
export interface Statistics {
  totalDetections: number
  totalFire: number
  totalSmoke: number
  avgInferenceTime: number
  alertCount: number
  detectionByDay: Record<string, number>
  detectionByHour: Record<string, number>
}

// 系统状态类型
export interface SystemStatus {
  status: string
  uptime: number
  modelLoaded: boolean
  currentModel?: string
  gpuAvailable: boolean
  gpuMemoryUsed?: number
  gpuMemoryTotal?: number
  cpuUsage: number
  memoryUsage: number
  diskUsage: number
}

// 检测参数类型
export interface DetectionParams {
  confidence: number
  iouThreshold: number
  frameInterval?: number
}

// API响应类型
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

// 分页参数类型
export interface PaginationParams {
  page: number
  pageSize: number
  startDate?: string
  endDate?: string
}

// 分页响应类型
export interface PaginatedResponse<T> {
  list: T[]
  total: number
  page: number
  pageSize: number
}