import axios from 'axios'
import { ElMessage } from 'element-plus'
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
    description: '侧重整体偏暗的照片，提亮暗部；Gamma 小于 1 时提亮，大于 1 时压暗。',
  },
  {
    value: 'clahe',
    label: 'CLAHE（逆光）',
    description: '侧重逆光下的人脸暗部与局部对比度，限制过度增强；无法恢复已过曝丢失的细节。',
  },
  {
    value: 'retinex',
    label: 'Retinex（光照不均）',
    description: '侧重阴影、侧光等明暗不均的照片，估计光照并平衡亮度。',
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
  backlight: '强逆光',
  infrared: '红外补光',
  overexposed: '局部过曝',
  uneven: '光照不均匀',
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
