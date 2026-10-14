// Token + Tavily usage: KPI strip, per-agent rollup, live counters, run history.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { AGENTS } from '../lib/agents'
import { formatHKDateTime } from '../lib/api'

const ACCENT = Object.fromEntries(AGENTS.map((a) => [a.key, a.accent]))
const NAME_TO_KEY = Object.fromEntries(AGENTS.map((a) => [a.name.toLowerCase(), a.key]))

function agentKey(name) {
  return NAME_TO_KEY[String(name || '').toLowerCase()] || String(name || '').toLowerCase()
}

function fmt(n) {
  return Number(n || 0).toLocaleString()
}

function groupRuns(items) {
  const pipelines = []
  const byPipe = new Map()
  for (const row of items) {
    const pid = row.pipeline_id
    if (!pid) continue
    if (!byPipe.has(pid)) byPipe.set(pid, [])
    byPipe.get(pid).push(row)
  }
  for (const [pid, rows] of byPipe) {
    const chronological = [...rows].reverse()
    pipelines.push({
      id: pid,
      started: chronological[0]?.started_at || chronological[0]?.finished_at,
      rows: chronological,
      tokens: rows.reduce((n, r) => n + (r.total_tokens || 0), 0),
      credits: rows.reduce((n, r) => n + (r.tavily_credits_est || 0), 0),
    })
  }
  const solos = items.filter((r) => !r.pipeline_id)
  return { pipelines, solos }
}

function mergeByAgent(byAgent) {
  const map = new Map()
  for (const row of byAgent || []) {
    const key = agentKey(row.agent)
    const prev = map.get(key) || {
      key,
      name: row.agent,
      runs: 0,
      total_tokens: 0,
      tavily_calls: 0,
      tavily_credits_est: 0,
    }
    prev.runs += row.runs || 0
    prev.total_tokens += row.total_tokens || 0
    prev.tavily_calls += row.tavily_calls || 0
    prev.tavily_credits_est += row.tavily_credits_est || 0
    if (!prev.name) prev.name = row.agent
    map.set(key, prev)
  }
  return AGENTS.map((a) => map.get(a.key) || {
    key: a.key,
    name: a.name,
    runs: 0,
    total_tokens: 0,
    tavily_calls: 0,
    tavily_credits_est: 0,
  })
}

function liveRows(agentStatus) {
  if (!agentStatus) return []
  return AGENTS.map((a) => {
    const st = agentStatus[a.key]
    if (!st) return null
    const tokens = st.total_tokens || 0
    const credits = st.tavily_credits_est || 0
    const calls = st.tavily_calls || 0
    const working = st.state === 'WORKING'
    if (!working && tokens === 0 && credits === 0 && calls === 0) return null
    return { ...a, ...st, working }
  }).filter(Boolean)
}

function KpiCard({ label, value, sub }) {
  return (
    <div className="panel-inset px-4 py-3 min-h-[88px]">
      <div className="font-mono text-[12px] text-slate-500">{label}</div>
      <div className="font-mono text-[20px] text-slate-100 mt-1 leading-7 tabular-nums">{value}</div>
      {sub ? <div className="font-mono text-[12px] text-slate-400 mt-1 leading-5">{sub}</div> : null}
    </div>
  )
}

function UsageRow({ row }) {
  const { t } = useTranslation()
  const key = agentKey(row.agent)
  const color = ACCENT[key] || '#94a3b8'
  return (
    <div className="grid grid-cols-1 md:grid-cols-[8.5rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-4 gap-y-1 py-2.5 border-b border-ink-700 last:border-0">
      <div>
        <div className="font-pixel text-[12px]" style={{ color }}>{row.agent}</div>
        <div className="font-mono text-[12px] text-slate-500 mt-1">
          {formatHKDateTime(row.finished_at || row.started_at)}
        </div>
      </div>
      <div className="font-mono text-[12px] text-slate-300 leading-5">
        {t('usage.tokensLine', {
          total: fmt(row.total_tokens),
          prompt: fmt(row.prompt_tokens),
          completion: fmt(row.completion_tokens),
        })}
      </div>
      <div className="font-mono text-[12px] text-slate-300 leading-5">
        {t('usage.tavilyLine', {
          credits: fmt(row.tavily_credits_est),
          calls: fmt(row.tavily_calls),
          search: fmt(row.tavily_search_calls),
          extract: fmt(row.tavily_extract_calls),
        })}
      </div>
    </div>
  )
}

export default function AgentUsagePanel({ runs, summary, agentStatus }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const items = runs?.items || []
  const { pipelines, solos } = groupRuns(items)
  const life = summary?.lifetime
  const week = summary?.week
  const agents = mergeByAgent(summary?.by_agent)
  const live = liveRows(agentStatus)

  return (
    <section id="usage" className="panel p-3 mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full text-left min-w-0"
        aria-expanded={open}
        aria-controls="usage-body"
        title={open ? t('usage.toggleHide') : t('usage.toggleShow')}
      >
        {open
          ? <ChevronDown size={16} className="text-amber-retro shrink-0" />
          : <ChevronRight size={16} className="text-amber-retro shrink-0" />}
        <h2 className="font-pixel text-[12px] text-amber-retro shrink-0">{t('usage.title')}</h2>
        <span className="font-mono text-[12px] text-slate-400 truncate">
          {t('usage.collapsedSum', {
            tokens: fmt(life?.total_tokens),
            credits: fmt(life?.tavily_credits_est),
          })}
        </span>
        {live.some((row) => row.working) ? (
          <span className="font-mono text-[12px] text-amber-retro shrink-0">{t('usage.live')}</span>
        ) : null}
      </button>

      {open && (
      <div id="usage-body" className="mt-3">
      <p className="font-mono text-[12px] text-slate-500 mb-3 leading-5">{t('usage.hint')}</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-3">
        <KpiCard
          label={t('usage.kpiTokens')}
          value={fmt(life?.total_tokens)}
          sub={`${t('usage.lifetime')} · ${t('usage.inOut', {
            prompt: fmt(life?.prompt_tokens),
            completion: fmt(life?.completion_tokens),
          })}`}
        />
        <KpiCard
          label={t('usage.kpiTokensWeek')}
          value={fmt(week?.total_tokens)}
          sub={`${t('usage.week')} · ${t('usage.runsCount', { count: fmt(week?.runs) })}`}
        />
        <KpiCard
          label={t('usage.kpiTavily')}
          value={`≈${fmt(life?.tavily_credits_est)}`}
          sub={`${t('usage.week')} ≈${fmt(week?.tavily_credits_est)}`}
        />
        <KpiCard
          label={t('usage.kpiCalls')}
          value={fmt(life?.tavily_calls)}
          sub={t('usage.searchExtract', {
            search: fmt(life?.tavily_search_calls),
            extract: fmt(life?.tavily_extract_calls),
          })}
        />
      </div>

      <div className="panel-inset px-4 py-3 mb-3">
        <div className="font-mono text-[12px] text-slate-400 mb-2">{t('usage.live')}</div>
        {live.length === 0 ? (
          <div className="font-mono text-[12px] text-slate-500">{t('usage.liveIdle')}</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {live.map((row) => (
              <div key={row.key} className="font-mono text-[12px] text-slate-300 leading-5">
                <span className="font-pixel text-[12px] mr-2" style={{ color: row.accent }}>{row.name}</span>
                {row.working ? (
                  <span className="text-amber-retro mr-2">{t('usage.live')}</span>
                ) : null}
                {t('usage.tokensLine', {
                  total: fmt(row.total_tokens),
                  prompt: fmt(row.prompt_tokens),
                  completion: fmt(row.completion_tokens),
                })}
                {' · '}
                {t('usage.tavilyLine', {
                  credits: fmt(row.tavily_credits_est),
                  calls: fmt(row.tavily_calls),
                  search: fmt(row.tavily_search_calls),
                  extract: fmt(row.tavily_extract_calls),
                })}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel-inset px-4 py-3 mb-3 overflow-x-auto">
        <div className="font-mono text-[12px] text-slate-400 mb-2">{t('usage.byAgent')}</div>
        <table className="w-full min-w-[520px] text-left">
          <thead>
            <tr className="font-mono text-[12px] text-slate-500">
              <th className="font-normal py-1.5 pr-3">{t('usage.colAgent')}</th>
              <th className="font-normal py-1.5 pr-3">{t('usage.colRuns')}</th>
              <th className="font-normal py-1.5 pr-3">{t('usage.colTokens')}</th>
              <th className="font-normal py-1.5 pr-3">{t('usage.colTavily')}</th>
              <th className="font-normal py-1.5">{t('usage.colCalls')}</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((row) => (
              <tr key={row.key} className="border-t border-ink-700">
                <td className="py-2 pr-3 font-pixel text-[12px]" style={{ color: ACCENT[row.key] }}>{row.name}</td>
                <td className="py-2 pr-3 font-mono text-[12px] text-slate-300 tabular-nums">{fmt(row.runs)}</td>
                <td className="py-2 pr-3 font-mono text-[12px] text-slate-300 tabular-nums">{fmt(row.total_tokens)}</td>
                <td className="py-2 pr-3 font-mono text-[12px] text-slate-300 tabular-nums">≈{fmt(row.tavily_credits_est)}</td>
                <td className="py-2 font-mono text-[12px] text-slate-300 tabular-nums">{fmt(row.tavily_calls)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <div className="font-mono text-[12px] text-slate-400 mb-2">{t('usage.history')}</div>
        {items.length === 0 ? (
          <div className="panel-inset px-4 py-6 font-mono text-[12px] text-slate-500 leading-5">
            {t('usage.empty')}
          </div>
        ) : (
          <div className="h-[min(48vh,420px)] overflow-y-auto">
            {pipelines.map((pipe) => (
              <div key={pipe.id} className="panel-inset px-4 py-3 mb-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
                  <div className="font-mono text-[12px] text-slate-400">
                    {t('usage.pipeline')} · {formatHKDateTime(pipe.started)}
                  </div>
                  <div className="font-mono text-[12px] text-slate-300">
                    {t('usage.pipelineSum', { tokens: fmt(pipe.tokens), credits: fmt(pipe.credits) })}
                  </div>
                </div>
                {pipe.rows.map((row) => (
                  <UsageRow key={row.id} row={row} />
                ))}
              </div>
            ))}
            {solos.length > 0 && (
              <div className="panel-inset px-4 py-3">
                <div className="font-mono text-[12px] text-slate-400 mb-2">{t('usage.solo')}</div>
                {solos.map((row) => (
                  <UsageRow key={row.id} row={row} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      </div>
      )}
    </section>
  )
}
