// App.jsx — Jobhunter Pixel Office Dashboard root.
// Adds a backend-offline banner: if /api/health is unreachable, the banner
// shows the exact command to start FastAPI. This is the most common reason
// "talking to an agent" (clicking RUN) fails — the backend isn't running.

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TriangleAlert, CircleCheck, X } from 'lucide-react'
import Header from './components/Header'
import OfficeScene from './components/PixelOffice/OfficeScene'
import PipelineKanban from './components/PipelineKanban'
import DetailDrawer from './components/DetailDrawer'
import TutorialModal from './components/TutorialModal'
import AgentLogConsole from './components/AgentLogConsole'
import AgentUsagePanel from './components/AgentUsagePanel'
import ProfileEditor from './components/ProfileEditor'
import MiloChat from './components/MiloChat'
import PipelineFinishOverview from './components/PipelineFinishOverview'
import { api } from './lib/api'

function searchParams() {
  try {
    return new URLSearchParams(window.location.search)
  } catch {
    return new URLSearchParams()
  }
}

export default function App() {
  const { t } = useTranslation()
  const miloPopup = searchParams().get('milo') === '1'
  const [candidateId, setCandidateId] = useState(() => searchParams().get('candidate') || null)
  const [funnel, setFunnel] = useState(null)
  const [agentStatus, setAgentStatus] = useState(null)
  const [agentLog, setAgentLog] = useState(null)
  const [agentRuns, setAgentRuns] = useState(null)
  const [usageSummary, setUsageSummary] = useState(null)
  const [selectedJobId, setSelectedJobId] = useState(null)
  const [jobsByStage, setJobsByStage] = useState({})
  const [navStage, setNavStage] = useState(null)
  const [tutorialAgent, setTutorialAgent] = useState(null)
  const [tick, setTick] = useState(0)
  const [backendOnline, setBackendOnline] = useState(null) // null = unknown
  const [dismissedBanner, setDismissedBanner] = useState(false)
  const [editingProfile, setEditingProfile] = useState(null) // null | candidateId | 'new'
  const [talkingMilo, setTalkingMilo] = useState(false)
  const [finishOverview, setFinishOverview] = useState(null)
  const [pipelineBusy, setPipelineBusy] = useState(false)
  const pipelineBusyRef = useRef(false)

  const agentsBusy = Object.values(agentStatus || {}).some((a) => a?.state === 'WORKING')

  useEffect(() => {
    let active = true
    async function poll() {
      try {
        const [h, f, s, l, r, u, p, sched] = await Promise.all([
          api.health(),
          api.funnel().catch(() => null),
          api.agentStatus().catch(() => null),
          api.agentLog().catch(() => null),
          api.agentRuns(40).catch(() => null),
          api.agentRunsSummary().catch(() => null),
          api.pipelineStatus().catch(() => null),
          api.schedulerStatus?.().catch(() => null),
        ])
        if (!active) return
        setBackendOnline(true)
        setFunnel(f)
        setAgentStatus(s)
        setAgentLog(l)
        setAgentRuns(r)
        setUsageSummary(u)
        const busy = p?.state === 'RUNNING' || !!sched?.pipeline_running
        if (pipelineBusyRef.current && !busy) {
          const overview = await api.pipelineApplyOverview().catch(() => null)
          if (active && overview) setFinishOverview(overview)
        }
        pipelineBusyRef.current = busy
        setPipelineBusy(busy)
      } catch {
        if (active) setBackendOnline(false)
      }
    }
    poll()
    const id = setInterval(poll, agentsBusy || pipelineBusy ? 1000 : 4000)
    return () => { active = false; clearInterval(id) }
  }, [tick, agentsBusy, pipelineBusy])

  const handleRunAgent = useCallback((agentKey) => setTutorialAgent(agentKey), [])
  const handleStopAgent = useCallback(async (agentKey) => {
    try { await api.stopAgent(agentKey) } catch { /* ignore */ }
    setTimeout(() => setTick((x) => x + 1), 400)
  }, [])
  const handleStarted = useCallback(() => {
    setTick((x) => x + 1)
    setTimeout(() => setTick((x) => x + 1), 400)
  }, [])

  const handleSelectJob = useCallback((job, stage) => {
    if (!job?.id) return
    setSelectedJobId(job.id)
    if (stage) setNavStage(stage)
  }, [])

  const showBanner = backendOnline === false && !dismissedBanner

  if (miloPopup) {
    return (
      <MiloChat
        candidateId={candidateId}
        variant="popup"
        open
        onClose={() => window.close()}
      />
    )
  }

  return (
    <div className="min-h-screen overflow-x-hidden">
      <div className="px-4 pt-4 max-w-[1400px] mx-auto">
      <Header
        funnel={funnel}
        candidateId={candidateId}
        onCandidateChange={setCandidateId}
        onEditProfile={(id) => setEditingProfile(id)}
        onNewPerson={() => setEditingProfile('new')}
        tick={tick}
      />

      {showBanner && (
        <div className="panel p-3 mb-3 border-rose-retro" style={{ borderColor: '#f43f5e' }}>
          <div className="flex items-start gap-3">
            <TriangleAlert size={18} className="text-rose-retro mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="font-pixel text-[12px] text-rose-retro mb-1">{t('backend.offlineTitle')}</div>
              <div className="font-mono text-[12px] text-slate-300 mb-2">{t('backend.offlineMsg')}</div>
              <code className="font-mono text-[12px] text-amber-retro block panel-inset p-2 break-all">
                {t('backend.offlineCmd')}
              </code>
              <div className="font-mono text-[11px] text-slate-500 mt-2">
                {t('office.awaiting')} — {t('app.subtitle')}
              </div>
            </div>
            <button
              onClick={() => setDismissedBanner(true)}
              className="text-slate-500 hover:text-slate-300 shrink-0"
              title="dismiss"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {backendOnline && (
        <div className="flex items-center gap-1.5 mb-3 font-mono text-[12px] text-emerald-retro">
          <CircleCheck size={14} /> {t('backend.online')}
        </div>
      )}
      </div>

      <div className="px-4 mt-3 mb-3">
        <OfficeScene
          onAgentClick={setTutorialAgent}
          onRunAgent={handleRunAgent}
          onStopAgent={handleStopAgent}
          funnel={funnel}
          tick={tick}
          agentStatus={agentStatus}
          onActivity={handleStarted}
        />
      </div>

      <div className="px-4 max-w-[1400px] mx-auto pb-4">
      <PipelineKanban
        candidateId={candidateId}
        onSelectJob={handleSelectJob}
        onJobOrderChange={setJobsByStage}
        tick={tick}
      />

      <AgentUsagePanel runs={agentRuns} summary={usageSummary} agentStatus={agentStatus} />

      <AgentLogConsole agentStatus={agentStatus} agentLog={agentLog} />

      <footer className="mt-6 mb-2 text-center font-mono text-[11px] text-slate-700">
        {t('app.footer')}
      </footer>
      </div>

      {selectedJobId != null && (
        <DetailDrawer
          jobId={selectedJobId}
          jobsByStage={jobsByStage}
          navStage={navStage}
          candidateId={candidateId}
          agentStatus={agentStatus}
          onClose={() => { setSelectedJobId(null); setNavStage(null) }}
          onSelectJob={handleSelectJob}
          onStageStarted={handleStarted}
        />
      )}

      {finishOverview && (
        <PipelineFinishOverview
          overview={finishOverview}
          onClose={() => setFinishOverview(null)}
          onSelectJob={(job) => {
            if (!job?.id) return
            setSelectedJobId(job.id)
            setNavStage('applied')
            setFinishOverview(null)
          }}
        />
      )}

      {tutorialAgent && (
        <TutorialModal
          agentKey={tutorialAgent}
          candidateId={candidateId}
          onClose={() => setTutorialAgent(null)}
          onStarted={handleStarted}
          agentStatus={agentStatus}
        />
      )}

      {editingProfile && (
        <ProfileEditor
          candidateId={editingProfile === 'new' ? null : editingProfile}
          onClose={() => setEditingProfile(null)}
          onSaved={() => setTick((x) => x + 1)}
        />
      )}

      <MiloChat
        candidateId={candidateId}
        open={talkingMilo}
        onOpen={() => setTalkingMilo(true)}
        onClose={() => setTalkingMilo(false)}
      />
    </div>
  )
}
