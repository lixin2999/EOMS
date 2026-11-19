import dayjs from 'dayjs'

export function money(value, withSymbol = false) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return '-'
  const text = num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return withSymbol ? `¥${text}` : text
}

export function moneyShort(value) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return '-'
  if (Math.abs(num) >= 100000000) return `${(num / 100000000).toFixed(2)} 亿`
  if (Math.abs(num) >= 10000) return `${(num / 10000).toFixed(2)} 万`
  return num.toFixed(2)
}

export function percent(value, digits = 2) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return '-'
  return `${(num * 100).toFixed(digits)}%`
}

export function rawPercent(value, digits = 2) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return '-'
  return `${num.toFixed(digits)}%`
}

export function date(value) {
  if (!value) return '-'
  const d = dayjs(value)
  return d.isValid() ? d.format('YYYY-MM-DD') : String(value)
}

export function datetime(value) {
  if (!value) return '-'
  const d = dayjs(value)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : String(value)
}

export function fromNow(value) {
  if (!value) return '-'
  const d = dayjs(value)
  if (!d.isValid()) return '-'
  const diff = dayjs().diff(d, 'minute')
  if (diff < 1) return '刚刚'
  if (diff < 60) return `${diff} 分钟前`
  if (diff < 60 * 24) return `${Math.floor(diff / 60)} 小时前`
  if (diff < 60 * 24 * 30) return `${Math.floor(diff / 60 / 24)} 天前`
  return d.format('YYYY-MM-DD')
}

export function today() {
  return dayjs().format('YYYY-MM-DD')
}

export function monthStart() {
  return dayjs().startOf('year').format('YYYY-MM')
}

export function currentMonth() {
  return dayjs().format('YYYY-MM')
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export function progressStatus(percentValue) {
  const num = Number(percentValue || 0)
  if (num >= 100) return 'success'
  if (num < 30) return 'exception'
  return undefined
}

export function maskPhone(phone) {
  if (!phone) return '已脱敏'
  return phone
}
