// Employer research board — Dana (Agent 2) dossiers from company_dossiers.
// # Ref: dashboard-frontend-expert Companies page (list + verdict filter).

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck } from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'

const FILTERS = ['all', 'PROCEED', 'AVOID']

function VerdictChip({ verdict, t }) {
  const v = (verdict || '').toUpperCase()
  const proceed = v === 'PROCEED'
  const avoid = v === 'AVOID'
  const color = proceed ? '#10b981' : avoid ? '#f43f5e' : '#64748b'
  const label = proceed ? t('job.badges.proceed') : avoid ? t('job.badges.avoid') : t('research.pending')
  return (
    <span className="font-mono text-[12px] px-1.5 py-0.5 border shrink-0" style={{ color, borderColor: color }}>
      {label}
    </span>
  )
}

export default function ResearchBoard({ tick, onSelectCompany }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const d = await api.dossiers()
        if (active) setRows(d || [])
      } catch { /* backend not up */ }
      finally { if (active) setLoading(false) }
    }
    load()
    const id = setInterval(load, 15000)
    return () => { active = false; clearInterval(id) }
  }, [tick])

  const shown = useMemo(() => {
    if (filter === 'all') return rows
    return rows.filter((r) => (r.vetting_verdict || '').toUpperCase() === filter)
  }, [rows, filter])

  return (
    <section className="panel p-3 mt-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div>
          <h2 className="font-pixel text-[12px] text-emerald-retro flex items-center gap-1.5">
            <ShieldCheck size={14} /> {t('research.title')}
          </h2>
          <div className="font-mono text-[11px] text-slate-600">{t('research.subtitle')}</div>
        </div>
        <span className="font-mono text-[12px] text-slate-500">
          {loading ? t('research.loading') : t('research.count', { n: shown.length })}
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-2">
        {FILTERS.map((key) => {
          const active = filter === key
          const label = key === 'all' ? t('research.filterAll') : key === 'PROCEED' ? t('job.badges.proceed') : t('job.badges.avoid')
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`font-mono text-[12px] px-2.5 py-1.5 panel ${active ? 'text-amber-retro' : 'text-slate-400'}`}
              style={active ? { borderColor: '#f59e0b' } : undefined}
            >
              {label}
            </button>
          )
        })}
      </div>

      <div className="h-[min(50vh,420px)] overflow-y-auto kanban-scroll space-y-1.5">
        {shown.length === 0 && !loading && (
          <div className="font-mono text-[12px] text-slate-600 text-center py-8">{t('research.empty')}</div>
        )}
        {shown.map((row) => (
          <button
            key={row.id || row.company_name}
            type="button"
            onClick={() => onSelectCompany(row.company_name)}
            className="w-full text-left panel-inset p-2.5 hover:border-cyan-retro transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-mono text-[13px] text-slate-100 truncate" title={row.company_name}>
                  {row.company_name}
                </div>
                <div className="font-mono text-[12px] text-slate-500 mt-0.5">
                  {t('research.jobs')}: {row.job_count ?? 0}
                  {row.updated_at && (
                    <span className="text-slate-600"> · {formatHKDateTime(row.updated_at)} HKT</span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <VerdictChip verdict={row.vetting_verdict} t={t} />
                {row.confidence != null && (
                  <span className="font-mono text-[12px] text-slate-400">{row.confidence}/100</span>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}
