// DetailDrawer.jsx — slide-in detail panel with tabs:
//   Overview | Dossier | Application Pack | CV Previewer

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X, Building2, MapPin, Coins, Link as LinkIcon, FileText, FileCheck,
  ClipboardList, TriangleAlert, ShieldCheck, ExternalLink, LoaderCircle,
  RefreshCw, CircleCheck, Unlink, Power, Ban, RotateCcw,
} from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'
import DossierBody from './DossierBody'
import { /* JobStageStrip, */ StageEmptyCta, StagePaneAction, useJobStageRunner } from './JobStageActions'

function Chip({ children, color = '#06b6d4' }) {
  return (
    <span className="font-mono text-[11px] px-1.5 py-0.5 border" style={{ color, borderColor: color }}>
      {children}
    </span>
  )
}

function Bar({ label, value, color }) {
  const v = Math.max(0, Math.min(100, value ?? 0))
  return (
    <div>
      <div className="flex justify-between font-mono text-[12px] mb-1">
        <span className="text-slate-400">{label}</span>
        <span style={{ color }}>{value ?? '—'}</span>
      </div>
      <div className="h-3 panel-inset">
        <div className="h-full transition-all" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  )
}

function JobStatusRow({ job, onChanged }) {
  const { t } = useTranslation()
  const [expired, setExpired] = useState(!!job.expired)
  const [unconsiderable, setUnconsiderable] = useState(!!job.unconsiderable)
  const [checking, setChecking] = useState(false)
  const [checkRes, setCheckRes] = useState(null)

  useEffect(() => {
    setExpired(!!job.expired)
    setUnconsiderable(!!job.unconsiderable)
  }, [job.id, job.expired, job.unconsiderable])

  async function check() {
    setChecking(true); setCheckRes(null)
    try {
      const res = await api.checkJob(job.id)
      setCheckRes(res)
    } catch (e) {
      setCheckRes({ exists: false, reason: String(e.message || e) })
    } finally {
      setChecking(false)
    }
  }
  async function toggleExpire(next) {
    setExpired(next)
    try {
      await api.setJobExpired(job.id, next)
      onChanged?.()
    } catch { /* ignore */ }
  }

  const exists = checkRes?.exists
  const mismatch = !!checkRes?.listing_mismatch
  const checkOk = exists && !mismatch
  return (
    <div className="panel-inset px-2.5 py-1.5 flex flex-wrap items-center gap-2">
      <span
        className="font-pixel text-[11px] flex items-center gap-1 shrink-0"
        style={{ color: expired ? '#f43f5e' : '#10b981' }}
      >
        {expired ? <><Unlink size={12} /> {t('job.expired')}</> : <><CircleCheck size={12} /> {t('job.active')}</>}
      </span>

      <button
        onClick={check}
        disabled={checking}
        className="font-mono text-[11px] px-2 py-1 panel flex items-center gap-1 text-cyan-retro disabled:opacity-50"
      >
        {checking ? <LoaderCircle size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        {t('job.check')}
      </button>

      {expired ? (
        <button
          onClick={() => toggleExpire(false)}
          className="font-mono text-[11px] px-2 py-1 panel flex items-center gap-1 text-emerald-retro"
        >
          <Power size={12} /> {t('job.reactivate')}
        </button>
      ) : (
        <button
          onClick={() => toggleExpire(true)}
          className="font-mono text-[11px] px-2 py-1 panel flex items-center gap-1 text-rose-retro"
        >
          <X size={12} /> {t('job.expire')}
        </button>
      )}

      {unconsiderable ? (
        <button
          onClick={async () => {
            setUnconsiderable(false)
            try {
              await api.setJobUnconsiderable(job.id, false)
              onChanged?.()
            } catch { /* ignore */ }
          }}
          className="font-mono text-[11px] px-2 py-1 panel flex items-center gap-1 text-emerald-retro"
        >
          <RotateCcw size={12} /> {t('job.considerAgain')}
        </button>
      ) : (
        <button
          onClick={async () => {
            setUnconsiderable(true)
            try {
              await api.setJobUnconsiderable(job.id, true)
              onChanged?.()
            } catch { /* ignore */ }
          }}
          className="font-mono text-[11px] px-2 py-1 panel flex items-center gap-1 text-slate-300"
          title={t('job.unconsiderableHint')}
        >
          <Ban size={12} /> {t('job.markUnconsiderable')}
        </button>
      )}

      {checkRes && (
        <span
          className="font-mono text-[11px] flex items-center gap-1 w-full leading-4"
          style={{ color: checkOk ? '#10b981' : '#fbbf24' }}
          title={checkRes.reason || ''}
        >
          {checkOk
            ? <><CircleCheck size={12} /> {t('job.checkExists')} ({checkRes.status_code})</>
            : <><TriangleAlert size={12} /> {mismatch ? t('job.checkMismatch') : t('job.checkMissing')}{checkRes.reason ? ` — ${checkRes.reason}` : ''}</>}
        </span>
      )}
      {checkRes && checkRes.expired_suggested && !expired && (
        <button
          onClick={() => toggleExpire(true)}
          className="font-mono text-[11px] px-2 py-1 panel text-rose-retro"
        >
          {t('job.expireSuggested')}
        </button>
      )}
    </div>
  )
}

function OverviewTab({ job, dossier, t, onJobChanged }) {
  return (
    <div className="space-y-3">
      <JobStatusRow job={job} onChanged={onJobChanged} />
      {/* Rework this job — Overview only. Restore by uncommenting JobStageStrip import + this:
      <JobStageStrip runner={runner} activeTab="overview" onSelectTab={onSelectTab} />
      */}
      <div>
        <div className="font-mono text-[16px] text-slate-100 leading-tight">{job.job_title}</div>
        <div className="flex items-center gap-1.5 mt-1">
          <Building2 size={14} className="text-slate-500" />
          <span className="font-mono text-[13px] text-slate-300">{job.company_name || t('job.confidential')}</span>
          {dossier?.vetting_verdict && (
            <Chip color={dossier.vetting_verdict === 'PROCEED' ? '#10b981' : '#f43f5e'}>
              {dossier.vetting_verdict === 'PROCEED' ? t('job.badges.proceed') : t('job.badges.avoid')}
            </Chip>
          )}
        </div>
        <div className="flex flex-wrap gap-3 mt-1.5 font-mono text-[12px] text-slate-400">
          {job.location_mode && <span className="flex items-center gap-1"><MapPin size={13} /> {job.location_mode}</span>}
          {job.salary_range && <span className="flex items-center gap-1"><Coins size={13} /> {job.salary_range}</span>}
          {job.source_lane && <Chip>{job.source_lane}</Chip>}
          {job.target_industry && <Chip color="#06b6d4">{job.target_industry}</Chip>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Bar label={t('detail.hardSkill')} value={job.hard_skill_match_score} color="#10b981" />
        <Bar label={t('detail.transfer')} value={job.transferability_score} color="#06b6d4" />
        <Bar label={t('detail.composite')} value={job.match_score} color="#f59e0b" />
      </div>
      <div className="font-mono text-[11px] text-slate-600">{t('detail.weighting')}</div>

      {job.matched_skills?.length > 0 && (
        <div>
          <div className="font-mono text-[12px] text-emerald-retro mb-1">{t('job.matched')}</div>
          <div className="flex flex-wrap gap-1.5">{job.matched_skills.map((s) => <Chip key={s} color="#10b981">{s}</Chip>)}</div>
        </div>
      )}
      {job.missing_skills?.length > 0 && (
        <div>
          <div className="font-mono text-[12px] text-rose-retro mb-1">{t('job.gaps')}</div>
          <div className="flex flex-wrap gap-1.5">{job.missing_skills.map((s) => <Chip key={s} color="#f43f5e">{s}</Chip>)}</div>
        </div>
      )}
      {job.transferable_strengths?.length > 0 && (
        <div className="panel-inset p-2.5">
          <div className="font-mono text-[12px] text-cyan-retro mb-1">{t('job.transferable')}</div>
          <ul className="font-mono text-[12px] text-slate-300 list-disc pl-4 space-y-0.5">
            {job.transferable_strengths.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {job.career_advisory_note && (
        <div className="panel-inset p-2.5">
          <div className="font-mono text-[12px] text-amber-retro mb-1">{t('job.advisory')}</div>
          <p className="font-mono text-[12px] text-slate-300">{job.career_advisory_note}</p>
        </div>
      )}
      {job.jd_snippet && (
        <div>
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('job.jdSnippet')}</div>
          <p className="font-sans text-[13px] text-slate-400 leading-relaxed">{job.jd_snippet}</p>
        </div>
      )}
      {job.job_url && (
        <a href={job.job_url} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-mono text-[12px] text-cyan-retro hover:underline">
          <LinkIcon size={14} /> {t('job.openPosting')} <ExternalLink size={12} />
        </a>
      )}
    </div>
  )
}

function DossierTab({ jobId, dossier, t, onSelectJob, emptyCta, paneAction }) {
  if (!dossier) return emptyCta || null
  return (
    <div className="space-y-3">
      <div className="flex justify-end">{paneAction}</div>
      <DossierBody
        dossier={dossier}
        t={t}
        onSelectJob={onSelectJob}
        markdownUrl={jobId != null ? api.jobResearchUrl(jobId) : undefined}
      />
    </div>
  )
}

function AppPackTab({ job, t, previewKey, emptyCta, paneAction }) {
  if (!job.application_checklist_path) return emptyCta || null
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileCheck size={16} className="text-rose-retro shrink-0" />
          <span className="font-pixel text-[12px] text-rose-retro">{t('detail.appReady')}</span>
        </div>
        {paneAction}
      </div>
      <iframe
        src={`${api.jobChecklistUrl(job.id)}?v=${previewKey}`}
        className="w-full h-[60vh] panel-inset"
        title="Application Checklist"
      />
    </div>
  )
}

function CvTab({ job, t, previewKey, emptyCta, paneAction, candidateId }) {
  if (!job.cv_pdf_path && !job.cv_typ_path) return emptyCta || null
  const cvSrc = api.jobCvUrl(job.id, { candidateId, v: previewKey })
  const cvDownload = api.jobCvUrl(job.id, { candidateId, download: true })
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={16} className="text-amber-retro shrink-0" />
          <span className="font-pixel text-[12px] text-amber-retro">
            {job.cv_status === 'MATERIALS_GENERATED' ? t('detail.cvReady') : t('detail.cvTypOnly')}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          {paneAction}
          <a
            href={cvSrc}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[12px] px-2 py-1 panel-inset text-slate-200 hover:text-cyan-retro"
          >
            {t('detail.openCvNewTab')}
          </a>
          <a
            href={cvDownload}
            download
            className="font-mono text-[12px] px-2 py-1 panel-inset text-slate-200 hover:text-emerald-retro"
          >
            {t('detail.downloadCv')}
          </a>
        </div>
      </div>
      <iframe src={cvSrc} className="w-full h-[60vh] panel-inset" title="CV Preview" />
    </div>
  )
}

const TABS = [
  { key: 'overview', labelKey: 'detail.tabs.overview', icon: Building2 },
  { key: 'dossier', labelKey: 'detail.tabs.dossier', icon: ShieldCheck },
  { key: 'pack', labelKey: 'detail.tabs.pack', icon: ClipboardList },
  { key: 'cv', labelKey: 'detail.tabs.cv', icon: FileText },
]

export default function DetailDrawer({
  jobId,
  candidateId,
  agentStatus,
  onClose,
  onSelectJob,
  onStageStarted,
}) {
  const { t } = useTranslation()
  const [job, setJob] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [tab, setTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [previewKey, setPreviewKey] = useState(0)

  const loadJob = useCallback((opts) => {
    const soft = !!(opts && opts.soft)
    let active = true
    if (!soft) {
      setLoading(true)
      setJob(null)
      setDossier(null)
    }
    api.job(jobId)
      .then(async (j) => {
        if (!active) return
        setJob(j)
        let d = j?.dossier || null
        if (!d) {
          d = await api.jobDossier(jobId).catch(() => null)
        }
        if (!d && j?.company_name) {
          d = await api.dossier(j.company_name).catch(() => null)
        }
        if (!active) return
        setDossier(d)
        if (soft) setPreviewKey((n) => n + 1)
      })
      .catch(() => { if (active && !soft) setJob(null) })
      .finally(() => { if (active && !soft) setLoading(false) })
    return () => { active = false }
  }, [jobId])

  useEffect(() => {
    setTab('overview')
  }, [jobId])

  useEffect(() => {
    const stop = loadJob()
    return () => stop()
  }, [loadJob])

  const refreshJob = useCallback(() => {
    loadJob({ soft: true })
  }, [loadJob])

  const runner = useJobStageRunner({
    job,
    dossier: dossier || job?.dossier,
    candidateId,
    agentStatus,
    onRefresh: refreshJob,
    onStarted: onStageStarted,
  })

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside className="relative w-full max-w-xl panel border-l-4 border-amber-retro h-full flex flex-col">
        <div className="flex items-center justify-between p-3 border-b-2 border-ink-700">
          <h3 className="font-pixel text-[13px] text-amber-retro">{t('detail.title')}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-rose-retro"><X size={20} /></button>
        </div>

        <div className="flex border-b-2 border-ink-700">
          {TABS.map((tb) => {
            const Icon = tb.icon
            const active = tab === tb.key
            return (
              <button
                key={tb.key}
                onClick={() => setTab(tb.key)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 font-mono text-[12px] border-r border-ink-700 last:border-r-0 ${
                  active ? 'bg-ink-700 text-amber-retro' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                <Icon size={14} /> {t(tb.labelKey)}
              </button>
            )
          })}
        </div>

        {job && runner.error && tab !== 'overview' && (
          <div className="px-4 py-2 border-b-2 border-ink-700 font-mono text-[12px] text-rose-retro leading-4">
            {runner.error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center gap-2 font-mono text-[13px] text-slate-500">
              <LoaderCircle size={16} className="animate-spin" /> {t('detail.loading')}
            </div>
          ) : !job ? (
            <div className="font-mono text-[13px] text-slate-500">{t('detail.jobNotFound')}</div>
          ) : (
            <>
              {tab === 'overview' && (
                <OverviewTab
                  job={job}
                  dossier={dossier || job.dossier}
                  t={t}
                  onJobChanged={refreshJob}
                />
              )}
              {tab === 'dossier' && (
                <DossierTab
                  jobId={jobId}
                  dossier={dossier || job.dossier}
                  t={t}
                  emptyCta={<StageEmptyCta agentKey="dana" runner={runner} />}
                  paneAction={<StagePaneAction agentKey="dana" runner={runner} />}
                  onSelectJob={(next) => {
                    if (next?.id && next.id !== jobId) onSelectJob?.(next)
                  }}
                />
              )}
              {tab === 'pack' && (
                <AppPackTab
                  job={job}
                  t={t}
                  previewKey={previewKey}
                  emptyCta={<StageEmptyCta agentKey="clara" runner={runner} />}
                  paneAction={<StagePaneAction agentKey="clara" runner={runner} />}
                />
              )}
              {tab === 'cv' && (
                <CvTab
                  job={job}
                  t={t}
                  previewKey={previewKey}
                  candidateId={candidateId}
                  emptyCta={<StageEmptyCta agentKey="leo" runner={runner} />}
                  paneAction={<StagePaneAction agentKey="leo" runner={runner} />}
                />
              )}
            </>
          )}
        </div>

        {job && (
          <div className="p-2.5 border-t-2 border-ink-700 font-mono text-[11px] text-slate-600">
            job #{job.id} · {t('detail.created')} {formatHKDateTime(job.created_at)} HKT
          </div>
        )}
      </aside>
    </div>
  )
}
