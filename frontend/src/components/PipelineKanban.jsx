// PipelineKanban.jsx — 5 columns mapping the agent pipeline to Kanban stages.

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive } from 'lucide-react'
import JobCard from './JobCard'
import JobShelfPanel from './JobShelfPanel'
import { api } from '../lib/api'

export const PIPELINE_STAGES = [
  { key: 'discovered', color: '#64748b' },
  { key: 'vetting', color: '#06b6d4' },
  { key: 'vetted', color: '#10b981' },
  { key: 'materials', color: '#f59e0b' },
  { key: 'applied', color: '#f43f5e' },
]

export const COLUMN_KEYS = PIPELINE_STAGES.map((col) => col.key)

const SHELF_STAGE_KEYS = ['low_score', 'expired', 'unconsiderable']

function classify(job, dossierByCompany) {
  if (job.application_ready) return 'applied'
  if (job.cv_status === 'MATERIALS_GENERATED' || job.cv_status === 'MATERIALS_RENDERED') return 'materials'
  const d = lookupDossier(job, dossierByCompany) || job.dossier
  if (d && d.vetting_verdict) return 'vetted'
  if (job.match_score != null && job.match_score >= 80) return 'vetting'
  return 'discovered'
}

function lookupDossier(job, dossierByCompany) {
  if (!job?.company_name) return null
  return dossierByCompany[job.company_name] || dossierByCompany[job.company_name.toLowerCase()] || null
}

function Column({ col, jobs, dossierByCompany, onSelect, t }) {
  return (
    <div className="flex flex-col panel-inset h-[min(60vh,640px)] w-[280px] shrink-0">
      <div className="px-2.5 py-2 border-b-2 border-ink-700 shrink-0" style={{ borderColor: col.color }}>
        <div className="flex items-center justify-between">
          <span className="font-pixel text-[12px]" style={{ color: col.color }}>{t(`kanban.columns.${col.key}`)}</span>
          <span className="font-mono text-[12px] text-slate-400">{jobs.length}</span>
        </div>
        <div className="font-mono text-[11px] text-slate-600">{t(`kanban.columns.${col.key}Hint`)}</div>
      </div>
      <div className="kanban-scroll flex-1 min-h-0 overflow-y-auto p-2 space-y-2">
        {jobs.length === 0 && (
          <div className="font-mono text-[12px] text-slate-700 text-center py-6">{t('kanban.empty')}</div>
        )}
        {jobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            dossier={lookupDossier(job, dossierByCompany) || job.dossier}
            onClick={() => onSelect(job, col.key)}
          />
        ))}
      </div>
    </div>
  )
}

export default function PipelineKanban({ candidateId, onSelectJob, onJobOrderChange, tick }) {
  const { t } = useTranslation()
  const [jobs, setJobs] = useState([])
  const [dossiers, setDossiers] = useState([])
  const [loading, setLoading] = useState(true)
  const [shelfOpen, setShelfOpen] = useState(false)
  const [shelfCounts, setShelfCounts] = useState({ low_score: 0, expired: 0, unconsiderable: 0 })
  const [shelfJobs, setShelfJobs] = useState({ low_score: [], expired: [], unconsiderable: [] })

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const [j, d, shelf] = await Promise.all([
          api.jobs({ candidate_id: candidateId, page_size: 200, view: 'active' }),
          api.dossiers(),
          api.jobsShelf().catch(() => null),
        ])
        if (!active) return
        setJobs(j.items || [])
        setDossiers(d || [])
        if (shelf?.counts) setShelfCounts(shelf.counts)
        setShelfJobs({
          low_score: shelf?.low_score || [],
          expired: shelf?.expired || [],
          unconsiderable: shelf?.unconsiderable || [],
        })
      } catch { /* backend not up */ }
      finally { if (active) setLoading(false) }
    }
    load()
    const id = setInterval(load, 5000)
    return () => { active = false; clearInterval(id) }
  }, [candidateId, tick])

  const dossierByCompany = useMemo(() => {
    const m = {}
    for (const d of dossiers) {
      if (!d.company_name) continue
      m[d.company_name] = d
      m[d.company_name.toLowerCase()] = d
    }
    return m
  }, [dossiers])

  const byCol = useMemo(() => {
    const m = { discovered: [], vetting: [], vetted: [], materials: [], applied: [] }
    for (const job of jobs) m[classify(job, dossierByCompany)].push(job)
    for (const key of COLUMN_KEYS) {
      m[key].sort((a, b) => Number(!!a.expired) - Number(!!b.expired))
    }
    return m
  }, [jobs, dossierByCompany])

  const jobsByStage = useMemo(() => {
    const m = {}
    for (const key of COLUMN_KEYS) m[key] = byCol[key].map((job) => job.id)
    for (const key of SHELF_STAGE_KEYS) {
      m[key] = (shelfJobs[key] || []).map((job) => job.id)
    }
    return m
  }, [byCol, shelfJobs])

  useEffect(() => {
    onJobOrderChange?.(jobsByStage)
  }, [jobsByStage, onJobOrderChange])

  const COLUMNS = PIPELINE_STAGES

  const shelfTotal = (shelfCounts.low_score || 0) + (shelfCounts.expired || 0) + (shelfCounts.unconsiderable || 0)

  return (
    <section className="panel p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <h2 className="font-pixel text-[12px] text-cyan-retro">{t('kanban.title')}</h2>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[12px] text-slate-500">
            {loading ? t('kanban.loading') : `${jobs.length} ${t('kanban.jobs')}`}
          </span>
          <button
            type="button"
            onClick={() => setShelfOpen(true)}
            className="panel flex items-center gap-1.5 px-2.5 py-1.5 text-slate-300"
            title={t('shelf.openHint')}
          >
            <Archive size={16} />
            <span className="font-mono text-[12px]">{t('shelf.button')}</span>
            {shelfTotal > 0 && (
              <span className="font-mono text-[11px] px-1.5 py-0.5 border border-slate-600 text-slate-400">
                {shelfTotal}
              </span>
            )}
          </button>
        </div>
      </div>
      <div className="flex gap-3 overflow-x-auto kanban-scroll pb-2">
        {COLUMNS.map((col) => (
          <Column key={col.key} col={col} jobs={byCol[col.key]} dossierByCompany={dossierByCompany} onSelect={onSelectJob} t={t} />
        ))}
      </div>
      <JobShelfPanel
        open={shelfOpen}
        tick={tick}
        onClose={() => setShelfOpen(false)}
        onSelectJob={(job, shelfStage) => {
          setShelfOpen(false)
          onSelectJob(job, shelfStage)
        }}
      />
    </section>
  )
}
