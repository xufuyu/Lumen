/**
 * Smart date formatting + day-grouping utilities.
 *
 * All functions accept ISO strings (as returned by the API) or Date instances,
 * and internally normalize to local calendar days.
 *
 * Grouping keys are `YYYY-MM-DD` in local time so identical dates from
 * different timezones don't accidentally split groups.
 */

export type DateInput = string | Date | null | undefined

/** Parse an ISO string to Date, or null if the input is falsy/invalid. */
function toDate(input: DateInput): Date | null {
  if (!input) return null
  const d = input instanceof Date ? input : new Date(input)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Local calendar day key `YYYY-MM-DD` (not ISO — no timezone shift issues). */
export function dayKey(input: DateInput): string | null {
  const d = toDate(input)
  if (!d) return null
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Signed number of calendar days between input and today, in local time.
 *  0 = today, 1 = tomorrow, -1 = yesterday. */
export function dayOffset(input: DateInput): number | null {
  const d = toDate(input)
  if (!d) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(d)
  target.setHours(0, 0, 0, 0)
  const ms = target.getTime() - today.getTime()
  return Math.round(ms / (1000 * 60 * 60 * 24))
}

/**
 * Format a date as a human-friendly relative label.
 *
 * - offset 0 → 今天 / Today
 * - offset 1 → 明天 / Tomorrow
 * - offset 2 → 后天 / In 2 days
 * - offset -1 → 昨天 / Yesterday
 * - -6 ≤ offset ≤ -2 → 「上周三」 / "Last Wed"
 * - 3 ≤ offset ≤ 6 → 「周三」 / "Wed"
 * - offset > 6 or < -6 → 「3月15日」 / "Mar 15" (with year if cross-year)
 *
 * `locale` should be either `'zh-CN'` or `'en'`. Others fall back to en.
 */
export function formatSmartDate(input: DateInput, locale: string = 'zh-CN'): string {
  const d = toDate(input)
  if (!d) return ''
  const offset = dayOffset(d)
  if (offset === null) return ''
  const isZh = locale.startsWith('zh')

  if (offset === 0) return isZh ? '今天' : 'Today'
  if (offset === 1) return isZh ? '明天' : 'Tomorrow'
  if (offset === 2) return isZh ? '后天' : 'In 2 days'
  if (offset === -1) return isZh ? '昨天' : 'Yesterday'

  const weekdaysZh = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const weekdaysEn = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const dow = d.getDay()

  if (offset >= 3 && offset <= 6) {
    return isZh ? weekdaysZh[dow] : weekdaysEn[dow]
  }
  if (offset >= -6 && offset <= -2) {
    return isZh ? `上${weekdaysZh[dow]}` : `Last ${weekdaysEn[dow]}`
  }

  const now = new Date()
  const sameYear = d.getFullYear() === now.getFullYear()
  if (isZh) {
    return sameYear
      ? `${d.getMonth() + 1}月${d.getDate()}日`
      : `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
  }
  return d.toLocaleDateString('en-US', sameYear
    ? { month: 'short', day: 'numeric' }
    : { year: 'numeric', month: 'short', day: 'numeric' },
  )
}

/** Same as formatSmartDate but includes the time portion for known days.
 *  e.g. `今天 14:30`, `明天 09:00`, `3月15日 10:00`. */
export function formatSmartDateTime(input: DateInput, locale: string = 'zh-CN'): string {
  const d = toDate(input)
  if (!d) return ''
  const dateStr = formatSmartDate(d, locale)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${dateStr} ${hh}:${mm}`
}

/** Compact relative time — "刚刚 / 3分钟前 / 2小时前 / 3天前".
 *  For times more than 30 days back, falls back to a formatted date. */
export function formatRelative(input: DateInput, locale: string = 'zh-CN'): string {
  const d = toDate(input)
  if (!d) return ''
  const isZh = locale.startsWith('zh')
  const diffMs = Date.now() - d.getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return isZh ? '刚刚' : 'just now'
  if (mins < 60) return isZh ? `${mins}分钟前` : `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return isZh ? `${hours}小时前` : `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days <= 30) return isZh ? `${days}天前` : `${days}d ago`
  return formatSmartDate(d, locale)
}

/**
 * Group an iterable of items into a Map keyed by local calendar day.
 * Items whose key function returns a falsy date are collected under `null`.
 *
 * The Map preserves insertion order — pass items already sorted the way you
 * want them displayed.
 */
export function groupByDay<T>(
  items: T[],
  keyFn: (item: T) => DateInput,
): Map<string | null, T[]> {
  const out = new Map<string | null, T[]>()
  for (const item of items) {
    const k = dayKey(keyFn(item))
    const bucket = out.get(k)
    if (bucket) bucket.push(item)
    else out.set(k, [item])
  }
  return out
}
