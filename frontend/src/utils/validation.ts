import { ElMessage } from 'element-plus/es/components/message/index'

export function validateRequired(fields: [label: string, filled: unknown][]): boolean {
  const missing = fields.filter(([, filled]) => !filled).map(([label]) => label)
  if (!missing.length) return true
  ElMessage.closeAll('error')
  ElMessage.error({
    message: `请补全必填项：${missing.join('、')}。`,
    grouping: true,
    showClose: true,
    duration: 5000,
  })
  return false
}
