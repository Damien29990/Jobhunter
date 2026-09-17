// Company research drawer — full Dana dossier without requiring a job click.

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, LoaderCircle, ShieldCheck } from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'
import DossierBody from './DossierBody'

export default function CompanyDrawer({ companyName, onClose, onSelectJob }) {
  const { t } = useTranslation()
  const [dossier, setDossier] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    setDossier(null)
    api.dossier(companyName)
      .then((d) => { if (active) setDossier(d) })
      .catch(() => { if (active) setDossier(null) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [companyName])

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside className="relative w-full max-w-xl panel border-l-4 border-emerald-retro h-full flex flex-col">
        <div className="flex items-center justify-between p-3 border-b-2 border-ink-700">
          <h3 className="font-pixel text-[13px] text-emerald-retro flex items-center gap-1.5">
            <ShieldCheck size={16} /> {t('research.title')}
          </h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-rose-retro">
            <X size={20} />
          </button>
        </div>
        <div className="px-4 py-2 border-b-2 border-ink-700">
          <div className="font-mono text-[14px] text-slate-100 break-words">{companyName}</div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center gap-2 font-mono text-[13px] text-slate-500">
              <LoaderCircle size={16} className="animate-spin" /> {t('detail.loading')}
            </div>
          ) : (
            <DossierBody
              dossier={dossier}
              t={t}
              onSelectJob={(job) => {
                onClose()
                onSelectJob?.(job)
              }}
            />
          )}
        </div>
        {dossier?.updated_at && (
          <div className="p-2.5 border-t-2 border-ink-700 font-mono text-[11px] text-slate-600">
            {t('research.updated')} {formatHKDateTime(dossier.updated_at)} HKT
          </div>
        )}
      </aside>
    </div>
  )
}
