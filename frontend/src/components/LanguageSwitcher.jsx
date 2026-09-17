// LanguageSwitcher.jsx — toggle between English and 繁體中文 (zh-HK).

import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import { LANGS, changeLang, currentLang } from '../lib/i18n'

export default function LanguageSwitcher() {
  const { t } = useTranslation()
  const cur = currentLang()
  return (
    <div className="panel flex items-center gap-1 px-2 py-2" title={t('lang.switch')}>
      <Globe size={16} className="text-amber-retro" />
      <div className="flex gap-0.5">
        {LANGS.map((l) => (
          <button
            key={l.code}
            onClick={() => changeLang(l.code)}
            className={`font-mono text-[11px] px-1.5 py-0.5 border transition-colors ${
              cur === l.code
                ? 'border-amber-retro text-amber-retro bg-ink-700'
                : 'border-ink-600 text-slate-500 hover:text-slate-300'
            }`}
          >
            {l.code === 'en' ? 'EN' : '繁'}
          </button>
        ))}
      </div>
    </div>
  )
}
