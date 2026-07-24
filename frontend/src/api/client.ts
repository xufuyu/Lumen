const BASE = '/api'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}
// ── Records ──

export interface RecordOut {
  id: number
  content: string
  type: string
  status: string
  created_at: string
  updated_at: string
  linked_event_ids: number[]
  linked_task_ids: number[]
}

export interface RecordList {
  items: RecordOut[]
  total: number
  page: number
  page_size: number
}

export function createRecord(content: string, type = 'text', voiceEmotion?: string) {
  const body: Record<string, unknown> = { content, type }
  if (voiceEmotion) body.voice_emotion = voiceEmotion
  return request<RecordOut>('/records', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listRecords(params?: { page?: number; page_size?: number; status?: string }) {
  const qs = new URLSearchParams()
  if (params?.page) qs.set('page', String(params.page))
  if (params?.page_size) qs.set('page_size', String(params.page_size))
  if (params?.status) qs.set('status', params.status)
  return request<RecordList>(`/records?${qs}`)
}

export function updateRecord(id: number, data: { content?: string; status?: string }) {
  return request<RecordOut>(`/records/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteRecord(id: number) {
  return request<void>(`/records/${id}`, { method: 'DELETE' })
}

// 隐式润色：ASR 结束后调用，赢过用户手动编辑就自动替换
export interface PolishResponse {
  polished: string
  changed: boolean
}
export function polishAsrText(text: string, signal?: AbortSignal) {
  return request<PolishResponse>('/records/polish', {
    method: 'POST',
    body: JSON.stringify({ text }),
    signal,
  })
}

// ── Timeline / Events ──

export interface EventOut {
  id: number
  title: string
  description: string | null
  start_time: string | null
  end_time: string | null
  confidence: number
  status: string
  created_at: string
  source_record_ids: number[]
}

export interface EventList {
  items: EventOut[]
  total: number
}

export function listEvents(params?: { from?: string; to?: string; status?: string; limit?: number }) {
  const qs = new URLSearchParams()
  if (params?.from) qs.set('from', params.from)
  if (params?.to) qs.set('to', params.to)
  if (params?.status) qs.set('status', params.status)
  if (params?.limit) qs.set('limit', String(params.limit))
  return request<EventList>(`/timeline?${qs}`)
}

export function updateEvent(id: number, data: Record<string, unknown>) {
  return request<EventOut>(`/timeline/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteEvent(id: number) {
  return request<void>(`/timeline/${id}`, { method: 'DELETE' })
}

// ── Tasks ──

export interface TaskOut {
  id: number
  title: string
  description: string | null
  status: string
  priority: string
  due_date: string | null
  confidence: number
  created_at: string
  completed_at: string | null
  source_record_ids: number[]
}

export interface TaskList {
  items: TaskOut[]
  total: number
}

export function listTasks(params?: { status?: string; sort?: string }) {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.sort) qs.set('sort', params.sort)
  return request<TaskList>(`/tasks?${qs}`)
}

export function createTask(data: { title: string; description?: string; priority?: string; due_date?: string }) {
  return request<TaskOut>('/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateTask(id: number, data: Record<string, unknown>) {
  return request<TaskOut>(`/tasks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteTask(id: number) {
  return request<void>(`/tasks/${id}`, { method: 'DELETE' })
}

// ── Context ──

export interface ContextOut {
  id: number
  summary: string
  valid_from: string
  valid_until: string | null
  created_at: string
  source_record_ids: number[]
}

export function getCurrentContext() {
  return request<ContextOut>('/context/current')
}

// ── Query ──

export interface QuerySource {
  record_id: number
  excerpt: string
  created_at: string
}

export interface QueryResponse {
  answer: string
  sources: QuerySource[]
  disclaimer: string | null
}

export function askQuestion(question: string) {
  return request<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

// ── Process ──

export interface ProcessResponse {
  processed: number
  events_created: number
  events_updated: number
  tasks_created: number
  tasks_updated: number
  context_updated: boolean
  merge_candidates: MergeCandidate[]
}

export interface MergeCandidate {
  new_task_id: number
  new_title: string
  existing_title: string
  score: number
  record_id: number | null
}

export function triggerProcess() {
  return request<ProcessResponse>('/process', { method: 'POST' })
}

// ── Merge ──

export function resolveMerge(newTaskId: number, action: 'merge' | 'keep_separate') {
  return request<{ status: string; message: string }>('/merge/resolve', {
    method: 'POST',
    body: JSON.stringify({ new_task_id: newTaskId, action }),
  })
}

// ── Mood ──

export interface MoodOut {
  id: number
  score: number
  label: string
  summary: string
  key_factors: string[]
  created_at: string
}

export interface MoodGenerateResponse {
  mood: MoodOut | null
  message: string
}

export function generateMood() {
  return request<MoodGenerateResponse>('/mood/generate', { method: 'POST' })
}

export function getLatestMood() {
  return request<MoodGenerateResponse>('/mood/latest')
}
