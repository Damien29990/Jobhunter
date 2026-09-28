// Clara post-application follow-up: user marks status + employer updates.

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileCheck, LoaderCircle } from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'

const STATUSES = [
  'READY',
  'APPLIED',
  'AWAITING',
  'EMPLOYER_UPDATE',
  'INTERVIEW',
  'OFFER',
  'REJECTED',
  'WITHDRAWN',
]

export default function ApplicationFollowUp({ job, onChanged }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState(job.application_status || 'READY')
  const [note, setNote] = useState(job.application_note || '')
  const [employer, setEmployer] = useState(job.employer_update_note || '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setStatus(job.application_status || 'READY')
    setNote(job.application_note || '')
    setEmployer(job.employer_update_note || '')
  }, [job.id, job.application_status, job.application_note, job.employer_update_note])

  async function save(patch) {
    setSaving(true)
    setErr(null)
    try {
      await api.setJobFollowUp(job.id, patch)
      onChanged?.()
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="panel-inset p-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <FileCheck size={14} className="text-rose-retro shrink-0" />
        <span className="font-pixel text-[11px] text-rose-retro">{t('clara.followUpTitle')}</span>
      </div>
      <p className="font-mono text-[11px] text-slate-500 leading-4">{t('clara.followUpHint')}</p>
      <label className="block">
        <span className="font-mono text-[11px] text-slate-500">{t('clara.followUpStatus')}</span>
        <select
          value={status}
          disabled={saving}
          onChange={(e) => {
            const next = e.target.value
            setStatus(next)
            save({ application_status: next })
          }}
          className="mt-1 w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200"
        >
          {STATUSES.map((key) => (
            <option key={key} value={key}>{t(`clara.status.${key}`)}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="font-mono text-[11px] text-slate-500">{t('clara.followUpNote')}</span>
        <textarea
          value={note}
          rows={2}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => {
            if (note !== (job.application_note || '')) save({ application_note: note })
          }}
          className="mt-1 w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 resize-y"
        />
      </label>
      <label className="block">
        <span className="font-mono text-[11px] text-slate-500">{t('clara.employerUpdate')}</span>
        <textarea
          value={employer}
          rows={2}
          placeholder={t('clara.employerUpdatePlaceholder')}
          onChange={(e) => setEmployer(e.target.value)}
          onBlur={() => {
            if (employer !== (job.employer_update_note || '')) {
              save({ employer_update_note: employer })
            }
          }}
          className="mt-1 w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 resize-y"
        />
      </label>
      <div className="font-mono text-[10px] text-slate-600 space-y-0.5">
        {job.application_status_at && (
          <div>{t('clara.statusAt')}: {formatHKDateTime(job.application_status_at)}</div>
        )}
        {job.employer_update_at && (
          <div>{t('clara.employerAt')}: {formatHKDateTime(job.employer_update_at)}</div>
        )}
        {job.follow_up_needed && (
          <div className="text-amber-retro">{t('clara.followUpNeeded')}</div>
        )}
      </div>
      {saving && (
        <div className="font-mono text-[11px] text-slate-500 flex items-center gap-1">
            <LoaderCircle size={12} className="animate-spin" /> {t('clara.saving')}
        </div>
      )}
      {err && <div className="font-mono text-[11px] text-rose-retro">{err}</div>}
    </div>
  )
}
