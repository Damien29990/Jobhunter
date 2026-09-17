// API client for the Jobhunter dashboard backend.
// All timestamps arrive as Asia/Hong_Kong ISO 8601 — display as-is, do not re-zone.

const BASE = import.meta.env.VITE_API_URL || '/api'

async function getJSON(path, params) {
  const qs = params
    ? '?' + new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
      ).toString()
    : ''
  const res = await fetch(`${BASE}${path}${qs}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    let msg = `${res.status}`
    try { msg = (await res.json()).detail || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json()
}

async function postJSON(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })
  const data = await res.json().catch(() => ({ ok: res.ok }))
  if (!res.ok) {
    const msg = data.detail || `${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

async function postForm(path, formData) {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: formData })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = data.detail || `${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export const api = {
  health: () => getJSON('/health'),

  // Milo — CV intake, chat, history
  importCv: (candidateId, cvText) =>
    postJSON('/candidates/import-cv', { candidate_id: candidateId || 'default', cv_text: cvText }),
  importCvFile: (candidateId, file) => {
    const fd = new FormData()
    fd.append('candidate_id', candidateId || 'default')
    fd.append('file', file)
    return postForm('/candidates/import-cv', fd)
  },
  miloChat: (candidateId, message, files) => {
    const id = candidateId || 'default'
    if (files && files.length) {
      const fd = new FormData()
      fd.append('candidate_id', id)
      fd.append('message', message || '')
      for (const f of files) fd.append('files', f)
      return postForm('/milo/chat', fd)
    }
    return postJSON('/milo/chat', { candidate_id: id, message })
  },
  miloHistory: (candidateId) => getJSON(`/milo/history/${candidateId || 'default'}`),
  miloSummary: (candidateId) => getJSON(`/milo/summary/${candidateId || 'default'}`),
  telegramBot: () => getJSON('/telegram/bot'),

  candidates: () => getJSON('/candidates'),
  candidate: (id) => getJSON(`/candidates/${id}`),
  saveCandidate: (id, profile) =>
    fetch(`${BASE}/candidates/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    }).then((r) => (r.ok ? r.json() : r.json().then((e) => Promise.reject(e)))),
  createCandidate: (id, name, location) =>
    fetch(`${BASE}/candidates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, name, location }),
    }).then((r) => (r.ok ? r.json() : r.json().then((e) => Promise.reject(e)))),

  jobs: (params) => getJSON('/jobs', params),
  job: (id) => getJSON(`/jobs/${id}`),
  jobsSummary: (stage) => getJSON('/jobs/summary', stage ? { stage } : undefined),
  setJobExpired: (id, expired) =>
    fetch(`${BASE}/jobs/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expired }),
    }).then((r) => (r.ok ? r.json() : r.json().then((e) => Promise.reject(e)))),
  setJobUnconsiderable: (id, unconsiderable) =>
    fetch(`${BASE}/jobs/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ unconsiderable }),
    }).then((r) => (r.ok ? r.json() : r.json().then((e) => Promise.reject(e)))),
  jobsShelf: () => getJSON('/jobs/shelf'),
  checkJob: (id) => postJSON(`/jobs/${id}/check`),
  jobDossier: (id) => getJSON(`/jobs/${id}/dossier`),
  jobCvUrl: (id, opts) => {
    const params = new URLSearchParams()
    if (opts?.candidateId) params.set('candidate_id', opts.candidateId)
    if (opts?.download) params.set('download', '1')
    if (opts?.v != null) params.set('v', String(opts.v))
    const qs = params.toString()
    return `${BASE}/jobs/${id}/cv${qs ? `?${qs}` : ''}`
  },
  jobChecklistUrl: (id) => `${BASE}/jobs/${id}/checklist`,
  jobResearchUrl: (id) => `${BASE}/jobs/${id}/research`,

  dossiers: (verdict) => getJSON('/dossiers', verdict ? { verdict } : undefined),
  dossier: (name) => getJSON(`/dossiers/${encodeURIComponent(name)}`),
  dossierMarkdownUrl: (name) => `${BASE}/dossiers/${encodeURIComponent(name)}/markdown`,

  funnel: () => getJSON('/stats/funnel'),
  gates: () => getJSON('/gates'),

  agentStatus: () => getJSON('/agents/status'),
  runPipeline: (body) => postJSON('/pipeline/run', body),
  stopPipeline: () => postJSON('/pipeline/stop', {}),
  pipelineStatus: () => getJSON('/pipeline/status'),
  agentLog: (tail, source) => {
    const params = {}
    if (tail) params.tail = tail
    if (source) params.source = source
    return getJSON('/agents/log', Object.keys(params).length ? params : undefined)
  },
  runAgent: (key, body) => postJSON(`/agents/${key}/run`, body),
  stopAgent: (key) => postJSON(`/agents/${key}/stop`, {}),

  suggestions: (candidateId) => getJSON('/suggestions', candidateId ? { candidate_id: candidateId } : undefined),
  skillCategories: () => getJSON('/skill-categories'),
  refreshSkillCategories: () => postJSON('/skill-categories/refresh'),
  skillSuggestions: (candidateId, category) => getJSON('/skills/suggest', { candidate_id: candidateId, category }),

  agentRoute: {
    milo: 'intake',
    rex: 'scout',
    dana: 'diligence',
    leo: 'cv',
    clara: 'assembler',
  },

  // Scheduler endpoints
  schedulerStatus: () => getJSON('/scheduler/status'),
  schedulerStart: () => postJSON('/scheduler/start', {}),
  schedulerStop: () => postJSON('/scheduler/stop', {}),
  schedulerRunNow: () => postJSON('/scheduler/run-now', {}),
  schedulerConfigure: (hours) => postJSON('/scheduler/configure', { hours }),
}

// --- Time helpers (Asia/Hong_Kong, display as-is) ---
export function formatHK(iso, opts) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-HK', { timeZone: 'Asia/Hong_Kong', ...opts })
}
export function formatHKDate(iso) {
  return formatHK(iso, { year: 'numeric', month: 'short', day: 'numeric' })
}
export function formatHKTime(iso) {
  return formatHK(iso, { hour: '2-digit', minute: '2-digit', hour12: false })
}
// YYYY-MM-DD HH:MM in Asia/Hong_Kong — the format the dashboard shows on every job card.
// Built from parts so the separators are always '-' and ':' regardless of locale quirks
// (the zh-HK locale would otherwise render '2026/09/07').
export function formatHKDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Hong_Kong',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(d)
  const g = (t) => parts.find((p) => p.type === t)?.value || ''
  return `${g('year')}-${g('month')}-${g('day')} ${g('hour')}:${g('minute')}`
}
export function relativeFromHK(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diff / 60000)
  if (mins < 0) return 'just now'
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  return `${days}d ago`
}
