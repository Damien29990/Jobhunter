// ProfileSwitcher.jsx — candidate dropdown with per-person edit and add at the end.

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Pencil, User, UserPlus } from 'lucide-react'
import { api } from '../lib/api'

export default function ProfileSwitcher({ value, onChange, onEditPerson, onNewPerson, tick }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(true)
  const ref = useRef(null)

  const load = useCallback(() => {
    api.candidates()
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load, tick])

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

  function selectPerson(id) {
    onChange(id)
    setOpen(false)
  }

  function editPerson(e, id) {
    e.stopPropagation()
    onChange(id)
    onEditPerson?.(id)
    setOpen(false)
  }

  function addPerson() {
    onNewPerson?.()
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => { setOpen((v) => !v); if (!open) load() }}
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
            <div
              key={c.id}
              className={`flex items-stretch border-b border-ink-700 ${
                c.id === value ? 'bg-ink-700' : ''
              }`}
            >
              <button
                type="button"
                onClick={() => selectPerson(c.id)}
                className="flex-1 min-w-0 text-left px-3 py-2 hover:bg-ink-700"
              >
                <div className="flex items-center gap-2">
                  <span className="font-pixel text-[12px] text-slate-100 truncate">{c.name}</span>
                  {c.is_default && (
                    <span className="font-mono text-[10px] text-amber-retro shrink-0">{t('candidate.default')}</span>
                  )}
                </div>
                <div className="font-mono text-[11px] text-slate-500 truncate mt-0.5">
                  {c.target_roles?.[0] || c.id}
                </div>
              </button>
              <button
                type="button"
                onClick={(e) => editPerson(e, c.id)}
                title={t('profile.edit')}
                className="shrink-0 px-2.5 text-slate-400 hover:text-cyan-retro"
              >
                <Pencil size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addPerson}
            className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-ink-700 text-slate-300"
          >
            <UserPlus size={16} />
            <span className="font-mono text-[12px]">{t('profile.newPerson')}</span>
          </button>
        </div>
      )}
    </div>
  )
}
