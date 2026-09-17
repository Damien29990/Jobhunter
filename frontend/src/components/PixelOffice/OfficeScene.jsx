// OfficeScene.jsx — top-down 16-bit office floor with 4 interactive agent desks.
// Integrates the former QuestBar functions: per-agent step label, done
// indicator, and a run/stop button (so the desk is self-contained — you can
// run/stop and see progress without opening the tutorial modal).
// Clicking the desk body still opens the tutorial modal.

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CircleCheck, Play, Square, FastForward, LoaderCircle } from 'lucide-react'
import PixelAgent from './PixelAgent'
import OfficeFurniture from './OfficeFurniture'
import { api } from '../../lib/api'
import { OFFICE_AGENTS, QUEST_STEPS } from '../../lib/agents'
import { useAgentMovement } from '../../lib/useAgentMovement'
import { TILE_SIZE, GRID_W, GRID_H, DESK_POSITIONS, gridToPx } from '../../lib/officeGrid'

function StatusLabel({ state, accent }) {
  const { t } = useTranslation()
  const map = {
    IDLE: { text: t('office.states.IDLE'), color: '#64748b', dot: '#64748b' },
    WORKING: { text: t('office.states.WORKING'), color: accent, dot: accent, pulse: true },
    FAILED: { text: t('office.states.FAILED'), color: '#f43f5e', dot: '#f43f5e' },
  }
  const s = map[state] || map.IDLE
  return (
    <div className="flex items-center gap-1.5 font-mono text-[12px]" style={{ color: s.color }}>
      <span
        className={`inline-block w-2.5 h-2.5 ${s.pulse ? 'animate-blink' : ''}`}
        style={{ background: s.dot }}
      />
      {s.text}
    </div>
  )
}

function Desk({ agent, status, step, done, onClick, onRun, onStop, t }) {
  const state = status?.state || 'IDLE'
  const accent = agent.accent
  const working = state === 'WORKING'
  const lastLine = status?.last_lines?.slice(-1)[0] || ''

  return (
    <div
      onClick={onClick}
      className="group relative panel p-3 cursor-pointer transition-transform hover:-translate-y-0.5 hover:shadow-glow-amber"
      style={{ borderColor: working ? accent : '#1e293b' }}
    >
      {/* header: name + done + status */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className="font-pixel text-[12px]" style={{ color: accent }}>{agent.name}</span>
          {done && <CircleCheck size={14} style={{ color: accent }} />}
        </div>
        <StatusLabel state={state} accent={accent} />
      </div>

      {/* step label (integrated from QuestBar) */}
      {step && (
        <div className="font-mono text-[11px] text-slate-300 leading-tight mb-0.5">{t(step.labelKey)}</div>
      )}
      <div className="font-mono text-[11px] text-slate-500 mb-2">{t(`agents.${agent.key}.role`)}</div>
      {(status?.total_tokens > 0) && (
        <div className="font-mono text-[11px] text-slate-400 mb-2">
          {t('office.tokens', {
            total: status.total_tokens,
            prompt: status.prompt_tokens || 0,
            completion: status.completion_tokens || 0,
          })}
        </div>
      )}

      {/* the character */}
      <div className="flex justify-center my-2">
        <PixelAgent agentKey={agent.key} state={state} size={120} />
      </div>

      {/* live tail */}
      <div className="panel-inset h-14 overflow-hidden px-2 py-1 mt-2">
        <code className="font-mono text-[12px] text-emerald-retro/80 leading-5 block line-clamp-2 break-words">
          {lastLine || t('office.awaiting')}
        </code>
      </div>

      {/* run / stop button (integrated from QuestBar) */}
      <button
        onClick={(e) => { e.stopPropagation(); working ? onStop?.() : onRun?.() }}
        className="mt-2 w-full panel px-2 py-1.5 flex items-center justify-center gap-1.5 font-mono text-[12px] transition-colors"
        style={{
          color: working ? '#f43f5e' : accent,
          borderColor: working ? '#f43f5e' : '#334155',
        }}
      >
        {working ? <><Square size={13} /> {t('quest.stop')}</> : <><Play size={13} /> {t('quest.run')}</>}
      </button>

      {/* hover hint */}
      <div className="absolute -top-7 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <span className="font-mono text-[10px] bg-ink-700 border border-ink-600 px-2 py-0.5 text-amber-retro">
          {t('office.clickToTalk')}
        </span>
      </div>
    </div>
  )
}

function effectiveAgentStatus(status, pipeline) {
  if (!status) return status
  const step = pipeline?.state === 'RUNNING' ? pipeline.step : ''
  if (!step || status[step]?.state === 'WORKING') return status
  return {
    ...status,
    [step]: { ...(status[step] || {}), state: 'WORKING' },
  }
}

export default function OfficeScene({
  onAgentClick, onRunAgent, onStopAgent, funnel, tick, agentStatus: parentStatus, onActivity,
}) {
  const { t } = useTranslation()
  const [status, setStatus] = useState(parentStatus || null)
  const [pipeline, setPipeline] = useState(null)
  const [scheduler, setScheduler] = useState(null)

  useEffect(() => {
    if (parentStatus) setStatus(parentStatus)
  }, [parentStatus])

  const liveStatus = effectiveAgentStatus(status, pipeline)
  const anyoneWorking = Object.values(liveStatus || {}).some((a) => a?.state === 'WORKING')
    || pipeline?.state === 'RUNNING'
    || !!scheduler?.pipeline_running

  useEffect(() => {
    let active = true
    async function poll() {
      try {
        const [s, p, sched] = await Promise.all([
          api.agentStatus(),
          api.pipelineStatus().catch(() => null),
          api.schedulerStatus?.().catch(() => null),
        ])
        if (!active) return
        setStatus(s)
        setPipeline(p)
        setScheduler(sched)
      } catch { /* backend not up yet */ }
    }
    poll()
    const id = setInterval(poll, anyoneWorking ? 1000 : 2500)
    return () => { active = false; clearInterval(id) }
  }, [tick, anyoneWorking])

  // Agent movement — A* pathfinding driven by agentStatus
  const { bindAgent, movingMap, posRef } = useAgentMovement(liveStatus)

  const floorRef = useRef(null)
  const [floorScale, setFloorScale] = useState(1)
  useEffect(() => {
    const el = floorRef.current
    if (!el) return
    const nativeW = GRID_W * TILE_SIZE
    const apply = () => {
      const w = el.clientWidth
      setFloorScale(w > 0 ? w / nativeW : 1)
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // done state per agent (mirrors the former QuestBar logic)
  const doneFor = {
    milo: (funnel?.found || 0) > 0 || (funnel?.score_ge_80 || 0) > 0,
    rex: (funnel?.found || 0) > 0,
    dana: (funnel?.vetted_proceed || 0) > 0,
    leo: (funnel?.cv_generated || 0) > 0,
    clara: (funnel?.application_ready || 0) > 0,
  }
  const stepFor = Object.fromEntries(QUEST_STEPS.map((s) => [s.agent, s]))

  const pipelineRunning = pipeline?.state === 'RUNNING'
  async function togglePipeline() {
    if (pipelineRunning) {
      await api.stopPipeline().catch(() => {})
    } else {
      await api.runPipeline({ candidate_id: undefined }).catch(() => {})
    }
    onActivity?.()
  }

  async function toggleScheduler() {
    if (scheduler?.running) {
      await api.schedulerStop?.().catch(() => {})
    } else {
      await api.schedulerStart?.().catch(() => {})
    }
    onActivity?.()
  }

  async function runSchedulerNow() {
    await api.schedulerRunNow?.().catch(() => {})
    onActivity?.()
  }

  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b-2 border-ink-700">
        <h2 className="font-pixel text-[12px] text-amber-retro">{t('office.title')}</h2>
        <div className="flex items-center gap-2">
          {/* Scheduler controls */}
          {scheduler && (
            <div className="flex items-center gap-1.5">
              {scheduler.pipeline_running && (
                <span className="font-mono text-[11px] text-emerald-retro flex items-center gap-1">
                  <LoaderCircle size={11} className="animate-spin" /> Auto
                </span>
              )}
              <button
                onClick={toggleScheduler}
                className="font-pixel text-[10px] px-2 py-1 panel flex items-center gap-1"
                style={{
                  color: scheduler.running ? '#f43f5e' : '#a78bfa',
                  borderColor: scheduler.running ? '#f43f5e' : '#a78bfa',
                }}
              >
                {scheduler.running ? '⏸ Auto' : '⏰ Auto'}
              </button>
              {!scheduler.running && (
                <button
                  onClick={runSchedulerNow}
                  className="font-pixel text-[10px] px-2 py-1 panel flex items-center gap-1 text-emerald-retro"
                >
                  ▶ Now
                </button>
              )}
            </div>
          )}
          {pipeline?.step && pipelineRunning && (
            <span className="font-mono text-[11px] text-emerald-retro flex items-center gap-1">
              <LoaderCircle size={12} className="animate-spin" /> {t(`agents.${pipeline.step}.role`) || pipeline.step}
            </span>
          )}
          <button
            onClick={togglePipeline}
            disabled={!!pipelineRunning}
            className="font-pixel text-[11px] px-2.5 py-1.5 panel flex items-center gap-1.5 disabled:opacity-50"
            style={{ color: pipelineRunning ? '#f43f5e' : '#10b981', borderColor: pipelineRunning ? '#f43f5e' : '#10b981' }}
          >
            {pipelineRunning ? <><Square size={13} /> {t('pipeline.stop')}</> : <><FastForward size={13} /> {t('pipeline.run')}</>}
          </button>
          <span className="font-mono text-[10px] text-slate-500">{t('office.live')}</span>
        </div>
      </div>

      <div className="px-3 pt-3">
        <div
          ref={floorRef}
          className="relative w-full overflow-hidden panel-inset"
          style={{ height: GRID_H * TILE_SIZE * floorScale }}
        >
        <div
          className="relative pixelated origin-top-left"
          style={{
            width: GRID_W * TILE_SIZE,
            height: GRID_H * TILE_SIZE,
            transform: `scale(${floorScale})`,
            transformOrigin: 'top left',
            backgroundColor: '#0b1120',
            backgroundImage:
              'linear-gradient(#0f172a 1px, transparent 1px), linear-gradient(90deg, #0f172a 1px, transparent 1px)',
            backgroundSize: `${TILE_SIZE}px ${TILE_SIZE}px`,
          }}
        >
          <OfficeFurniture />

          {OFFICE_AGENTS.map((agent) => {
            const pos = posRef.current[agent.key] || gridToPx(DESK_POSITIONS[agent.key])
            const moving = !!movingMap[agent.key]
            const state = liveStatus?.[agent.key]?.state || 'IDLE'
            return (
              <div
                key={agent.key}
                ref={bindAgent(agent.key)}
                className="absolute cursor-pointer transition-none"
                style={{
                  top: 0,
                  left: 0,
                  transform: `translate(${pos.x}px, ${pos.y}px)`,
                  willChange: moving || state === 'WORKING' ? 'transform' : 'auto',
                  zIndex: 2,
                }}
                onClick={() => onAgentClick(agent.key)}
              >
                <PixelAgent
                  agentKey={agent.key}
                  state={state}
                  size={TILE_SIZE * 1.5}
                  moving={moving || state === 'WORKING'}
                  embedded={false}
                />
                <div
                  className="absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap font-pixel text-[8px]"
                  style={{ color: agent.accent }}
                >
                  {agent.name}
                </div>
              </div>
            )
          })}
        </div>
        </div>
      </div>

      <div
        className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3"
      >
        {OFFICE_AGENTS.map((agent) => (
          <Desk
            key={agent.key}
            agent={agent}
            status={liveStatus?.[agent.key]}
            step={stepFor[agent.key]}
            done={doneFor[agent.key]}
            onClick={() => onAgentClick(agent.key)}
            onRun={() => onRunAgent?.(agent.key)}
            onStop={() => onStopAgent?.(agent.key)}
            t={t}
          />
        ))}
      </div>
    </section>
  )
}
