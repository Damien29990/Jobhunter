// JobCard.jsx — a job in a Kanban column.

import { useTranslation } from 'react-i18next'
import { Building2, MapPin, Coins, ExternalLink, Clock } from 'lucide-react'
import { formatHKDateTime } from '../lib/api'

function scoreColor(s) {
  if (s == null) return '#475569'
  if (s >= 80) return '#10b981'
  if (s >= 75) return '#f59e0b'
  return '#64748b'
}

function CvBadge({ status }) {
  const { t } = useTranslation()
  if (!status) return null
  const map = {
    MATERIALS_GENERATED: { t: t('job.badges.cv'), c: '#10b981' },
    MATERIALS_RENDERED: { t: t('job.badges.typ'), c: '#06b6d4' },
    GENERATION_FAILED: { t: t('job.badges.fail'), c: '#f43f5e' },
  }
  const m = map[status]
  if (!m) return null
  return (
    <span className="font-mono text-[11px] px-1.5 py-0.5 border" style={{ color: m.c, borderColor: m.c }}>
      {m.t}
    </span>
  )
}

export default function JobCard({ job, dossier, onClick }) {
  const { t } = useTranslation()
  const sc = scoreColor(job.match_score)
  const brief = dossier || job.dossier
  return (
    <button
      onClick={onClick}
      className={`w-full text-left panel-inset p-2.5 hover:-translate-y-0.5 hover:shadow-glow-cyan transition-all ${job.expired ? 'opacity-50' : ''}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[13px] text-slate-100 truncate">{job.job_title}</div>
          <div className="flex items-center gap-1 mt-1">
            <Building2 size={12} className="text-slate-500" />
            <span className="font-mono text-[12px] text-slate-400 truncate">
              {job.company_name || t('job.confidential')}
            </span>
          </div>
        </div>
        <div
          className="font-pixel text-[13px] leading-none px-2 py-1.5 border"
          style={{ color: sc, borderColor: sc }}
          title="composite match score"
        >
          {job.match_score ?? '—'}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mt-2">
        {job.location_mode && (
          <span className="flex items-center gap-1 font-mono text-[12px] text-slate-400">
            <MapPin size={12} /> {job.location_mode}
          </span>
        )}
        {job.salary_range && (
          <span className="flex items-center gap-1 font-mono text-[12px] text-slate-400 truncate max-w-[140px]">
            <Coins size={12} /> {job.salary_range}
          </span>
        )}
        {job.target_industry && (
          <span className="font-mono text-[12px] text-cyan-retro/80">{job.target_industry}</span>
        )}
      </div>

      <div className="flex items-center gap-2 mt-2">
        {brief?.vetting_verdict && (
          <span
            className="font-mono text-[11px] px-1.5 py-0.5 border"
            style={{
              color: brief.vetting_verdict === 'PROCEED' ? '#10b981' : '#f43f5e',
              borderColor: brief.vetting_verdict === 'PROCEED' ? '#10b981' : '#f43f5e',
            }}
          >
            {brief.vetting_verdict === 'PROCEED' ? t('job.badges.proceed') : t('job.badges.avoid')}
          </span>
        )}
        <CvBadge status={job.cv_status} />
        {job.application_ready && (
          <span className="font-mono text-[11px] px-1.5 py-0.5 border text-rose-retro border-rose-retro">
            {t('job.badges.ready')}
          </span>
        )}
        {job.expired && (
          <span className="font-mono text-[11px] px-1.5 py-0.5 border text-slate-500 border-slate-600 line-through">
            {t('job.expired')}
          </span>
        )}
        {job.unconsiderable && (
          <span className="font-mono text-[11px] px-1.5 py-0.5 border text-rose-retro border-rose-retro">
            {t('job.unconsiderable')}
          </span>
        )}
        {job.job_url && (
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="ml-auto text-slate-500 hover:text-cyan-retro"
            title={t('job.openPosting')}
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>

      <div className="flex items-center gap-1 mt-2 font-mono text-[11px] text-slate-500">
        <Clock size={12} />
        <span title={t('job.posted')}>{formatHKDateTime(job.created_at)}</span>
        <span className="text-slate-600">HKT</span>
      </div>
    </button>
  )
}
