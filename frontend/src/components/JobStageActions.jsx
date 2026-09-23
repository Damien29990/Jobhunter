// Per-job stage Run / Re-run / Stop for Dana, Leo, Clara.
// Dashboard is additive: agents own writes; we only POST existing /agents/{route}/run.
// Score thresholds stay on the API (`/gates`); the UI never re-derives them.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoaderCircle, Play, RefreshCw, Square } from 'lucide-react'
import { api } from '../lib/api'
import { AGENT_BY_KEY } from '../lib/agents'

export const JOB_STAGES = [
  { agentKey: 'dana', tab: 'dossier', has: (job, dossier) => !!(dossier || job?.dossier) },
  { agentKey: 'leo', tab: 'cv', has: (job) => !!(job?.cv_pdf_path || job?.cv_typ_path || job?.cover_letter_pdf_path || job?.cover_letter_typ_path) },
  { agentKey: 'clara', tab: 'pack', has: (job) => !!job?.application_checklist_path },
]

export function useJobStageRunner({
  job,
  dossier,
  candidateId,
  agentStatus,
  onRefresh,
  onStarted,
}) {
  const { t } = useTranslation()
  const [gates, setGates] = useState(null)
  const [busyKey, setBusyKey] = useState(null)
  const [error, setError] = useState(null)
  const prevWorking = useRef({})
  const startTimeout = useRef(null)

  useEffect(() => () => {
    if (startTimeout.current) window.clearTimeout(startTimeout.current)
  }, [])

  useEffect(() => {
    let active = true
    api.gates()
      .then((g) => { if (active) setGates(g) })
      .catch(() => { /* gates are hints only */ })
    return () => { active = false }
  }, [])

  useEffect(() => {
    for (const { agentKey } of JOB_STAGES) {
      const working = agentStatus?.[agentKey]?.state === 'WORKING'
      if (prevWorking.current[agentKey] && !working) {
        onRefresh?.()
      }
      prevWorking.current[agentKey] = working
      if (working && busyKey === agentKey) setBusyKey(null)
    }
  }, [agentStatus, onRefresh, busyKey])

  const run = useCallback(async (agentKey, extra = {}) => {
    if (!job?.id) return
    setError(null)
    setBusyKey(agentKey)
    try {
      const body = { job_id: Number(job.id) }
      if (candidateId) body.candidate_id = candidateId
      if (job.company_name) body.company = job.company_name
      if (agentKey === 'dana') {
        body.force_refresh = true
        body.force = true
      }
      if (agentKey === 'leo' || agentKey === 'clara') {
        body.force_refresh = true
      }
      if (extra.force_refresh) body.force_refresh = true
      if (extra.force) body.force = true
      if (extra.document) body.document = extra.document
      const res = await api.runAgent(api.agentRoute[agentKey], body)
      if (res?.ok) {
        onStarted?.()
        if (startTimeout.current) window.clearTimeout(startTimeout.current)
        startTimeout.current = window.setTimeout(() => {
          setBusyKey((k) => (k === agentKey ? null : k))
        }, 8000)
      } else {
        setError(res?.error || t('detail.stage.failed'))
        setBusyKey(null)
      }
    } catch (e) {
      setError(String(e.message || e))
      setBusyKey(null)
    }
  }, [job, candidateId, onStarted, t])

  const stop = useCallback(async (agentKey) => {
    setError(null)
    setBusyKey(agentKey)
    try {
      await api.stopAgent(agentKey)
      onStarted?.()
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusyKey(null)
    }
  }, [onStarted])

  const hintFor = useCallback((agentKey) => {
    if (!job || !gates) return null
    const score = Number(job.match_score ?? 0)
    const verdict = String(dossier?.vetting_verdict || job.dossier?.vetting_verdict || '').toUpperCase()
    const cvStatus = job.cv_status || ''
    const danaMin = Number(gates.agent2_pool_min_score)
    if (agentKey === 'dana' && Number.isFinite(danaMin) && score < danaMin) {
      return t('detail.stage.hintDana', { n: danaMin })
    }
    if (agentKey === 'leo' && verdict !== gates.agent3_cv_required_verdict) {
      return t('detail.stage.hintLeo', { verdict: gates.agent3_cv_required_verdict })
    }
    if (agentKey === 'clara' && cvStatus !== gates.agent4_required_cv_status) {
      return t('detail.stage.hintClara')
    }
    return null
  }, [job, dossier, gates, t])

  const snapshot = useMemo(() => ({
    job, dossier, busyKey, error, gates, agentStatus, run, stop, hintFor,
  }), [job, dossier, busyKey, error, gates, agentStatus, run, stop, hintFor])

  return snapshot
}

function StageButton({ stage, runner, highlight, onSelectTab }) {
  const { t } = useTranslation()
  const { job, dossier, busyKey, agentStatus, run, stop } = runner
  const agent = AGENT_BY_KEY[stage.agentKey]
  const working = agentStatus?.[stage.agentKey]?.state === 'WORKING'
  const starting = busyKey === stage.agentKey && !working
  const hasOutput = stage.has(job, dossier)
  const label = working
    ? t('detail.stage.stop')
    : hasOutput
      ? t('detail.stage.rerun')
      : t('detail.stage.run')
  const Icon = working ? Square : hasOutput ? RefreshCw : Play

  return (
    <button
      type="button"
      disabled={starting}
      onClick={() => {
        onSelectTab?.(stage.tab)
        if (working) stop(stage.agentKey)
        else run(stage.agentKey, hasOutput ? { force_refresh: true } : {})
      }}
      className={`flex-1 min-w-0 panel px-2 py-2 flex flex-col items-start gap-1 text-left disabled:opacity-50 ${
        highlight ? 'bg-ink-700' : ''
      }`}
      title={t(`detail.stage.${stage.agentKey}Title`)}
    >
      <span className="font-pixel text-[11px] leading-none" style={{ color: agent.accent }}>
        {agent.name}
      </span>
      <span className="flex items-center gap-1.5 font-mono text-[12px] text-slate-200">
        {starting || working ? (
          <LoaderCircle size={16} className="animate-spin shrink-0" style={{ color: working ? '#10b981' : agent.accent }} />
        ) : (
          <Icon size={16} className="shrink-0" style={{ color: working ? '#f43f5e' : agent.accent }} />
        )}
        <span className="truncate">{label}</span>
      </span>
    </button>
  )
}

export function JobStageStrip({ runner, activeTab, onSelectTab }) {
  const { t } = useTranslation()
  if (!runner.job) return null
  const focused = JOB_STAGES.find((s) => s.tab === activeTab)
  const hints = (focused ? [focused] : JOB_STAGES)
    .map((s) => runner.hintFor(s.agentKey))
    .filter(Boolean)

  return (
    <div className="space-y-1.5">
      <div className="font-pixel text-[11px] text-slate-500">{t('detail.stage.title')}</div>
      <div className="flex gap-2">
        {JOB_STAGES.map((stage) => (
          <StageButton
            key={stage.agentKey}
            stage={stage}
            runner={runner}
            highlight={activeTab === stage.tab}
            onSelectTab={onSelectTab}
          />
        ))}
      </div>
      {hints.map((h) => (
        <div key={h} className="font-mono text-[11px] text-slate-500 leading-4">{h}</div>
      ))}
      {runner.error && (
        <div className="font-mono text-[12px] text-rose-retro leading-4">{runner.error}</div>
      )}
    </div>
  )
}

export function StagePaneAction({ agentKey, runner, extra = {} }) {
  const { t } = useTranslation()
  const stage = JOB_STAGES.find((s) => s.agentKey === agentKey)
  if (!stage || !runner.job || !stage.has(runner.job, runner.dossier)) return null
  const agent = AGENT_BY_KEY[agentKey]
  const working = runner.agentStatus?.[agentKey]?.state === 'WORKING'
  const starting = runner.busyKey === agentKey && !working

  return (
    <button
      type="button"
      disabled={starting}
      onClick={() => (working ? runner.stop(agentKey) : runner.run(agentKey, { force_refresh: true, ...extra }))}
      className="font-mono text-[12px] px-2 py-1 panel inline-flex items-center gap-1.5 text-slate-200 disabled:opacity-50 shrink-0"
      title={t(`detail.stage.${agentKey}Title`)}
    >
      {starting || working ? (
        <LoaderCircle size={16} className="animate-spin" style={{ color: agent.accent }} />
      ) : (
        <RefreshCw size={16} style={{ color: agent.accent }} />
      )}
      {working ? t('detail.stage.stopNamed', { name: agent.name }) : t('detail.stage.rerunNamed', { name: agent.name })}
    </button>
  )
}

export function StageEmptyCta({ agentKey, runner }) {
  const { t } = useTranslation()
  const stage = JOB_STAGES.find((s) => s.agentKey === agentKey)
  if (!stage || !runner.job || stage.has(runner.job, runner.dossier)) return null
  const agent = AGENT_BY_KEY[agentKey]
  const working = runner.agentStatus?.[agentKey]?.state === 'WORKING'
  const starting = runner.busyKey === agentKey && !working
  const hint = runner.hintFor(agentKey)

  return (
    <div className="panel-inset p-3 space-y-2">
      <p className="font-mono text-[13px] text-slate-400 leading-5">
        {t({ dana: 'detail.noDossier', leo: 'detail.noCv', clara: 'detail.noChecklist' }[agentKey])}
      </p>
      {hint && <p className="font-mono text-[11px] text-slate-500 leading-4">{hint}</p>}
      <button
        type="button"
        disabled={starting}
        onClick={() => (working ? runner.stop(agentKey) : runner.run(agentKey))}
        className="font-mono text-[12px] px-3 py-2 panel inline-flex items-center gap-1.5 text-slate-100 disabled:opacity-50"
      >
        {starting || working ? (
          <LoaderCircle size={16} className="animate-spin" style={{ color: agent.accent }} />
        ) : (
          <Play size={16} style={{ color: agent.accent }} />
        )}
        {working ? t('detail.stage.stopNamed', { name: agent.name }) : t('detail.stage.runNamed', { name: agent.name })}
      </button>
    </div>
  )
}
