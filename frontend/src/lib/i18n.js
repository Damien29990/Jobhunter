// i18n setup — Traditional Chinese (zh-HK) + English (en).
// Default = browser language if it starts with 'zh', else 'en'. Persisted in localStorage.

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import zhHK from './locales/zh-HK.json'

const STORAGE_KEY = 'jobhunter.lang'

export const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'zh-HK', label: '繁體中文' },
]

function detectInitial() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && LANGS.some((l) => l.code === saved)) return saved
  const nav = (navigator.language || 'en').toLowerCase()
  return nav.startsWith('zh') ? 'zh-HK' : 'en'
}

const initial = detectInitial()

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    'zh-HK': { translation: zhHK },
  },
  lng: initial,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnNull: false,
})

export function changeLang(code) {
  i18n.changeLanguage(code)
  localStorage.setItem(STORAGE_KEY, code)
  document.documentElement.lang = code === 'zh-HK' ? 'zh-HK' : 'en'
}

export function currentLang() {
  return i18n.language || initial
}

export default i18n
