// JobShelfPanel.jsx — overlay listing jobs hidden from the main kanban.
// Low score (< 35), expired, and unconsiderable. Rows stay in SQLite for agents.

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive, Ban, Clock, TrendingDown, X } from 'lucide-react'
import JobCard from './JobCard'
import { api } from '../lib/api'

function Section({ icon: Icon, color, title, hint, jobs, stageKey, onSelect }) {
  const { t } = useTranslation()
  return (
    <section className="flex flex-col min-h-0 min-w-0 flex-1">
      <div className="flex items-center gap-2 px-1 pb-2 shrink-0">
        <Icon size={16} style={{ color }} aria-hidden />
        <h3 className="font-pixel text-[12px]" style={{ color }}>{title}</h3>
        <span className="font-mono text-[12px] text-slate-500">{jobs.length}</span>
      </div>
      <p className="font-mono text-[11px] text-slate-600 px-1 pb-2 leading-4">{hint}</p>
      <div className="flex-1 min-h-[180px] max-h-[min(42vh,320px)] overflow-y-auto space-y-2 pr-1 kanban-scroll">
        {jobs.length === 0 ? (
          <div className="font-mono text-[12px] text-slate-600 text-center py-8">{t('shelf.empty')}</div>
        ) : (
          jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              dossier={job.dossier}
              onClick={() => onSelect(job, stageKey)}
            />
          ))
        )}
      </div>
    </section>
  )
}

export default function JobShelfPanel({ open, onClose, onSelectJob, tick }) {
  const { t } = useTranslation()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    let active = true
    setLoading(true)
    api.jobsShelf()
      .then((res) => { if (active) setData(res) })
      .catch(() => { if (active) setData(null) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [open, tick])

  if (!open) return null

  const low = data?.low_score || []
  const expired = data?.expired || []
  const uncon = data?.unconsiderable || []

  return (
    <div
      className="fixed inset-0 z-40 flex items-end sm:items-center justify-center p-3 sm:p-6 shelf-overlay"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="panel w-full max-w-[1100px] max-h-[min(88vh,820px)] flex flex-col p-4 shelf-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="job-shelf-title"
      >
        <div className="flex items-start justify-between gap-3 mb-3 shrink-0">
          <div>
            <h2 id="job-shelf-title" className="font-pixel text-[13px] text-amber-retro flex items-center gap-2">
              <Archive size={16} /> {t('shelf.title')}
            </h2>
            <p className="font-mono text-[12px] text-slate-500 mt-1 leading-5 max-w-[52rem]">
              {t('shelf.subtitle')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="panel p-2 text-slate-400 hover:text-slate-100"
            title={t('shelf.close')}
          >
            <X size={16} />
          </button>
        </div>

        {loading && !data ? (
          <div className="font-mono text-[12px] text-slate-500 py-10 text-center">{t('shelf.loading')}</div>
        ) : (
          <div className="flex flex-col lg:flex-row gap-4 min-h-0 flex-1 overflow-hidden">
            <Section
              icon={TrendingDown}
              color="#94a3b8"
              title={t('shelf.lowScore')}
              hint={t('shelf.lowScoreHint')}
              jobs={low}
              stageKey="low_score"
              onSelect={onSelectJob}
            />
            <Section
              icon={Clock}
              color="#fbbf24"
              title={t('shelf.expired')}
              hint={t('shelf.expiredHint')}
              jobs={expired}
              stageKey="expired"
              onSelect={onSelectJob}
            />
            <Section
              icon={Ban}
              color="#f43f5e"
              title={t('shelf.unconsiderable')}
              hint={t('shelf.unconsiderableHint')}
              jobs={uncon}
              stageKey="unconsiderable"
              onSelect={onSelectJob}
            />
          </div>
        )}
      </div>
    </div>
  )
}
