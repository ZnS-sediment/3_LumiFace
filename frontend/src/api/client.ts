import axios from 'axios'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'
export const api = axios.create({ baseURL: '/api', timeout: 180000 })
api.interceptors.response.use(r => r, error => {
  const message = error.response?.data?.message || (error.code === 'ECONNABORTED' ? '处理超时，请检查后端任务状态' : '无法连接后端，请确认服务已启动')
  ElMessage.error(message)
  return Promise.reject(error)
})
export async function get<T = any>(path: string): Promise<T> { return (await api.get(path)).data.data }
export async function post<T = any>(path: string, data?: unknown): Promise<T> { return (await api.post(path, data)).data.data }
export const methods = [{value:'original',label:'不增强'}, {value:'adaptive',label:'自适应增强'}, {value:'gamma',label:'Gamma 校正'}, {value:'clahe',label:'CLAHE'}, {value:'retinex',label:'Retinex'}, {value:'exposure',label:'曝光补偿'}, {value:'normalize',label:'光照归一化'}]
export const scenes: Record<string,string> = {normal:'正常光照',low_light:'低照度',backlight:'强逆光',infrared:'红外补光',overexposed:'局部过曝',uneven:'光照不均匀'}
export function methodLabel(value: string) { return methods.find(x => x.value === value)?.label || value }
export function percent(value: number | null | undefined) { return value == null ? '未评估' : `${(value * 100).toFixed(1)}%` }
export function number(value: number | null | undefined, digits = 1) { return value == null ? '—' : value.toFixed(digits) }
export function imageForm(file: File, options: unknown) { const data = new FormData(); data.append('file',file); data.append('options', JSON.stringify(options)); return data }
export function useTask() {
  const busy = ref(false)
  async function run<T>(fn: () => Promise<T>) { if (busy.value) return; busy.value = true; try { return await fn() } finally { busy.value = false } }
  async function safe(fn: () => Promise<unknown>) { try { await run(fn) } catch { /* interceptor displays the precise API error */ } }
  return {busy, run: safe}
}
