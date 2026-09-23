// ProfileEditor.jsx — full-screen modal to edit a candidate's whole profile
// (config/master_profile.json or config/profiles/{id}.json) and to create a new person.
//
// The dashboard is read-only by default; this editor is the explicit write
// feature the user asked for. It writes ONLY to config/ profile JSON files
// (via PUT/POST /api/candidates) — never to src/agents, templates, or job_agent.db.
// Unknown profile keys round-trip safely (Pydantic extra="allow").

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X, Save, LoaderCircle, UserPlus, AlertCircle, Sparkles, RefreshCw, Plus,
  User, GraduationCap, Wrench, Briefcase, Layers, BadgeCheck, Trophy, Upload,
} from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'
import { ChipInput, LabeledInput, TextArea, RepeatList } from './profileEditorParts'
import { githubProfileUrl, isValidLinkedinUsername, linkedinProfileUrl, websiteUrl } from '../lib/contactLinks'

const TABS = [
  { key: 'basics', labelKey: 'profile.tabs.basics', icon: User },
  { key: 'education', labelKey: 'profile.tabs.education', icon: GraduationCap },
  { key: 'skills', labelKey: 'profile.tabs.skills', icon: Wrench },
  { key: 'experience', labelKey: 'profile.tabs.experience', icon: Briefcase },
  { key: 'projects', labelKey: 'profile.tabs.projects', icon: Layers },
  { key: 'certs', labelKey: 'profile.tabs.certs', icon: BadgeCheck },
  { key: 'awards', labelKey: 'profile.tabs.awards', icon: Trophy },
]

const PROFICIENCY_PRESETS = [
  { value: 'Native', labelKey: 'profile.proficiency.native' },
  { value: 'Fluent', labelKey: 'profile.proficiency.fluent' },
  { value: 'Professional', labelKey: 'profile.proficiency.professional' },
  { value: 'Intermediate', labelKey: 'profile.proficiency.intermediate' },
  { value: 'Basic', labelKey: 'profile.proficiency.basic' },
]

const PROJECT_ROLE_PRESETS = [
  { value: 'Owner', labelKey: 'profile.projectRole.owner' },
  { value: 'Tech lead', labelKey: 'profile.projectRole.techLead' },
  { value: 'Full-stack engineer', labelKey: 'profile.projectRole.fullStack' },
  { value: 'Backend engineer', labelKey: 'profile.projectRole.backend' },
  { value: 'Frontend engineer', labelKey: 'profile.projectRole.frontend' },
  { value: 'Data / ML engineer', labelKey: 'profile.projectRole.dataMl' },
  { value: 'Designer', labelKey: 'profile.projectRole.designer' },
  { value: 'Product manager', labelKey: 'profile.projectRole.product' },
  { value: 'Contributor', labelKey: 'profile.projectRole.contributor' },
  { value: 'Maintainer', labelKey: 'profile.projectRole.maintainer' },
  { value: 'Researcher', labelKey: 'profile.projectRole.researcher' },
]

function matchPresetValue(raw, presets) {
  const text = String(raw || '').trim()
  if (!text) return ''
  const found = presets.find((item) => item.value.toLowerCase() === text.toLowerCase())
  return found ? found.value : text
}

function PresetOrOtherField({
  value,
  onChange,
  t,
  presets,
  labelKey,
  unsetKey,
  otherKey,
  customLabelKey,
  customHintKey,
}) {
  const stored = String(value || '').trim()
  const matched = presets.find((item) => item.value.toLowerCase() === stored.toLowerCase())
  const [otherMode, setOtherMode] = useState(() => Boolean(stored && !matched))
  useEffect(() => {
    if (matched) setOtherMode(false)
  }, [matched])
  const showOther = otherMode || Boolean(stored && !matched)
  const selectValue = showOther ? 'other' : (matched ? matched.value : '')
  const customValue = showOther && !matched ? stored : ''
  return (
    <div className="space-y-2">
      <label className="block">
        <span className="font-mono text-[12px] text-slate-500">{t(labelKey)}</span>
        <select
          value={selectValue}
          onChange={(e) => {
            const next = e.target.value
            if (next === 'other') {
              setOtherMode(true)
              if (matched) onChange('')
            } else {
              setOtherMode(false)
              onChange(next)
            }
          }}
          className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro bg-transparent"
        >
          <option value="">{t(unsetKey)}</option>
          {presets.map((item) => (
            <option key={item.value} value={item.value}>{t(item.labelKey)}</option>
          ))}
          <option value="other">{t(otherKey)}</option>
        </select>
      </label>
      {showOther && (
        <LabeledInput
          label={t(customLabelKey)}
          value={customValue}
          onChange={onChange}
          placeholder={t(customHintKey)}
        />
      )}
    </div>
  )
}

function ProficiencyField({ value, onChange, t }) {
  return (
    <PresetOrOtherField
      value={value}
      onChange={onChange}
      t={t}
      presets={PROFICIENCY_PRESETS}
      labelKey="profile.fields.proficiency"
      unsetKey="profile.proficiency.unset"
      otherKey="profile.proficiency.other"
      customLabelKey="profile.fields.proficiencyCustom"
      customHintKey="profile.fields.proficiencyCustomHint"
    />
  )
}

function ProjectRoleField({ value, onChange, t }) {
  return (
    <PresetOrOtherField
      value={value}
      onChange={onChange}
      t={t}
      presets={PROJECT_ROLE_PRESETS}
      labelKey="profile.fields.role"
      unsetKey="profile.projectRole.unset"
      otherKey="profile.projectRole.other"
      customLabelKey="profile.fields.roleCustom"
      customHintKey="profile.fields.roleCustomHint"
    />
  )
}

const EMPTY_PROFILE = {
  basics: {
    name: '',
    location: 'Hong Kong',
    email: '',
    phone: '',
    address: '',
    website: '',
    github: '',
    linkedin: '',
    target_roles: [],
    min_expected_salary_hkd: null,
    languages: [],
  },
  education: [], technical_skills: {}, experience: [], projects: [], certifications: [],
  languages: [], awards: [],
}

function displayNameFromLinkedin(raw) {
  const slug = String(raw || '').trim().replace(/^@/, '').split('/').filter(Boolean).pop() || ''
  const parts = slug.split(/[-_]+/).filter((p) => p && !/^\d+$/.test(p))
  if (!parts.length) return slug
  return parts.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(' ')
}

function parseLanguageChip(raw) {
  const text = String(raw || '').trim()
  const match = text.match(/^(.*?)\s*\((.+)\)\s*$/)
  if (match) return { name: match[1].trim(), proficiency: matchPresetValue(match[2].trim(), PROFICIENCY_PRESETS) }
  return { name: text, proficiency: '' }
}

function hydrateProfile(payload) {
  const structured = Array.isArray(payload.languages)
    && payload.languages.some((item) => item && typeof item === 'object' && item.name)
  const languages = structured
    ? payload.languages.map((item) => ({
      name: item.name || '',
      proficiency: matchPresetValue(item.proficiency || '', PROFICIENCY_PRESETS),
    }))
    : (payload.basics?.languages || []).map(parseLanguageChip)
  const projects = (payload.projects || []).map((item) => ({
    name: item.name || '',
    role: matchPresetValue(item.role || '', PROJECT_ROLE_PRESETS),
    is_side_project: !!item.is_side_project,
    period: item.period || '',
    employer: item.employer || '',
    description: item.description || '',
    tech_stack: item.tech_stack || [],
  }))
  const experience = (payload.experience || []).map((item) => {
    const nested = Array.isArray(item.roles) && item.roles.length
      ? item.roles
      : [{
        role: item.role || '',
        period: item.period || '',
        highlights: item.highlights || [],
        skills_used: item.skills_used || [],
      }]
    return {
      company: item.company || '',
      roles: nested.map((stint) => ({
        role: stint.role || '',
        period: stint.period || '',
        highlights: stint.highlights || [],
        skills_used: stint.skills_used || [],
      })),
    }
  })
  return {
    ...payload,
    languages,
    projects,
    experience,
    awards: payload.awards || [],
    basics: { ...EMPTY_PROFILE.basics, ...(payload.basics || {}) },
  }
}

function languageDisplayLabels(items) {
  return (items || []).map((item) => {
    const name = (item.name || '').trim()
    const level = (item.proficiency || '').trim()
    if (!name) return ''
    return level ? `${name} (${level})` : name
  }).filter(Boolean)
}

function UrlHint({ href }) {
  if (!href) return null
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="block font-mono text-[11px] text-cyan-retro hover:underline break-all mt-0.5"
    >
      {href}
    </a>
  )
}

function UnsavedChangesDialog({ open, t, saving, onSave, onDiscard, onStay }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/80" onClick={onStay} />
      <div
        className="relative panel max-w-sm w-full p-4 border-amber-retro"
        style={{ borderColor: '#f59e0b' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="unsaved-profile-title"
      >
        <h3 id="unsaved-profile-title" className="font-pixel text-[13px] text-amber-retro">
          {t('profile.unsavedTitle')}
        </h3>
        <p className="font-mono text-[12px] text-slate-300 mt-2">{t('profile.unsavedBody')}</p>
        <div className="flex flex-col gap-2 mt-3">
          <button
            type="button"
            disabled={saving}
            onClick={onSave}
            className="w-full panel px-3 py-2 flex items-center justify-center gap-2 font-pixel text-[12px] text-emerald-retro disabled:opacity-50"
          >
            {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />}
            {t('profile.unsavedSave')}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={onDiscard}
            className="w-full panel px-3 py-2 font-pixel text-[12px] text-rose-retro disabled:opacity-50"
          >
            {t('profile.unsavedDiscard')}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={onStay}
            className="w-full panel px-3 py-2 font-pixel text-[12px] text-slate-300 disabled:opacity-50"
          >
            {t('profile.unsavedStay')}
          </button>
        </div>
      </div>
    </div>
  )
}

function SectionHeader({ tabKey, t }) {
  const meta = TABS.find((item) => item.key === tabKey)
  if (!meta) return null
  const Icon = meta.icon
  return (
    <h4 className="font-pixel text-[13px] text-amber-retro flex items-center gap-2 pb-2 mb-1 border-b border-ink-700">
      <Icon size={16} aria-hidden />
      {t(meta.labelKey)}
    </h4>
  )
}

export default function ProfileEditor({ candidateId, onClose, onSaved }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState(candidateId ? 'edit' : 'new') // 'new' | 'edit'
  const [id, setId] = useState(candidateId || '')
  const [newName, setNewName] = useState('')
  const [newLocation, setNewLocation] = useState('Hong Kong')
  const [newLinkedin, setNewLinkedin] = useState('')
  const [useLinkedinSetup, setUseLinkedinSetup] = useState(true)
  const [cvFile, setCvFile] = useState(null)
  const [cvBusy, setCvBusy] = useState(false)
  const [cvMsg, setCvMsg] = useState(null)
  const [profile, setProfile] = useState(EMPTY_PROFILE)
  const [tab, setTab] = useState('basics')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)
  const [confirmClose, setConfirmClose] = useState(false)
  const [liBusy, setLiBusy] = useState(false)
  const [liMsg, setLiMsg] = useState(null)
  const snapshotRef = useRef(JSON.stringify(EMPTY_PROFILE))

  // load profile when entering edit mode
  useEffect(() => {
    if (mode !== 'edit' || !id) return
    let active = true
    setLoading(true); setErr(null)
    api.candidate(id)
      .then((p) => {
        if (!active) return
        const next = hydrateProfile(p)
        setProfile(next)
        snapshotRef.current = JSON.stringify(next)
      })
      .catch((e) => active && setErr(String(e.detail || e.message || e)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [mode, id])

  async function createNew(closeAfter = false) {
    if (!id.trim()) { setErr(t('profile.needIdName')); return false }
    const name = newName.trim() || (isValidLinkedinUsername(newLinkedin) ? displayNameFromLinkedin(newLinkedin) : '')
    if (!name) { setErr(t('profile.needIdName')); return false }
    setSaving(true); setErr(null)
    try {
      const linkedin = isValidLinkedinUsername(newLinkedin) ? newLinkedin.trim() : ''
      const p = await api.createCandidate(id.trim(), name, newLocation || 'Hong Kong', linkedin)
      const next = hydrateProfile(p)
      setProfile(next)
      snapshotRef.current = JSON.stringify(next)
      setMode('edit')
      onSaved?.()
      if (closeAfter) onClose()
      return true
    } catch (e) {
      setErr(String(e.detail || e.message || e))
      return false
    } finally {
      setSaving(false)
    }
  }

  async function ensureCreated() {
    if (mode === 'edit' && id) return id
    if (!id.trim()) {
      setErr(t('profile.needIdName'))
      return null
    }
    const name = newName.trim() || (isValidLinkedinUsername(newLinkedin) ? displayNameFromLinkedin(newLinkedin) : '')
    if (!name) {
      setErr(t('profile.needIdName'))
      return null
    }
    const linkedin = isValidLinkedinUsername(newLinkedin) ? newLinkedin.trim() : ''
    try {
      const p = await api.createCandidate(id.trim(), name, newLocation || 'Hong Kong', linkedin)
      const next = hydrateProfile(p)
      setProfile(next)
      snapshotRef.current = JSON.stringify(next)
      setMode('edit')
      onSaved?.()
      return id.trim()
    } catch (e) {
      const msg = String(e.detail || e.message || e)
      if (msg.includes('already exists') || msg.includes('409')) {
        try {
          const p = await api.candidate(id.trim())
          const next = hydrateProfile(p)
          setProfile(next)
          snapshotRef.current = JSON.stringify(next)
          setMode('edit')
          return id.trim()
        } catch (inner) {
          setErr(String(inner.detail || inner.message || inner))
          return null
        }
      }
      setErr(msg)
      return null
    }
  }

  async function importFromLinkedin() {
    const raw = mode === 'new' ? newLinkedin : profile.basics?.linkedin
    if (!isValidLinkedinUsername(raw)) return
    if (mode === 'new' && !useLinkedinSetup) {
      setErr(t('profile.linkedinSetupRequired'))
      return
    }
    setLiBusy(true); setLiMsg(null); setErr(null)
    try {
      const cid = await ensureCreated()
      if (!cid) return
      const res = await api.importLinkedin(cid, raw)
      const { linkedin_source: source, linkedin_url: _url, ...rest } = res
      const next = hydrateProfile(rest)
      setProfile(next)
      snapshotRef.current = JSON.stringify(next)
      setLiMsg(source === 'skeleton' ? t('milo.linkedinSkeleton') : t('milo.linkedinImported'))
      onSaved?.()
    } catch (e) {
      setErr(String(e.detail || e.message || e))
    } finally {
      setLiBusy(false)
    }
  }

  async function uploadSetupCv() {
    if (!cvFile) return
    setCvBusy(true); setCvMsg(null); setErr(null)
    try {
      const cid = await ensureCreated()
      if (!cid) return
      const name = (cvFile.name || '').toLowerCase()
      const isText = /\.(txt|md|json|text)$/.test(name)
      const res = isText
        ? await api.importCv(cid, await cvFile.text())
        : await api.importCvFile(cid, cvFile)
      const next = hydrateProfile(res)
      setProfile(next)
      snapshotRef.current = JSON.stringify(next)
      setCvMsg(t('milo.imported'))
      setCvFile(null)
      onSaved?.()
    } catch (e) {
      setErr(String(e.detail || e.message || e))
    } finally {
      setCvBusy(false)
    }
  }

  async function save(closeAfter = false) {
    setSaving(true); setErr(null)
    try {
      await api.saveCandidate(id, {
        ...profile,
        languages: profile.languages || [],
        awards: profile.awards || [],
        basics: {
          ...profile.basics,
          languages: languageDisplayLabels(profile.languages || []),
        },
      })
      snapshotRef.current = JSON.stringify(profile)
      onSaved?.()
      if (closeAfter) onClose()
      return true
    } catch (e) {
      setErr(String(e.detail || e.message || e))
      return false
    } finally {
      setSaving(false)
    }
  }

  function hasUnsavedChanges() {
    if (mode === 'new') {
      return Boolean(
        id.trim()
        || newName.trim()
        || newLinkedin.trim()
        || cvFile
        || (String(newLocation || '').trim() && String(newLocation).trim() !== 'Hong Kong'),
      )
    }
    if (loading) return false
    return JSON.stringify(profile) !== snapshotRef.current
  }

  function requestClose() {
    if (saving) return
    if (hasUnsavedChanges()) setConfirmClose(true)
    else onClose()
  }

  async function saveAndClose() {
    const ok = mode === 'new' ? await createNew(true) : await save(true)
    if (ok) setConfirmClose(false)
  }

  function discardAndClose() {
    setConfirmClose(false)
    onClose()
  }

  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      if (confirmClose) setConfirmClose(false)
      else requestClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // --- immutable update helpers ---
  const setBasics = (patch) => setProfile((p) => ({ ...p, basics: { ...p.basics, ...patch } }))

  // --- create-new form ---
  if (mode === 'new') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/70" onClick={requestClose} />
        <div className="relative panel max-w-lg w-full p-4 border-amber-retro" style={{ borderColor: '#f59e0b', maxHeight: 'calc(100vh - 2rem)', overflowY: 'auto' }}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-pixel text-[13px] text-amber-retro flex items-center gap-2"><UserPlus size={16} /> {t('profile.newPerson')}</h3>
            <button type="button" onClick={requestClose} className="text-slate-500 hover:text-rose-retro"><X size={18} /></button>
          </div>
          <div className="space-y-2.5">
            <LabeledInput label={t('profile.fields.id')} value={id} onChange={setId} placeholder="damien" />
            <LabeledInput label={t('profile.fields.name')} value={newName} onChange={setNewName} placeholder="Damien" />
            <LabeledInput label={t('profile.fields.location')} value={newLocation} onChange={setNewLocation} />
            <div>
              <LabeledInput
                label={t('profile.fields.linkedin')}
                value={newLinkedin}
                onChange={(v) => { setNewLinkedin(v ?? ''); setLiMsg(null) }}
                placeholder="your-linkedin-slug"
              />
              {isValidLinkedinUsername(newLinkedin) && (
                <a
                  href={linkedinProfileUrl(newLinkedin)}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 block font-mono text-[10px] text-cyan-400 truncate"
                >
                  {linkedinProfileUrl(newLinkedin)}
                </a>
              )}
              <label className="mt-2 flex items-start gap-2 font-mono text-[12px] text-slate-300">
                <input
                  type="checkbox"
                  checked={useLinkedinSetup}
                  onChange={(e) => setUseLinkedinSetup(e.target.checked)}
                  className="mt-0.5 accent-amber-retro"
                />
                <span>{t('profile.linkedinSetupUse')}</span>
              </label>
              <button
                type="button"
                disabled={liBusy || saving || !isValidLinkedinUsername(newLinkedin) || !useLinkedinSetup}
                onClick={importFromLinkedin}
                className="mt-2 w-full panel px-3 py-2 flex items-center justify-center gap-2 font-pixel text-[11px] text-violet-300 disabled:opacity-40"
              >
                {liBusy ? <LoaderCircle size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                {liBusy ? t('milo.linkedinParsing') : t('milo.linkedinImport')}
              </button>
              {liMsg && <div className="mt-1 font-mono text-[12px] text-emerald-retro">{liMsg}</div>}
              <div className="mt-1 font-mono text-[10px] text-slate-600">{t('profile.linkedinSetupHint')}</div>
            </div>
            <div>
              <span className="font-mono text-[12px] text-slate-500">{t('profile.setupCv')}</span>
              <input
                type="file"
                accept=".txt,.json,.md,.text,.pdf,.docx,.doc"
                disabled={cvBusy || saving}
                onChange={(e) => { setCvFile(e.target.files?.[0] || null); setCvMsg(null) }}
                className="mt-1 w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 file:mr-2"
              />
              {cvFile && (
                <div className="mt-1 font-mono text-[11px] text-slate-400">{cvFile.name}</div>
              )}
              <button
                type="button"
                disabled={cvBusy || saving || !cvFile}
                onClick={uploadSetupCv}
                className="mt-2 w-full panel px-3 py-2 flex items-center justify-center gap-2 font-pixel text-[11px] text-violet-300 disabled:opacity-40"
              >
                {cvBusy ? <LoaderCircle size={14} className="animate-spin" /> : <Upload size={14} />}
                {cvBusy ? t('milo.parsing') : t('profile.uploadCv')}
              </button>
              {cvMsg && <div className="mt-1 font-mono text-[12px] text-emerald-retro">{cvMsg}</div>}
              <div className="mt-1 font-mono text-[10px] text-slate-600">{t('milo.pdfNote')}</div>
            </div>
          </div>
          <div className="font-mono text-[11px] text-slate-600 mt-2">{t('profile.idHint')}</div>
          {err && <div className="mt-2 font-mono text-[12px] text-rose-retro flex items-center gap-1"><AlertCircle size={13} /> {err}</div>}
          <button type="button" onClick={() => createNew(false)} disabled={saving || liBusy || cvBusy} className="mt-3 w-full panel px-3 py-2.5 flex items-center justify-center gap-2 font-pixel text-[12px] text-amber-retro disabled:opacity-50">
            {saving ? <LoaderCircle size={15} className="animate-spin" /> : <UserPlus size={15} />} {t('profile.create')}
          </button>
        </div>
        <UnsavedChangesDialog
          open={confirmClose}
          t={t}
          saving={saving}
          onSave={saveAndClose}
          onDiscard={discardAndClose}
          onStay={() => setConfirmClose(false)}
        />
      </div>
    )
  }

  // --- editor ---
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/70" onClick={requestClose} />
      <aside className="relative w-full max-w-2xl panel border-l-4 border-amber-retro h-full flex flex-col">
        <div className="flex items-center justify-between p-3 border-b-2 border-ink-700">
          <h3 className="font-pixel text-[13px] text-amber-retro">{t('profile.edit')} · {profile.basics?.name || id}</h3>
          <button type="button" onClick={requestClose} className="text-slate-400 hover:text-rose-retro"><X size={20} /></button>
        </div>

        <div className="flex border-b-2 border-ink-700">
          {TABS.map((tb) => {
            const Icon = tb.icon
            const active = tab === tb.key
            return (
              <button
                key={tb.key}
                type="button"
                onClick={() => setTab(tb.key)}
                className={`flex-1 flex items-center justify-center py-2.5 border-r border-ink-700 last:border-r-0 ${
                  active ? 'bg-ink-700 text-amber-retro' : 'text-slate-500 hover:text-slate-300'
                }`}
                title={t(tb.labelKey)}
                aria-label={t(tb.labelKey)}
              >
                <Icon size={18} />
              </button>
            )
          })}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="flex items-center gap-2 font-mono text-[13px] text-slate-500"><LoaderCircle size={16} className="animate-spin" /> {t('profile.loading')}</div>
          ) : (
            <>
              <SectionHeader tabKey={tab} t={t} />
              {tab === 'basics' && (
                <div className="space-y-3">
                  <LabeledInput label={t('profile.fields.name')} value={profile.basics?.name} onChange={(v) => setBasics({ name: v ?? '' })} />
                  <LabeledInput label={t('profile.fields.location')} value={profile.basics?.location} onChange={(v) => setBasics({ location: v })} />
                  <LabeledInput label={t('profile.fields.email')} type="email" value={profile.basics?.email} onChange={(v) => setBasics({ email: v ?? '' })} placeholder="you@example.com" />
                  <LabeledInput label={t('profile.fields.phone')} value={profile.basics?.phone} onChange={(v) => setBasics({ phone: v ?? '' })} placeholder="+852 1234 5678" />
                  <LabeledInput label={t('profile.fields.address')} value={profile.basics?.address} onChange={(v) => setBasics({ address: v ?? '' })} placeholder={t('profile.fields.optional')} />
                  <div>
                    <LabeledInput label={t('profile.fields.website')} value={profile.basics?.website} onChange={(v) => setBasics({ website: v ?? '' })} placeholder="example.com" />
                    <UrlHint href={websiteUrl(profile.basics?.website)} />
                  </div>
                  <div>
                    <LabeledInput label={t('profile.fields.github')} value={profile.basics?.github} onChange={(v) => setBasics({ github: v ?? '' })} placeholder="octocat" />
                    <UrlHint href={githubProfileUrl(profile.basics?.github)} />
                  </div>
                  <div>
                    <LabeledInput label={t('profile.fields.linkedin')} value={profile.basics?.linkedin} onChange={(v) => setBasics({ linkedin: v ?? '' })} placeholder="your-linkedin-slug" />
                    <UrlHint href={linkedinProfileUrl(profile.basics?.linkedin)} />
                    {mode === 'edit' && (
                      <button
                        type="button"
                        disabled={liBusy || !isValidLinkedinUsername(profile.basics?.linkedin)}
                        onClick={importFromLinkedin}
                        className="mt-2 panel px-2 py-1 font-pixel text-[10px] text-violet-300 disabled:opacity-40"
                      >
                        {liBusy ? t('milo.linkedinParsing') : t('milo.linkedinImport')}
                      </button>
                    )}
                    {liMsg && <div className="mt-1 font-mono text-[12px] text-emerald-retro">{liMsg}</div>}
                    <div className="mt-1 font-mono text-[10px] text-slate-600">{t('milo.linkedinHint')}</div>
                  </div>
                  <LabeledInput label={t('profile.fields.minSalary')} type="number" value={profile.basics?.min_expected_salary_hkd} onChange={(v) => setBasics({ min_expected_salary_hkd: v })} />
                  <div>
                    <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.targetRoles')}</div>
                    <ChipInput values={profile.basics?.target_roles || []} onChange={(v) => setBasics({ target_roles: v })} placeholder="Senior Backend Engineer" accent="#06b6d4" />
                  </div>
                  <div>
                    <div className="font-mono text-[12px] text-slate-500 mb-2">{t('profile.fields.languages')}</div>
                    <RepeatList
                      items={profile.languages || []}
                      onChange={(v) => setProfile((p) => ({ ...p, languages: v }))}
                      blank={() => ({ name: '', proficiency: '' })}
                      addLabel={t('profile.addLanguage')}
                      render={(item, update) => (
                        <div className="space-y-2 pr-6">
                          <LabeledInput label={t('profile.fields.language')} value={item.name} onChange={(v) => update({ name: v ?? '' })} placeholder="Cantonese" />
                          <ProficiencyField value={item.proficiency} onChange={(v) => update({ proficiency: v })} t={t} />
                        </div>
                      )}
                    />
                  </div>
                </div>
              )}

              {tab === 'education' && (
                <RepeatList
                  items={profile.education || []}
                  onChange={(v) => setProfile((p) => ({ ...p, education: v }))}
                  blank={() => ({ institution: '', degree: '', year: '' })}
                  addLabel={t('profile.addEducation')}
                  render={(item, update) => (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.institution')} value={item.institution} onChange={(v) => update({ institution: v ?? '' })} />
                      <LabeledInput label={t('profile.fields.degree')} value={item.degree} onChange={(v) => update({ degree: v })} />
                      <LabeledInput label={t('profile.fields.year')} value={item.year} onChange={(v) => update({ year: v })} placeholder="2020 - 2024" />
                    </div>
                  )}
                />
              )}

              {tab === 'skills' && (
                <SkillsSection candidateId={id} skills={profile.technical_skills || {}} onChange={(v) => setProfile((p) => ({ ...p, technical_skills: v }))} />
              )}

              {tab === 'experience' && (
                <RepeatList
                  items={profile.experience || []}
                  onChange={(v) => setProfile((p) => ({ ...p, experience: v }))}
                  blank={() => ({
                    company: '',
                    roles: [{ role: '', period: '', highlights: [], skills_used: [] }],
                  })}
                  addLabel={t('profile.addExperience')}
                  render={(item, update) => (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.company')} value={item.company} onChange={(v) => update({ company: v ?? '' })} />
                      <div className="font-mono text-[12px] text-slate-500">{t('profile.fields.promotionHint')}</div>
                      <RepeatList
                        items={item.roles || []}
                        onChange={(roles) => update({ roles })}
                        blank={() => ({ role: '', period: '', highlights: [], skills_used: [] })}
                        addLabel={t('profile.addRole')}
                        render={(stint, updateRole) => (
                          <div className="space-y-2 pr-6">
                            <LabeledInput label={t('profile.fields.role')} value={stint.role} onChange={(v) => updateRole({ role: v })} />
                            <LabeledInput label={t('profile.fields.period')} value={stint.period} onChange={(v) => updateRole({ period: v })} placeholder="2024 - Present" />
                            <TextArea label={t('profile.fields.highlights')} value={(stint.highlights || []).join('\n')} onChange={(v) => updateRole({ highlights: v.split('\n').map((s) => s.trim()).filter(Boolean) })} rows={4} />
                            <div>
                              <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.skillsUsed')}</div>
                              <ChipInput values={stint.skills_used || []} onChange={(v) => updateRole({ skills_used: v })} placeholder="Python" accent="#f59e0b" />
                            </div>
                          </div>
                        )}
                      />
                    </div>
                  )}
                />
              )}

              {tab === 'projects' && (
                <RepeatList
                  items={profile.projects || []}
                  onChange={(v) => setProfile((p) => ({ ...p, projects: v }))}
                  blank={() => ({
                    name: '', role: '', is_side_project: false, period: '', employer: '',
                    description: '', tech_stack: [],
                  })}
                  addLabel={t('profile.addProject')}
                  render={(item, update) => {
                    const employers = [...new Set(
                      (profile.experience || [])
                        .map((job) => (job.company || '').trim())
                        .filter(Boolean),
                    )]
                    const current = (item.employer || '').trim()
                    const options = current && !employers.includes(current)
                      ? [current, ...employers]
                      : employers
                    return (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.name')} value={item.name} onChange={(v) => update({ name: v ?? '' })} />
                      <ProjectRoleField value={item.role} onChange={(v) => update({ role: v })} t={t} />
                      <label className="flex items-center gap-2 font-mono text-[12px] text-slate-300">
                        <input
                          type="checkbox"
                          checked={!!item.is_side_project}
                          onChange={(e) => update({ is_side_project: e.target.checked, employer: e.target.checked ? '' : item.employer })}
                        />
                        {t('profile.fields.isSideProject')}
                      </label>
                      <LabeledInput label={t('profile.fields.period')} value={item.period} onChange={(v) => update({ period: v })} placeholder="2024 - Present" />
                      {!item.is_side_project && (
                        <label className="block">
                          <span className="font-mono text-[12px] text-slate-500">{t('profile.fields.employer')}</span>
                          <select
                            value={current}
                            onChange={(e) => update({ employer: e.target.value })}
                            className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro bg-transparent"
                          >
                            <option value="">{t('profile.fields.employerUnset')}</option>
                            {options.map((company) => (
                              <option key={company} value={company}>{company}</option>
                            ))}
                          </select>
                          {employers.length === 0 && (
                            <div className="font-mono text-[11px] text-slate-600 mt-1">{t('profile.fields.employerNeedExperience')}</div>
                          )}
                        </label>
                      )}
                      <TextArea label={t('profile.fields.description')} value={item.description} onChange={(v) => update({ description: v })} rows={3} />
                      <div>
                        <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.techStack')}</div>
                        <ChipInput values={item.tech_stack || []} onChange={(v) => update({ tech_stack: v })} placeholder="Python" accent="#06b6d4" />
                      </div>
                    </div>
                    )
                  }}
                />
              )}

              {tab === 'certs' && (
                <RepeatList
                  items={profile.certifications || []}
                  onChange={(v) => setProfile((p) => ({ ...p, certifications: v }))}
                  blank={() => ({ name: '', issuer: '', year: null, category: '' })}
                  addLabel={t('profile.addCert')}
                  render={(item, update) => (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.name')} value={item.name} onChange={(v) => update({ name: v ?? '' })} />
                      <LabeledInput label={t('profile.fields.issuer')} value={item.issuer} onChange={(v) => update({ issuer: v })} />
                      <LabeledInput label={t('profile.fields.year')} type="number" value={item.year} onChange={(v) => update({ year: v })} />
                      <LabeledInput label={t('profile.fields.category')} value={item.category} onChange={(v) => update({ category: v })} placeholder="Cloud & Architecture" />
                    </div>
                  )}
                />
              )}

              {tab === 'awards' && (
                <RepeatList
                  items={profile.awards || []}
                  onChange={(v) => setProfile((p) => ({ ...p, awards: v }))}
                  blank={() => ({ name: '', issuer: '', year: null, description: '' })}
                  addLabel={t('profile.addAward')}
                  render={(item, update) => (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.name')} value={item.name} onChange={(v) => update({ name: v ?? '' })} />
                      <LabeledInput label={t('profile.fields.issuer')} value={item.issuer} onChange={(v) => update({ issuer: v })} />
                      <LabeledInput label={t('profile.fields.year')} type="number" value={item.year} onChange={(v) => update({ year: v })} />
                      <TextArea label={t('profile.fields.description')} value={item.description} onChange={(v) => update({ description: v })} rows={2} />
                    </div>
                  )}
                />
              )}
            </>
          )}
        </div>

        <div className="p-3 border-t-2 border-ink-700">
          {err && <div className="mb-2 font-mono text-[12px] text-rose-retro flex items-center gap-1"><AlertCircle size={13} /> {err}</div>}
          <button type="button" onClick={() => save(false)} disabled={saving} className="w-full panel px-3 py-2.5 flex items-center justify-center gap-2 font-pixel text-[12px] text-emerald-retro disabled:opacity-50">
            {saving ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />} {t('profile.save')}
          </button>
        </div>
        </aside>
        <UnsavedChangesDialog
          open={confirmClose}
          t={t}
          saving={saving}
          onSave={saveAndClose}
          onDiscard={discardAndClose}
          onStay={() => setConfirmClose(false)}
        />
      </div>
    )
}

// technical_skills = { category: [skills] }; add/remove categories + chips.
// Enhancement A: per-category "Suggest Skills" via local Ollama gemma4:e2b.
// Enhancement B: category picker from job-platform reference (JobsDB /
// CTgoodjobs / LinkedIn) with manual Tavily refresh.
function SkillsSection({ candidateId, skills, onChange }) {
  const { t } = useTranslation()
  const [newCat, setNewCat] = useState('')
  const [catRef, setCatRef] = useState({ categories: [], last_updated: null, sources: [] })
  const [refreshing, setRefreshing] = useState(false)

  const entries = Object.entries(skills || {})
  const update = (cat, list) => onChange({ ...skills, [cat]: list })
  const addCat = (name) => {
    const c = (name ?? newCat).trim()
    if (c && !(c in (skills || {}))) onChange({ ...skills, [c]: [] })
    setNewCat('')
  }

  // Load job-platform-referenced categories on mount.
  useEffect(() => {
    let active = true
    api.skillCategories()
      .then((d) => active && setCatRef(d))
      .catch(() => {})
    return () => { active = false }
  }, [])

  const refreshCats = async () => {
    setRefreshing(true)
    try {
      const d = await api.refreshSkillCategories()
      if (d && Array.isArray(d.categories)) setCatRef(d)
    } catch (e) {
      /* keep existing list on error */
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="space-y-3">
      {entries.map(([cat, list]) => (
        <CategoryBlock
          key={cat}
          cat={cat}
          list={list || []}
          candidateId={candidateId}
          onUpdate={(v) => update(cat, v)}
          onDelete={() => { const next = { ...skills }; delete next[cat]; onChange(next) }}
        />
      ))}

      {/* Enhancement B: category picker from job-platform reference */}
      <div className="panel-inset p-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[11px] text-slate-500">{t('skills.pickCategory')}</span>
          <button
            onClick={refreshCats}
            disabled={refreshing}
            className="font-mono text-[11px] text-cyan-retro flex items-center gap-1 disabled:opacity-50"
          >
            {refreshing ? <LoaderCircle size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {refreshing ? t('skills.refreshing') : t('skills.refreshCategories')}
          </button>
        </div>
        {catRef.last_updated && (
          <div className="font-mono text-[10px] text-slate-600">
            {t('skills.lastUpdated')}: {formatHKDateTime(catRef.last_updated)}
          </div>
        )}
        {catRef.categories?.length > 0 && (
          <select
            value=""
            onChange={(e) => { if (e.target.value) addCat(e.target.value) }}
            className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro"
          >
            <option value="">{t('skills.pickCategory')}</option>
            {catRef.categories.map((c) => {
              const labels = c.platform_labels || {}
              const tag = labels.jobsdb ? '(JobsDB)' : labels.ctgoodjobs ? '(CTgoodjobs)' : labels.linkedin ? '(LinkedIn)' : ''
              const label = `${c.internal_name} — ${labels.jobsdb || labels.ctgoodjobs || labels.linkedin || c.description || ''} ${tag}`.trim()
              return <option key={c.internal_name} value={c.internal_name}>{label}</option>
            })}
          </select>
        )}
        <div className="font-mono text-[10px] text-slate-600">{t('skills.orTypeCustom')}</div>
        <div className="flex gap-1.5">
          <input
            value={newCat}
            onChange={(e) => setNewCat(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCat() } }}
            placeholder={t('profile.newCategory')}
            className="flex-1 panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro"
          />
          <button onClick={() => addCat()} className="panel px-2 py-1.5 font-mono text-[12px] text-emerald-retro"><Plus size={14} /></button>
        </div>
      </div>
    </div>
  )
}

// One skill category block with a per-category "Suggest Skills" button.
// Suggestions come from local Ollama gemma4:e2b, grounded in the candidate's
// experience; clicking a suggestion chip adds it to the category's ChipInput.
function CategoryBlock({ cat, list, candidateId, onUpdate, onDelete }) {
  const { t } = useTranslation()
  const [suggesting, setSuggesting] = useState(false)
  const [suggestions, setSuggestions] = useState(null) // null = not fetched yet
  const [source, setSource] = useState(null) // 'ollama' | 'fallback'

  const suggest = async () => {
    setSuggesting(true)
    setSuggestions(null)
    try {
      const res = await api.skillSuggestions(candidateId, cat)
      setSuggestions(res.skills || [])
      setSource(res.source)
    } catch (e) {
      setSuggestions([])
      setSource('fallback')
    } finally {
      setSuggesting(false)
    }
  }

  const addSkill = (skill) => {
    if (!list.includes(skill)) onUpdate([...list, skill])
    if (suggestions) setSuggestions(suggestions.filter((s) => s !== skill))
  }

  return (
    <div className="panel-inset p-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <span className="font-pixel text-[12px] text-cyan-retro">{cat}</span>
          <button
            onClick={suggest}
            disabled={suggesting}
            title={t('skills.suggest')}
            className="font-mono text-[11px] text-amber-retro flex items-center gap-1 disabled:opacity-50"
          >
            {suggesting ? <LoaderCircle size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {suggesting ? t('skills.suggesting') : t('skills.suggest')}
          </button>
        </div>
        <button onClick={onDelete} className="text-slate-500 hover:text-rose-retro"><X size={14} /></button>
      </div>
      <ChipInput values={list || []} onChange={onUpdate} placeholder="add skill" accent="#06b6d4" />

      {/* Suggestion chips below the existing ChipInput */}
      {suggestions && suggestions.length > 0 && (
        <div className="mt-2 space-y-1">
          <div className="font-mono text-[10px] text-slate-500">{t('skills.suggestNotice')}</div>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => addSkill(s)}
                className="font-mono text-[11px] px-2 py-0.5 border flex items-center gap-1 text-amber-retro border-amber-retro hover:bg-amber-retro/10"
              >
                <Plus size={10} /> {s}
              </button>
            ))}
          </div>
        </div>
      )}
      {/* Fallback notice when Ollama is unavailable */}
      {source === 'fallback' && suggestions && suggestions.length === 0 && (
        <div className="mt-2 font-mono text-[10px] text-rose-retro">{t('skills.fallbackNote')}</div>
      )}
    </div>
  )
}
