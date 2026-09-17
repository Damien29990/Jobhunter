// AgentLogConsole.jsx — terminal-style widget that logs all 4 agents'
// activity. Reads the persistent agent_activity.txt log (via /api/agents/log)
// and renders it with:
//   - shortened timestamps (HH:MM:SS, not full ISO 8601)
//   - level-classified colors (ERROR red, WARN amber, INFO per-agent accent, SYSTEM amber)
// so errors/warnings stand out across all agents.

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Terminal } from 'lucide-react'
import { AGENTS } from '../lib/agents'

const STATE_COLOR = {
  IDLE: '#64748b',
  WORKING: '#10b981',
  FAILED: '#f43f5e',
}

// Level → color. ERROR/WARN are fixed so they stand out across every agent;
// INFO falls back to the agent's accent; SYSTEM (START/EXIT) is amber.
const LEVEL_COLOR = {
  ERROR: '#f43f5e',
  WARN: '#fbbf24',
  START: '#fbbf24',
  EXIT: '#fbbf24',
  INFO: null, // sentinel: use agent accent
}
const DIM_TS = '#475569'   // dim timestamp
const DIM_SRC = '#64748b'  // dim source tag when neutral
const NEUTRAL = '#94a3b8'

const CHAR_COLOR = Object.fromEntries(AGENTS.map((a) => [a.name, a.accent]))

// Parse ``[<ts>] [<SOURCE>] [<LEVEL>] <message>`` and shorten ts to HH:MM:SS.
function parseLogLine(line) {
  const m = line.match(/^\[([^\]]+)\]\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*(.*)$/)
  if (!m) return null
  const [, ts, source, level, message] = m
  // "2026-09-10T21:35:00+08:00" -> "21:35:00"
  const shortTs = ts.length >= 19 ? ts.slice(11, 19) : ts
  return { ts: shortTs, source, level, message: (message || '').trim() }
}

// One colored, shortened log line.
function LogLine({ line, accent }) {
  const p = parseLogLine(line)
  if (!p) {
    // raw line (e.g. "[exit code 0]" from the in-memory tail) — color by content
    const isExit = line.startsWith('[exit')
    return (
      <code className="block font-mono text-[12px] leading-5 whitespace-pre-wrap break-words" style={{ color: isExit ? '#fbbf24' : NEUTRAL }}>
        {line}
      </code>
    )
  }
  const levelColor = LEVEL_COLOR[p.level] ?? (accent || NEUTRAL)
  const srcColor = CHAR_COLOR[p.source] || DIM_SRC
  return (
    <code className="block font-mono text-[12px] leading-5 whitespace-pre-wrap break-words">
      <span style={{ color: DIM_TS }}>{p.ts}</span>{' '}
      <span style={{ color: srcColor }}>[{p.source}]</span>{' '}
      <span style={{ color: p.level === 'INFO' ? srcColor : (levelColor || NEUTRAL) }}>[{p.level}]</span>{' '}
      <span style={{ color: levelColor ?? accent ?? NEUTRAL }}>{p.message}</span>
    </code>
  )
}

function UnifiedPanel({ agentLog }) {
  const { t } = useTranslation()
  const scrollRef = useRef(null)
  const lines = agentLog?.lines || []

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines.length])

  return (
    <div className="panel-inset flex flex-col h-[min(50vh,420px)]" style={{ borderColor: '#1e293b' }}>
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-ink-700 shrink-0">
        <span className="font-pixel text-[12px] text-amber-retro">{t('logs.unified')}</span>
        <span className="font-mono text-[11px] text-slate-500">
          {agentLog?.total_lines != null ? `${agentLog.total_lines} lines` : ''}
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-2 py-1.5 kanban-scroll" style={{ background: '#070b13' }}>
        {lines.length === 0 ? (
          <code className="font-mono text-[12px] text-slate-700">{t('logs.empty')}</code>
        ) : (
          lines.map((line, i) => <LogLine key={i} line={line} />)
        )}
      </div>
    </div>
  )
}

function AgentPanel({ agent, status, agentLog }) {
  const { t } = useTranslation()
  const scrollRef = useRef(null)
  const state = status?.state || 'IDLE'
  const accent = agent.accent

  const allLines = agentLog?.lines || []
  const lines = allLines.filter((line) => {
    const m = line.match(/^\[[^\]]+\]\s*\[([^\]]+)\]/)
    return m && m[1] === agent.name
  })

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines.length])

  return (
    <div className="panel-inset flex flex-col h-[min(50vh,420px)]" style={{ borderColor: state === 'WORKING' ? accent : '#1e293b' }}>
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-ink-700 shrink-0">
        <span className="font-pixel text-[12px]" style={{ color: accent }}>{agent.name}</span>
        <span className="flex items-center gap-1 font-mono text-[11px]" style={{ color: STATE_COLOR[state] }}>
          <span className="inline-block w-2 h-2" style={{ background: STATE_COLOR[state] }} />
          {t(`office.states.${state}`)}
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-2 py-1.5 kanban-scroll" style={{ background: '#070b13' }}>
        {lines.length === 0 ? (
          <code className="font-mono text-[12px] text-slate-700">{t('logs.empty')}</code>
        ) : (
          lines.map((line, i) => <LogLine key={i} line={line} accent={accent} />)
        )}
      </div>
    </div>
  )
}

export default function AgentLogConsole({ agentStatus, agentLog }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(true)
  const [view, setView] = useState('perAgent')

  const Toggle = ({ value, label }) => (
    <button
      onClick={() => setView(value)}
      className="font-pixel text-[11px] px-2 py-1 panel-inset"
      style={{
        color: view === value ? '#fbbf24' : '#64748b',
        borderColor: view === value ? '#fbbf24' : '#1e293b',
      }}
    >
      {label}
    </button>
  )

  return (
    <section className="panel p-3 mt-3">
      <div className="flex items-center justify-between gap-2 w-full">
        <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-2 text-left">
          {open ? <ChevronDown size={16} className="text-amber-retro" /> : <ChevronRight size={16} className="text-amber-retro" />}
          <Terminal size={16} className="text-amber-retro" />
          <h2 className="font-pixel text-[12px] text-amber-retro">{t('logs.title')}</h2>
          <span className="font-mono text-[11px] text-slate-500">{t('logs.subtitle')}</span>
        </button>
        <div className="flex items-center gap-1 shrink-0">
          <Toggle value="perAgent" label={t('logs.perAgent')} />
          <Toggle value="unified" label={t('logs.unified')} />
        </div>
      </div>

      {open && (
        view === 'unified' ? (
          <div className="mt-3"><UnifiedPanel agentLog={agentLog} /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 mt-3">
            {AGENTS.map((agent) => (
              <AgentPanel key={agent.key} agent={agent} status={agentStatus?.[agent.key]} agentLog={agentLog} />
            ))}
          </div>
        )
      )}
    </section>
  )
}
