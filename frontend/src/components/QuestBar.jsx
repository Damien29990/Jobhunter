// QuestBar.jsx — gamified pipeline checklist for the active user.

import { useTranslation } from 'react-i18next'
import { CircleCheck, Circle, LoaderCircle } from 'lucide-react'
import { QUEST_STEPS, AGENT_BY_KEY } from '../lib/agents'

export default function QuestBar({ funnel, agentStatus, onRunAgent, onStopAgent }) {
  const { t } = useTranslation()
  const doneFor = {
    rex: (funnel?.found || 0) > 0,
    dana: (funnel?.vetted_proceed || 0) > 0,
    leo: (funnel?.cv_generated || 0) > 0,
    clara: (funnel?.application_ready || 0) > 0,
  }
  const workingFor = (key) => agentStatus?.[key]?.state === 'WORKING'

  return (
    <section className="panel p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="font-pixel text-[10px] text-emerald-retro">{t('quest.title')}</span>
        <span className="font-mono text-[8px] text-slate-500">{t('quest.subtitle')}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {QUEST_STEPS.map((step, i) => {
          const agent = AGENT_BY_KEY[step.agent]
          const done = doneFor[step.agent]
          const working = workingFor(step.agent)
          const accent = agent.accent
          return (
            <div
              key={step.agent}
              className="panel-inset p-2 flex items-start gap-2"
              style={{ borderColor: done ? accent : '#1e293b' }}
            >
              <div className="mt-0.5" style={{ color: done ? accent : '#475569' }}>
                {done ? <CircleCheck size={16} /> : working ? <LoaderCircle size={16} className="animate-spin" /> : <Circle size={16} />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[8px] text-slate-500">{t('quest.step')} {i + 1}</div>
                <div className="font-mono text-[10px] text-slate-200 leading-tight">{t(step.labelKey)}</div>
                <button
                  onClick={() => (working ? onStopAgent?.(step.agent) : onRunAgent?.(step.agent))}
                  className="mt-1 font-mono text-[9px] px-2 py-0.5 border transition-colors"
                  style={{
                    color: working ? '#f43f5e' : accent,
                    borderColor: working ? '#f43f5e' : '#334155',
                  }}
                >
                  {working ? t('quest.stop') : done ? t('quest.rerun') : t('quest.run')}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
