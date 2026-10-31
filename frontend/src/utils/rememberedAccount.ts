const key = 'teampilot.rememberedAccount'
const legacyKey = 'teampilot.rememberedLogin'

export function readRememberedAccount(storage: Storage): string {
  try {
    const legacy = storage.getItem(legacyKey)
    storage.removeItem(legacyKey)
    if (legacy) {
      const username = JSON.parse(legacy)?.username
      if (typeof username === 'string') storage.setItem(key, username)
    }
    return storage.getItem(key) || ''
  } catch {
    storage.removeItem(legacyKey)
    return ''
  }
}

export function saveRememberedAccount(storage: Storage, username: string, remember: boolean) {
  storage.removeItem(legacyKey)
  if (remember) storage.setItem(key, username)
  else storage.removeItem(key)
}
