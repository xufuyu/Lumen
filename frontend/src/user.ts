const STORAGE_KEY = 'lumen-uid'

function generateId(): string {
  return crypto.randomUUID()
}

export function getUserId(): string {
  let uid = localStorage.getItem(STORAGE_KEY)
  if (!uid) {
    uid = generateId()
    localStorage.setItem(STORAGE_KEY, uid)
  }
  return uid
}

export function setUserId(uid: string) {
  localStorage.setItem(STORAGE_KEY, uid)
}

export function resetUserId() {
  localStorage.removeItem(STORAGE_KEY)
}
