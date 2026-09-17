// ProfileSwitcher.jsx — candidate profile dropdown. Forward-compatible with config/profiles/.

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, User } from 'lucide-react'
import { api } from '../lib/api'

export default function ProfileSwitcher({ value, onChange }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(true)
  const ref = useRef(null)

  useEffect(() => {
    api.candidates()
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!candidates.length) return
    if (!value || !candidates.some((c) => c.id === value)) {
      onChange(candidates.find((c) => c.is_default)?.id || candidates[0].id)
    }
  }, [candidates, value, onChange])

  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const current = candidates.find((c) => c.id === value) || candidates[0]

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="panel flex items-center gap-2 px-3 py-2"
      >
        <User size={16} className="text-cyan-retro" />
        <div className="text-left">
          <div className="font-mono text-[11px] text-slate-500 leading-none">{t('candidate.label')}</div>
          <div className="font-pixel text-[12px] text-cyan-retro leading-tight">
            {loading ? '…' : current?.name || '—'}
          </div>
        </div>
        <ChevronDown size={16} className="text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-72 panel z-50 overflow-hidden">
          {candidates.length === 0 && (
            <div className="px-3 py-3 font-mono text-[12px] text-slate-500">
              {t('candidate.none')}
            </div>
          )}
          {candidates.map((c) => (
            <button
              key={c.id}
              onClick={() => { onChange(c.id); setOpen(false) }}
              className={`w-full text-left px-3 py-2 hover:bg-ink-700 border-b border-ink-700 last:border-b-0 ${
                c.id === value ? 'bg-ink-700' : ''
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-pixel text-[12px] text-slate-100">{c.name}</span>
                {c.is_default && (
                  <span className="font-mono text-[10px] text-amber-retro">{t('candidate.default')}</span>
                )}
              </div>
              <div className="font-mono text-[11px] text-slate-500 truncate mt-0.5">
                {c.target_roles?.[0] || c.id}
              </div>
            </button>
          ))}
          <div className="px-3 py-2 bg-ink-900 font-mono text-[10px] text-slate-600">
            {t('candidate.addHint')}
          </div>
        </div>
      )}
    </div>
  )
}
