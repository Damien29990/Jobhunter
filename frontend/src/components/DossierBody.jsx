// Structured Dana (Agent 2) employer brief. Payload is typed on the API;
// this component never JSON.parses dossier_json.
// # Ref: dashboard-frontend-expert company dossier viewer.

import {
  ShieldCheck, Star, TriangleAlert, FileText, ExternalLink, ListChecks,
} from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'
import { asStringList } from '../lib/lists'

function Chip({ children, color = '#06b6d4' }) {
  return (
    <span className="font-mono text-[12px] px-1.5 py-0.5 border" style={{ color, borderColor: color }}>
      {children}
    </span>
  )
}

function ConfidenceMeter({ value, label }) {
  const v = Math.max(0, Math.min(100, value ?? 0))
  const color = v >= 70 ? '#10b981' : v >= 40 ? '#f59e0b' : '#64748b'
  return (
    <div>
      <div className="flex justify-between font-mono text-[12px] mb-1">
        <span className="text-slate-400">{label}</span>
        <span style={{ color }}>{value == null ? '—' : `${value}/100`}</span>
      </div>
      <div className="h-3 panel-inset" role="meter" aria-label={label} aria-valuenow={value ?? 0} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full transition-all" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  )
}

function FlagColumn({ title, items, color, icon: Icon, emptyLabel }) {
  return (
    <div className="panel-inset p-2.5 min-h-[120px]">
      <div className="font-mono text-[12px] mb-1 flex items-center gap-1" style={{ color }}>
        <Icon size={13} /> {title}
      </div>
      <ul className="font-mono text-[12px] text-slate-300 list-disc pl-4 space-y-1 leading-5">
        {items.length === 0 && <li className="text-slate-600 list-none pl-0">{emptyLabel}</li>}
        {items.map((f, i) => <li key={i} className="break-words">{f}</li>)}
      </ul>
    </div>
  )
}

export default function DossierBody({ dossier, t, linkedJobs, onSelectJob, markdownUrl, showMarkdown = true }) {
  if (!dossier) {
    return <div className="font-mono text-[12px] text-slate-500 leading-5">{t('detail.noDossier')}</div>
  }

  const d = dossier.dossier || {}
  const verdict = (dossier.vetting_verdict || d.vetting_verdict || '').toUpperCase()
  const proceed = verdict === 'PROCEED'
  const avoid = verdict === 'AVOID'
  const verdictColor = proceed ? '#10b981' : avoid ? '#f43f5e' : '#64748b'
  const verdictLabel = proceed
    ? t('job.badges.proceed')
    : avoid
      ? t('job.badges.avoid')
      : t('research.pending')
  const confidence = dossier.confidence ?? d.confidence
  const news = asStringList(d.recent_news_and_events)
  const tech = asStringList(d.detected_tech_stack)
  const sources = asStringList(dossier.source_urls).length
    ? asStringList(dossier.source_urls)
    : asStringList(d.source_urls)
  const jobs = linkedJobs || dossier.linked_jobs || []

  return (
    <div className="space-y-4">
      <div className="panel-inset p-3 space-y-2" style={{ borderColor: verdictColor }}>
        <div className="flex flex-wrap items-center gap-2">
          <ShieldCheck size={16} style={{ color: verdictColor }} />
          <span className="font-pixel text-[12px]" style={{ color: verdictColor }}>{verdictLabel}</span>
          {verdict && <Chip color={verdictColor}>{verdict}</Chip>}
        </div>
        <ConfidenceMeter value={confidence} label={t('research.confidence')} />
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[12px] text-slate-400">
          {d.salary_benchmark && (
            <span><span className="text-slate-600">{t('research.salary')}: </span>{d.salary_benchmark}</span>
          )}
          {dossier.updated_at && (
            <span title={t('research.updated')}>{formatHKDateTime(dossier.updated_at)} HKT</span>
          )}
        </div>
      </div>

      {tech.length > 0 && (
        <div>
          <div className="font-mono text-[12px] text-cyan-retro mb-1">{t('detail.sections.techStack')}</div>
          <div className="flex flex-wrap gap-1.5">{tech.map((s, i) => <Chip key={`${s}-${i}`}>{s}</Chip>)}</div>
        </div>
      )}

      {d.engineering_culture && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('detail.sections.culture')}</div>
          <p className="font-sans text-[13px] text-slate-300 leading-relaxed break-words">{d.engineering_culture}</p>
        </div>
      )}

      {d.glassdoor_sentiment && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('detail.sections.sentiment')}</div>
          <p className="font-sans text-[13px] text-slate-400 leading-relaxed break-words">{d.glassdoor_sentiment}</p>
        </div>
      )}

      {news.length > 0 && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('detail.sections.news')}</div>
          <ul className="font-sans text-[13px] text-slate-400 list-disc pl-4 space-y-1 leading-relaxed">
            {news.map((n, i) => <li key={i} className="break-words">{n}</li>)}
          </ul>
        </div>
      )}

      {d.architectural_trade_offs && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('research.tradeoffs')}</div>
          <p className="font-sans text-[13px] text-slate-400 leading-relaxed break-words">{d.architectural_trade_offs}</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <FlagColumn
          title={t('detail.sections.greenFlags')}
          items={asStringList(d.green_flags)}
          color="#10b981"
          icon={Star}
          emptyLabel={t('detail.none')}
        />
        <FlagColumn
          title={t('detail.sections.redFlags')}
          items={asStringList(d.red_flags)}
          color="#f43f5e"
          icon={TriangleAlert}
          emptyLabel={t('detail.none')}
        />
      </div>

      {asStringList(d.reverse_interview_questions).length > 0 && (
        <div>
          <div className="font-mono text-[12px] text-amber-retro mb-1 flex items-center gap-1">
            <ListChecks size={14} /> {t('detail.sections.reverseQs')}
          </div>
          <ul className="space-y-1.5">
            {asStringList(d.reverse_interview_questions).map((q, i) => (
              <li key={i} className="flex items-start gap-2 font-mono text-[12px] text-slate-300 leading-5">
                <input type="checkbox" className="mt-1 shrink-0" />
                <span className="break-words">{q}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sources.length > 0 && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('research.sources')}</div>
          <ul className="space-y-1">
            {sources.map((url) => (
              <li key={url}>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1 font-mono text-[12px] text-cyan-retro hover:underline break-all"
                >
                  <ExternalLink size={12} className="mt-0.5 shrink-0" /> {url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {jobs.length > 0 && onSelectJob && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('research.linkedJobs')}</div>
          <ul className="space-y-1">
            {jobs.map((job) => (
              <li key={job.id}>
                <button
                  type="button"
                  onClick={() => onSelectJob(job)}
                  className="w-full text-left font-mono text-[12px] text-slate-300 hover:text-cyan-retro panel-inset px-2 py-1.5"
                >
                  <span className="text-slate-100">{job.job_title}</span>
                  {job.match_score != null && (
                    <span className="text-slate-500"> · {job.match_score}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {showMarkdown && (markdownUrl || dossier.company_name) && (
        <div className="space-y-2">
          <a
            href={markdownUrl || api.dossierMarkdownUrl(dossier.company_name)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-mono text-[12px] text-cyan-retro hover:underline"
          >
            <FileText size={14} /> {t('detail.sections.openDossier')}
          </a>
          <iframe
            src={markdownUrl || api.dossierMarkdownUrl(dossier.company_name)}
            className="w-full h-[min(50vh,420px)] panel-inset"
            title={t('research.previewReport')}
          />
        </div>
      )}
    </div>
  )
}
