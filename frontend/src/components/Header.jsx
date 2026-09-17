// Header.jsx — two-band chrome: brand + primary actions, then KPIs + context.
// Metrics stay inset (not buttons). Context actions share default panel chrome.
// One chromatic primary: Talk to Milo. Telegram keeps its own mark color.

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, Briefcase, FileCheck, FileText, MessageSquare, Search, Pencil, UserPlus } from 'lucide-react'
import ProfileSwitcher from './ProfileSwitcher'
import LanguageSwitcher from './LanguageSwitcher'
import { api } from '../lib/api'

function TelegramIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  )
}

function Kpi({ icon: Icon, label, value, color }) {
  return (
    <div className="panel-inset px-3 py-2 flex items-center gap-2">
      <Icon size={16} style={{ color }} />
      <div>
        <div className="font-mono text-[11px] text-slate-500 leading-none">{label}</div>
        <div className="font-pixel text-[14px] leading-tight" style={{ color }}>{value}</div>
      </div>
    </div>
  )
}

const CONTEXT_BTN = 'panel flex items-center gap-1.5 px-2.5 py-2 text-slate-300 disabled:opacity-40'

export default function Header({ funnel, candidateId, onCandidateChange, onEditProfile, onNewPerson, onTalkMilo }) {
  const { t } = useTranslation()
  const [tg, setTg] = useState(null)

  useEffect(() => {
    let active = true
    api.telegramBot()
      .then((bot) => { if (active) setTg(bot) })
      .catch(() => { if (active) setTg(null) })
    return () => { active = false }
  }, [])

  const tgHref = tg?.tme_url || tg?.tg_url
  const tgLabel = tg?.username ? `@${tg.username}` : null

  return (
    <header className="panel p-3 mb-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="panel-inset w-11 h-11 flex items-center justify-center">
            <span className="font-pixel text-[16px] text-amber-retro">J</span>
          </div>
          <div>
            <h1 className="font-pixel text-[14px] text-amber-retro leading-tight">{t('app.title')}</h1>
            <div className="font-mono text-[11px] text-slate-500">{t('app.subtitle')}</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={onTalkMilo}
            title={t('milo.title')}
            className="panel flex items-center gap-1.5 px-2.5 py-2"
            style={{ color: '#a78bfa', borderColor: '#a78bfa' }}
          >
            <MessageSquare size={16} /> <span className="font-mono text-[12px]">{t('milo.talk')}</span>
          </button>
          {tgHref && (
            <a
              href={tgHref}
              target="_blank"
              rel="noopener noreferrer"
              title={t('telegram.open', { handle: tgLabel || '', id: tg?.bot_id ?? '' })}
              className="panel flex items-center gap-1.5 px-2.5 py-2"
              style={{ color: '#29a9eb', borderColor: '#29a9eb' }}
            >
              <TelegramIcon size={16} />
              <span className="font-mono text-[12px]">{tgLabel || t('telegram.find')}</span>
            </a>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t-2 border-ink-700">
        <div className="flex flex-wrap items-center gap-2">
          <Kpi icon={Search} label={t('kpi.found')} value={funnel?.found ?? '—'} color="#64748b" />
          <Kpi icon={Activity} label={t('kpi.scoreGe80')} value={funnel?.score_ge_80 ?? '—'} color="#06b6d4" />
          <Kpi icon={Briefcase} label={t('kpi.proceed')} value={funnel?.vetted_proceed ?? '—'} color="#10b981" />
          <Kpi icon={FileText} label={t('kpi.cvs')} value={funnel?.cv_generated ?? '—'} color="#f59e0b" />
          <Kpi icon={FileCheck} label={t('kpi.ready')} value={funnel?.application_ready ?? '—'} color="#f43f5e" />
        </div>

        <div className="flex flex-wrap items-center gap-2 md:border-l-2 md:border-ink-600 md:pl-3">
          <LanguageSwitcher />
          <ProfileSwitcher value={candidateId} onChange={onCandidateChange} />
          <button
            onClick={onEditProfile}
            disabled={!candidateId}
            title={t('profile.edit')}
            className={CONTEXT_BTN}
          >
            <Pencil size={16} /> <span className="font-mono text-[12px]">{t('profile.edit')}</span>
          </button>
          <button
            onClick={onNewPerson}
            title={t('profile.newPerson')}
            className={CONTEXT_BTN}
          >
            <UserPlus size={16} /> <span className="font-mono text-[12px]">{t('profile.newPerson')}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
