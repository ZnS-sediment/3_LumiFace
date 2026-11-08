import axios from 'axios'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ref } from 'vue'
export const api = axios.create({ baseURL: '/api', timeout: 180000 })
api.interceptors.response.use(
  (r) => r,
  (error) => {
    const message =
      error.response?.data?.message ||
      (error.code === 'ECONNABORTED'
        ? '处理超时，请检查后端任务状态'
        : '无法连接后端，请确认服务已启动')
    ElMessage.error(message)
    return Promise.reject(error)
  },
)
export async function get<T = any>(path: string): Promise<T> {
  return (await api.get(path)).data.data
}
export async function post<T = any>(path: string, data?: unknown): Promise<T> {
  return (await api.post(path, data)).data.data
}
export const methods = [
  {
    value: 'gamma',
    label: 'Gamma 校正（低照度）',
    description: '根据图片亮度自动计算 Gamma，侧重提亮低照度照片。',
  },
  {
    value: 'clahe',
    label: 'CLAHE（逆光）',
    description: '根据明暗差与噪声自动调整对比度限制，侧重逆光暗部；无法恢复过曝细节。',
  },
  {
    value: 'retinex',
    label: 'Retinex（光照不均）',
    description: '根据图片尺寸和光照不均程度自动调整平滑尺度、处理强度，平衡阴影与侧光。',
  },
]
export const experimentMethods = [{ value: 'original', label: '不增强（对照组）' }, ...methods]
const historicalMethodLabels: Record<string, string> = {
  adaptive: '自适应增强（历史方案）',
  exposure: '曝光补偿（历史方案）',
  normalize: '光照归一化（历史方案）',
}
export const scenes: Record<string, string> = {
  normal: '正常光照',
  low_light: '低照度',
  backlight: '逆光',
  uneven: '光照不均',
}
export function sceneLabel(value: string) {
  const historical: Record<string, string> = {
    infrared: '红外补光（历史数据）',
    overexposed: '局部过曝（历史数据）',
  }
  return scenes[value] || historical[value] || value
}
export function methodLabel(value: string) {
  return (
    experimentMethods.find((x) => x.value === value)?.label ||
    historicalMethodLabels[value] ||
    value
  )
}
export function percent(value: number | null | undefined) {
  return value == null ? '未评估' : `${(value * 100).toFixed(1)}%`
}
export function number(value: number | null | undefined, digits = 1) {
  return value == null ? '—' : value.toFixed(digits)
}
export function imageForm(file: File, options: unknown) {
  const data = new FormData()
  data.append('file', file)
  data.append('options', JSON.stringify(options))
  return data
}
export function useTask() {
  const busy = ref(false)
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    if (busy.value) return
    busy.value = true
    try {
      return await fn()
    } catch {
      /* The API interceptor displays request errors. */
    } finally {
      busy.value = false
    }
  }
  return { busy, run }
}
