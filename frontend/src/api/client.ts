import { getUserId } from '../user'

const BASE = '/api'

class AbortError extends Error {
  constructor() { super('Request aborted'); this.name = 'AbortError' }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const signal = options?.signal
  // 提前短路：signal 已 abort 时不发请求
  if (signal?.aborted) throw new AbortError()
  const uid = getUserId()
  try {
    const res = await fetch(`${BASE}${url}`, {
      headers: { 'Content-Type': 'application/json', 'X-User-ID': uid, ...options?.headers },
      ...options,
    })
    if (!res.ok) {
      let err: string
      try { const j = await res.json(); err = j.detail || JSON.stringify(j) } catch { err = await res.text() }
      if (res.status === 429) {
        throw new Error(err || '请求过于频繁，请稍后再试。\nThis is a competition demo, rate limited.')
      }
      throw new Error(err || `HTTP ${res.status}`)
    }
    if (res.status === 204) return undefined as T
    return res.json()
  } catch (e: unknown) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new AbortError()
    }
    throw e
  }
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
  is_question: boolean
}

export function askQuestion(question: string) {
  return request<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

// 快速意图分类：判断是否为询问（<500ms）
export function classifyIntent(text: string) {
  return request<{ is_question: boolean }>('/query/classify', {
    method: 'POST',
    body: JSON.stringify({ question: text }),
  })
}

// 流式问答
export interface StreamChunk { type: 'chunk'; content: string }
export interface StreamDone { type: 'done'; is_question: boolean; answer: string; sources: QuerySource[]; disclaimer: string | null }
export interface StreamError { type: 'error'; message: string }
export type StreamEvent = StreamChunk | StreamDone | StreamError

export async function askQuestionStream(
  question: string,
  onChunk: (content: string) => void,
  onDone: (data: StreamDone) => void,
  onError?: (err: string) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) {
    onError?.(`HTTP ${res.status}`)
    return
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (!data) continue
      try {
        const evt: StreamEvent = JSON.parse(data)
        if (evt.type === 'chunk') onChunk(evt.content)
        else if (evt.type === 'done') onDone(evt)
        else if (evt.type === 'error') onError?.(evt.message)
      } catch { /* skip malformed */ }
    }
  }
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
  auto_completed_tasks: { task_id: number; title: string; old_status: string }[]
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

// ── User merge ──

export async function mergeUserData(newUserId: string): Promise<{ merged: number; message: string }> {
  return request('/user/merge', {
    method: 'POST',
    body: JSON.stringify({ new_user_id: newUserId }),
  })
}
