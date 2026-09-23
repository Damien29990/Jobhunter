// TutorialModal.jsx — retro dialogue bubble modal shown when an agent desk is clicked.

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Play, LoaderCircle, AlertCircle, Square, Sparkles } from 'lucide-react'
import PixelAgent from './PixelOffice/PixelAgent'
import { AGENT_BY_KEY } from '../lib/agents'
import { api } from '../lib/api'
import { isValidLinkedinUsername, linkedinProfileUrl } from '../lib/contactLinks'

function Field({ field, value, onChange, t, agentKey, candidateId }) {
  if (field.type === 'checkbox') {
    return (
      <label className="flex items-center gap-2 font-mono text-[12px] text-slate-300">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          className="accent-amber-retro"
        />
        {t(field.labelKey)}
      </label>
    )
  }
  if (field.type === 'jobselect') {
    return <JobSelectField field={field} value={value} onChange={onChange} t={t} agentKey={agentKey} />
  }
  if (field.type === 'cvfile') {
    return <CvFileField field={field} value={value} onChange={onChange} t={t} candidateId={candidateId} />
  }
  if (field.type === 'linkedin') {
    return <LinkedinField field={field} value={value} onChange={onChange} t={t} candidateId={candidateId} />
  }
  return (
    <label className="block">
      <span className="font-mono text-[12px] text-slate-500">{t(field.labelKey)}</span>
      <input
        type={field.type}
        placeholder={field.placeholder}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.type === 'number' ? (e.target.value ? Number(e.target.value) : undefined) : e.target.value)}
        className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro"
      />
    </label>
  )
}

// CvFileField — upload a CV file. Reads the file as text and calls
// POST /api/candidates/import-cv (which parses it via Ollama and writes
// the profile JSON). Works for text-based CVs (.txt/.json/.md).
// PDF needs a text-extraction step first (or a backend multipart endpoint).
function CvFileField({ field, value, onChange, t, candidateId }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const [file, setFile] = useState(null)

  async function importFile() {
    if (!file) return
    setBusy(true); setResult(null); setErr(null)
    try {
      const name = (file.name || '').toLowerCase()
      const isText = /\.(txt|md|json|text)$/.test(name)
      const res = isText
        ? await api.importCv(candidateId, await file.text())
        : await api.importCvFile(candidateId, file)
      setResult(res)
      onChange?.(res?.basics?.name || 'imported')
    } catch (e) {
      setErr(String(e.detail || e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="block">
      <span className="font-mono text-[12px] text-slate-500">{t(field.labelKey)}</span>
      <input
        type="file"
        accept=".txt,.json,.md,.text,.pdf,.docx,.doc"
        disabled={busy}
        onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); setErr(null) }}
        className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 file:mr-2"
      />
      {file && <div className="mt-1 font-mono text-[11px] text-slate-400">{file.name}</div>}
      <button
        type="button"
        disabled={busy || !file}
        onClick={importFile}
        className="mt-2 w-full panel px-2 py-1.5 font-pixel text-[10px] text-violet-300 disabled:opacity-40"
      >
        {busy ? t('milo.parsing') : t('profile.uploadCv')}
      </button>
      {result && <div className="mt-1 font-mono text-[12px] text-emerald-retro">{t('milo.imported')}</div>}
      {err && <div className="mt-1 font-mono text-[12px] text-rose-retro">⚠️ {err}</div>}
      <div className="mt-1 font-mono text-[10px] text-slate-600">{t('milo.pdfNote')}</div>
    </div>
  )
}

function LinkedinField({ field, value, onChange, t, candidateId }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const valid = isValidLinkedinUsername(value)

  async function importHandle() {
    if (!valid) return
    setBusy(true); setResult(null); setErr(null)
    try {
      const res = await api.importLinkedin(candidateId, value)
      setResult(res)
      onChange?.(res?.basics?.linkedin || value)
    } catch (e) {
      setErr(String(e.detail || e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const href = linkedinProfileUrl(value)
  return (
    <label className="block">
      <span className="font-mono text-[12px] text-slate-500">{t(field.labelKey)}</span>
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="your-linkedin-slug"
          value={value ?? ''}
          onChange={(e) => { onChange(e.target.value); setResult(null); setErr(null) }}
          className="flex-1 panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro"
        />
        <button
          type="button"
          disabled={busy || !valid}
          onClick={importHandle}
          className="panel px-2 py-1 font-pixel text-[10px] text-violet-300 disabled:opacity-40"
        >
          {busy ? t('milo.linkedinParsing') : t('milo.linkedinImport')}
        </button>
      </div>
      {href && valid && (
        <a href={href} target="_blank" rel="noreferrer" className="mt-1 block font-mono text-[10px] text-cyan-400 truncate">
          {href}
        </a>
      )}
      {result && (
        <div className="mt-1 font-mono text-[12px] text-emerald-retro">
          {result.linkedin_source === 'skeleton' ? t('milo.linkedinSkeleton') : t('milo.linkedinImported')}
        </div>
      )}
      {err && <div className="mt-1 font-mono text-[12px] text-rose-retro">⚠️ {err}</div>}
      <div className="mt-1 font-mono text-[10px] text-slate-600">{t('milo.linkedinHint')}</div>
    </label>
  )
}

// JobSelectField — a dropdown of jobs (id + title + company + score),
// filtered by the agent's pipeline stage so the options are only the jobs
// ready for THIS agent's next step.
function JobSelectField({ field, value, onChange, t, agentKey }) {
  const [jobs, setJobs] = useState([])
  useEffect(() => {
    api.jobsSummary(agentKey).then(setJobs).catch(() => setJobs([]))
  }, [agentKey])
  const emptyKey = agentKey ? `job.empty.${agentKey}` : 'job.empty.all'
  const listSize = Math.min(8, Math.max(4, jobs.length + 1))
  return (
    <label className="block">
      <span className="font-mono text-[12px] text-slate-500">{t(field.labelKey)}</span>
      <select
        size={listSize}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}
        className="mt-1 w-full panel-inset px-2 py-1.5 font-mono text-[12px] leading-5 text-slate-200 max-h-48 overflow-y-auto kanban-scroll focus:outline-none focus:border-amber-retro"
      >
        <option value="">{t(emptyKey)}</option>
        {jobs.map((j) => (
          <option key={j.id} value={j.id} title={`#${j.id} · ${j.job_title} — ${j.company_name || t('job.confidential')}`}>
            #{j.id} · {j.job_title} — {j.company_name || t('job.confidential')} ({j.match_score ?? '—'})
          </option>
        ))}
      </select>
    </label>
  )
}

export default function TutorialModal({ agentKey, candidateId, onClose, onStarted, agentStatus }) {
  const { t } = useTranslation()
  const agent = AGENT_BY_KEY[agentKey]
  const [values, setValues] = useState(() => {
    const v = {}
    for (const f of agent.quickAction.fields) v[f.name] = f.default
    return v
  })
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [liveTail, setLiveTail] = useState([])
  const [liveState, setLiveState] = useState(null)
  const [liveTokens, setLiveTokens] = useState(null)
  const [suggestions, setSuggestions] = useState(null)
  const [loadingSugg, setLoadingSugg] = useState(false)
  const pollRef = useRef(null)

  if (!agent) return null

  // After a run starts, poll this agent's status so live stdout (and any
  // runtime error) shows in the modal — not just in the global log console.
  function startLivePoll() {
    stopLivePoll()
    let ticks = 0
    pollRef.current = setInterval(async () => {
      ticks += 1
      try {
        const s = await api.agentStatus()
        const a = s?.[agentKey]
        if (a) {
          setLiveTail(a.last_lines || [])
          setLiveState(a.state)
          setLiveTokens({
            prompt: a.prompt_tokens || 0,
            completion: a.completion_tokens || 0,
            total: a.total_tokens || 0,
          })
        }
      } catch { /* ignore */ }
      if (ticks >= 20) stopLivePoll()  // ~24s of polling
    }, 1200)
  }
  function stopLivePoll() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }
  useEffect(() => () => stopLivePoll(), [])

  async function run() {
    setRunning(true); setResult(null); setLiveTail([]); setLiveState(null)
    try {
      const body = { candidate_id: candidateId, ...values }
      for (const k of Object.keys(body)) if (body[k] === undefined || body[k] === '') delete body[k]
      const res = await api.runAgent(api.agentRoute[agentKey], body)
      setResult(res)
      if (res.ok) { onStarted?.(); startLivePoll() }
    } catch (e) {
      setResult({ ok: false, error: String(e.message || e) })
    } finally {
      setRunning(false)
    }
  }

  // STOP the running agent. The RUN button becomes STOP while WORKING.
  async function stop() {
    setRunning(true); setResult(null)
    try {
      const res = await api.stopAgent(agentKey)
      setResult(res)
      onStarted?.() // nudge polls so the desk + log console reflect IDLE
    } catch (e) {
      setResult({ ok: false, error: String(e.message || e) })
    } finally {
      setRunning(false)
    }
  }

  // Generate profile-based suggestion tags via local Ollama gemma4:e2b.
  // Rex gets search queries; Dana gets target employer names. Clicking a chip
  // fills the matching quick-action field (query for rex, company for dana).
  async function generateSuggestions() {
    setLoadingSugg(true); setSuggestions(null)
    try {
      const res = await api.suggestions(candidateId)
      setSuggestions(res)
    } catch (e) {
      setSuggestions({ rex: [], dana: [], source: 'fallback', error: String(e.message || e) })
    } finally {
      setLoadingSugg(false)
    }
  }

  // Apply a suggestion chip to the matching quick-action field.
  function applySuggestion(chip) {
    const fieldName = agentKey === 'rex' ? 'query' : 'company'
    setValues((s) => ({ ...s, [fieldName]: chip }))
  }

  // Working if the backend says so OR our live poll just observed WORKING.
  const isWorking =
    (agentStatus?.[agentKey]?.state === 'WORKING') || liveState === 'WORKING'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative panel max-w-lg w-full p-4 flex flex-col" style={{ borderColor: agent.accent, maxHeight: 'calc(100vh - 2rem)', overflowY: 'auto' }}>
        <div className="flex items-start gap-3 mb-3">
          <div className="panel-inset p-1">
            <PixelAgent agentKey={agent.key} state="IDLE" size={64} />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="font-pixel text-[14px]" style={{ color: agent.accent }}>{agent.name}</span>
              <button onClick={onClose} className="text-slate-500 hover:text-rose-retro"><X size={18} /></button>
            </div>
            <div className="font-mono text-[12px] text-slate-400">{t(`agents.${agent.key}.role`)}</div>
            <p className="font-sans text-[13px] text-slate-300 mt-2 leading-relaxed">{t(`agents.${agent.key}.bio`)}</p>
          </div>
        </div>

        <div className="panel-inset p-2.5 mb-3">
          <div className="font-mono text-[12px] mb-1" style={{ color: agent.accent }}>{t('tutorial.purpose')}</div>
          <p className="font-sans text-[13px] text-slate-300">{t(`agents.${agent.key}.purpose`)}</p>
        </div>

        <div className="mb-3">
          <div className="font-mono text-[12px] text-slate-500 mb-1">{t('tutorial.howTo')}</div>
          <ol className="list-decimal pl-4 space-y-0.5">
            {t(`agents.${agent.key}.howTo`, { returnObjects: true }).map((step, i) => (
              <li key={i} className="font-mono text-[12px] text-slate-300">{step}</li>
            ))}
          </ol>
        </div>

        {['rex', 'dana'].includes(agentKey) && (
          <div className="mb-3">
            <div className="panel-inset p-2 mb-2" style={{ borderColor: '#f59e0b55' }}>
              <div className="font-mono text-[10px] text-amber-retro leading-relaxed">
                {t('suggestions.notice')}
              </div>
            </div>

            <button
              onClick={generateSuggestions}
              disabled={loadingSugg}
              className="panel px-2.5 py-1.5 flex items-center gap-1.5 font-pixel text-[11px] disabled:opacity-50"
              style={{ color: agent.accent, borderColor: agent.accent }}
            >
              {loadingSugg ? <LoaderCircle size={13} className="animate-spin" /> : <Sparkles size={13} />}
              {loadingSugg ? t('suggestions.loading') : t('suggestions.generate')}
            </button>

            {suggestions && (suggestions.rex?.length > 0 || suggestions.dana?.length > 0) && (
              <div className="mt-2">
                <div className="font-mono text-[11px] text-slate-500 mb-1">
                  {agentKey === 'rex' ? t('suggestions.rexTitle') : t('suggestions.danaTitle')}
                </div>
                {suggestions.source === 'fallback' && (
                  <div className="font-mono text-[10px] text-amber-retro mb-1.5">
                    {t('suggestions.fallbackNote')}
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {(agentKey === 'rex' ? suggestions.rex : suggestions.dana).map((chip, i) => (
                    <button
                      key={i}
                      onClick={() => applySuggestion(chip)}
                      className="panel-inset px-2 py-1 font-mono text-[11px] text-slate-200 hover:text-slate-50 transition-colors"
                      style={{ borderColor: `${agent.accent}55` }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = agent.accent)}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = `${agent.accent}55`)}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
                <div className="font-mono text-[10px] text-slate-600 mt-1.5">
                  {t('suggestions.clickToFill')}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="panel-inset p-3">
          <div className="font-mono text-[12px] mb-2" style={{ color: agent.accent }}>
            ▶ {t(agent.quickAction.actionKey)}
          </div>
          <div className="space-y-2">
            {agent.quickAction.fields.map((f) => (
              <Field
                key={f.name}
                field={f}
                value={values[f.name]}
                onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))}
                t={t}
                agentKey={agentKey}
                candidateId={candidateId}
              />
            ))}
          </div>
          <button
            onClick={isWorking ? stop : run}
            disabled={running}
            className="mt-3 w-full panel px-3 py-2.5 flex items-center justify-center gap-2 font-pixel text-[12px] disabled:opacity-50"
            style={{
              color: isWorking ? '#f43f5e' : agent.accent,
              borderColor: isWorking ? '#f43f5e' : agent.accent,
            }}
          >
            {running ? <LoaderCircle size={15} className="animate-spin" /> : isWorking ? <Square size={15} /> : <Play size={15} />}
            {running ? t('tutorial.running') : isWorking ? t('tutorial.stop') : t('tutorial.run')}
          </button>
          {result && (
            <div className={`mt-2 font-mono text-[12px] ${result.ok ? 'text-emerald-retro' : 'text-rose-retro'}`}>
              {result.ok
                ? t('tutorial.started', { pid: result.pid })
                : <span className="flex items-center gap-1"><AlertCircle size={13} /> {result.error || t('tutorial.failed')}</span>}
            </div>
          )}

          {(liveTail.length > 0 || liveState) && (
            <div className="mt-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-[11px] text-slate-500">{t('logs.title')}</span>
                {liveState && (
                  <span className="font-mono text-[11px]" style={{ color: liveState === 'FAILED' ? '#f43f5e' : liveState === 'WORKING' ? agent.accent : '#64748b' }}>
                    {t(`office.states.${liveState}`)}
                  </span>
                )}
              </div>
              {!!liveTokens?.total && (
                <div className="font-mono text-[11px] text-slate-400 mb-1">
                  {t('office.tokens', {
                    total: liveTokens.total,
                    prompt: liveTokens.prompt || 0,
                    completion: liveTokens.completion || 0,
                  })}
                </div>
              )}
              <div className="panel-inset h-28 overflow-y-auto px-2 py-1.5 kanban-scroll" style={{ background: '#070b13' }}>
                {liveTail.length === 0 ? (
                  <code className="font-mono text-[12px] text-slate-700">{t('office.awaiting')}</code>
                ) : (
                  liveTail.slice(-8).map((line, i) => (
                    <code
                      key={i}
                      className="block font-mono text-[12px] leading-tight whitespace-pre-wrap break-all"
                      style={{ color: line.startsWith('[exit') ? '#f43f5e' : `${agent.accent}cc` }}
                    >
                      {line}
                    </code>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
