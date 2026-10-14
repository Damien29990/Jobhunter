// PipelineFinishOverview.jsx — list every application_ready job after a run ends.

import { useTranslation } from 'react-i18next'
import { X, CircleCheck, ExternalLink } from 'lucide-react'
import { formatHKDateTime } from '../lib/api'

export default function PipelineFinishOverview({ overview, onClose, onSelectJob }) {
  const { t } = useTranslation()
  const jobs = overview?.jobs || []
  const failed = overview && overview.success === false

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div
        className="relative panel max-w-xl w-full p-4 flex flex-col"
        style={{ borderColor: failed ? '#f43f5e' : '#10b981', maxHeight: 'calc(100vh - 2rem)' }}
      >
        <div className="flex items-start justify-between gap-3 mb-3 shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <CircleCheck size={16} className={failed ? 'text-rose-retro' : 'text-emerald-retro'} />
              <span className="font-pixel text-[14px] text-emerald-retro">
                {failed ? t('pipelineFinish.failedTitle') : t('pipelineFinish.title')}
              </span>
            </div>
            <div className="font-mono text-[12px] text-slate-400 mt-1">
              {t('pipelineFinish.subtitle', { count: jobs.length })}
              {overview?.finished_at ? ` · ${formatHKDateTime(overview.finished_at)}` : ''}
            </div>
            {failed && overview?.error && (
              <div className="font-mono text-[12px] text-rose-retro mt-1">{overview.error}</div>
            )}
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-rose-retro shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="panel-inset flex-1 min-h-0 overflow-y-auto kanban-scroll" style={{ background: '#070b13' }}>
          {jobs.length === 0 ? (
            <div className="p-4 font-mono text-[12px] text-slate-500 leading-relaxed">
              {t('pipelineFinish.empty')}
            </div>
          ) : (
            <ul>
              {jobs.map((job) => (
                <li key={job.id} className="border-b border-ink-700 last:border-0">
                  <button
                    type="button"
                    onClick={() => onSelectJob?.(job)}
                    className="w-full text-left px-3 py-2.5 hover:bg-white/5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-mono text-[12px] text-slate-200 truncate">
                          {job.company_name || t('pipelineFinish.employer')}
                        </div>
                        <div className="font-sans text-[13px] text-slate-400 truncate">
                          {job.job_title || t('pipelineFinish.role')}
                        </div>
                        <div className="font-mono text-[11px] text-slate-500 mt-0.5">
                          #{job.id}
                          {job.source_domain ? ` · ${String(job.source_domain).replace(/^www\./, '')}` : ''}
                          {job.application_status ? ` · ${job.application_status}` : ''}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="font-pixel text-[12px] text-amber-retro">
                          {job.match_score != null ? job.match_score : '—'}
                        </div>
                        <ExternalLink size={12} className="text-slate-600 ml-auto mt-1" />
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
