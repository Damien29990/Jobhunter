// ProfileEditor.jsx — full-screen modal to edit a candidate's whole profile
// (config/master_profile.json or config/profiles/{id}.json) and to create a new person.
//
// The dashboard is read-only by default; this editor is the explicit write
// feature the user asked for. It writes ONLY to config/ profile JSON files
// (via PUT/POST /api/candidates) — never to src/agents, templates, or job_agent.db.
// Unknown profile keys round-trip safely (Pydantic extra="allow").

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Save, LoaderCircle, UserPlus, AlertCircle, Sparkles, RefreshCw, Plus } from 'lucide-react'
import { api, formatHKDateTime } from '../lib/api'
import { ChipInput, LabeledInput, TextArea, RepeatList } from './profileEditorParts'

const TABS = [
  { key: 'basics', labelKey: 'profile.tabs.basics' },
  { key: 'education', labelKey: 'profile.tabs.education' },
  { key: 'skills', labelKey: 'profile.tabs.skills' },
  { key: 'experience', labelKey: 'profile.tabs.experience' },
  { key: 'projects', labelKey: 'profile.tabs.projects' },
  { key: 'certs', labelKey: 'profile.tabs.certs' },
]

const EMPTY_PROFILE = {
  basics: { name: '', location: 'Hong Kong', target_roles: [], min_expected_salary_hkd: null, languages: [] },
  education: [], technical_skills: {}, experience: [], projects: [], certifications: [],
}

export default function ProfileEditor({ candidateId, onClose, onSaved }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState(candidateId ? 'edit' : 'new') // 'new' | 'edit'
  const [id, setId] = useState(candidateId || '')
  const [newName, setNewName] = useState('')
  const [newLocation, setNewLocation] = useState('Hong Kong')
  const [profile, setProfile] = useState(EMPTY_PROFILE)
  const [tab, setTab] = useState('basics')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  // load profile when entering edit mode
  useEffect(() => {
    if (mode !== 'edit' || !id) return
    let active = true
    setLoading(true); setErr(null)
    api.candidate(id)
      .then((p) => active && setProfile(p))
      .catch((e) => active && setErr(String(e.detail || e.message || e)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [mode, id])

  async function createNew() {
    if (!id.trim() || !newName.trim()) { setErr(t('profile.needIdName')); return }
    setSaving(true); setErr(null)
    try {
      const p = await api.createCandidate(id.trim(), newName.trim(), newLocation || 'Hong Kong')
      setProfile(p)
      setMode('edit')
      onSaved?.()
    } catch (e) {
      setErr(String(e.detail || e.message || e))
    } finally {
      setSaving(false)
    }
  }

  async function save() {
    setSaving(true); setErr(null)
    try {
      await api.saveCandidate(id, profile)
      onSaved?.()
    } catch (e) {
      setErr(String(e.detail || e.message || e))
    } finally {
      setSaving(false)
    }
  }

  // --- immutable update helpers ---
  const setBasics = (patch) => setProfile((p) => ({ ...p, basics: { ...p.basics, ...patch } }))

  // --- create-new form ---
  if (mode === 'new') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/70" onClick={onClose} />
        <div className="relative panel max-w-md w-full p-4 border-amber-retro" style={{ borderColor: '#f59e0b' }}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-pixel text-[13px] text-amber-retro flex items-center gap-2"><UserPlus size={16} /> {t('profile.newPerson')}</h3>
            <button onClick={onClose} className="text-slate-500 hover:text-rose-retro"><X size={18} /></button>
          </div>
          <div className="space-y-2.5">
            <LabeledInput label={t('profile.fields.id')} value={id} onChange={setId} placeholder="damien" />
            <LabeledInput label={t('profile.fields.name')} value={newName} onChange={setNewName} placeholder="Damien" />
            <LabeledInput label={t('profile.fields.location')} value={newLocation} onChange={setNewLocation} />
          </div>
          <div className="font-mono text-[11px] text-slate-600 mt-2">{t('profile.idHint')}</div>
          {err && <div className="mt-2 font-mono text-[12px] text-rose-retro flex items-center gap-1"><AlertCircle size={13} /> {err}</div>}
          <button onClick={createNew} disabled={saving} className="mt-3 w-full panel px-3 py-2.5 flex items-center justify-center gap-2 font-pixel text-[12px] text-amber-retro disabled:opacity-50">
            {saving ? <LoaderCircle size={15} className="animate-spin" /> : <UserPlus size={15} />} {t('profile.create')}
          </button>
        </div>
      </div>
    )
  }

  // --- editor ---
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <aside className="relative w-full max-w-2xl panel border-l-4 border-amber-retro h-full flex flex-col">
        <div className="flex items-center justify-between p-3 border-b-2 border-ink-700">
          <h3 className="font-pixel text-[13px] text-amber-retro">{t('profile.edit')} · {profile.basics?.name || id}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-rose-retro"><X size={20} /></button>
        </div>

        <div className="flex border-b-2 border-ink-700 overflow-x-auto">
          {TABS.map((tb) => (
            <button
              key={tb.key}
              onClick={() => setTab(tb.key)}
              className={`flex-1 whitespace-nowrap px-2 py-2.5 font-mono text-[12px] border-r border-ink-700 last:border-r-0 ${
                tab === tb.key ? 'bg-ink-700 text-amber-retro' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {t(tb.labelKey)}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="flex items-center gap-2 font-mono text-[13px] text-slate-500"><LoaderCircle size={16} className="animate-spin" /> {t('profile.loading')}</div>
          ) : (
            <>
              {tab === 'basics' && (
                <div className="space-y-3">
                  <LabeledInput label={t('profile.fields.name')} value={profile.basics?.name} onChange={(v) => setBasics({ name: v ?? '' })} />
                  <LabeledInput label={t('profile.fields.location')} value={profile.basics?.location} onChange={(v) => setBasics({ location: v })} />
                  <LabeledInput label={t('profile.fields.minSalary')} type="number" value={profile.basics?.min_expected_salary_hkd} onChange={(v) => setBasics({ min_expected_salary_hkd: v })} />
                  <div>
                    <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.targetRoles')}</div>
                    <ChipInput values={profile.basics?.target_roles || []} onChange={(v) => setBasics({ target_roles: v })} placeholder="Senior Backend Engineer" accent="#06b6d4" />
                  </div>
                  <div>
                    <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.languages')}</div>
                    <ChipInput values={profile.basics?.languages || []} onChange={(v) => setBasics({ languages: v })} placeholder="English (Professional)" accent="#10b981" />
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
                  blank={() => ({ company: '', role: '', period: '', highlights: [], skills_used: [] })}
                  addLabel={t('profile.addExperience')}
                  render={(item, update) => (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.company')} value={item.company} onChange={(v) => update({ company: v ?? '' })} />
                      <LabeledInput label={t('profile.fields.role')} value={item.role} onChange={(v) => update({ role: v })} />
                      <LabeledInput label={t('profile.fields.period')} value={item.period} onChange={(v) => update({ period: v })} placeholder="2024 - Present" />
                      <TextArea label={t('profile.fields.highlights')} value={(item.highlights || []).join('\n')} onChange={(v) => update({ highlights: v.split('\n').map((s) => s.trim()).filter(Boolean) })} rows={4} />
                      <div>
                        <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.skillsUsed')}</div>
                        <ChipInput values={item.skills_used || []} onChange={(v) => update({ skills_used: v })} placeholder="Python" accent="#f59e0b" />
                      </div>
                    </div>
                  )}
                />
              )}

              {tab === 'projects' && (
                <RepeatList
                  items={profile.projects || []}
                  onChange={(v) => setProfile((p) => ({ ...p, projects: v }))}
                  blank={() => ({ name: '', description: '', tech_stack: [] })}
                  addLabel={t('profile.addProject')}
                  render={(item, update) => (
                    <div className="space-y-2 pr-6">
                      <LabeledInput label={t('profile.fields.name')} value={item.name} onChange={(v) => update({ name: v ?? '' })} />
                      <TextArea label={t('profile.fields.description')} value={item.description} onChange={(v) => update({ description: v })} rows={3} />
                      <div>
                        <div className="font-mono text-[12px] text-slate-500 mb-1">{t('profile.fields.techStack')}</div>
                        <ChipInput values={item.tech_stack || []} onChange={(v) => update({ tech_stack: v })} placeholder="Python" accent="#06b6d4" />
                      </div>
                    </div>
                  )}
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
            </>
          )}
        </div>

        <div className="p-3 border-t-2 border-ink-700">
          {err && <div className="mb-2 font-mono text-[12px] text-rose-retro flex items-center gap-1"><AlertCircle size={13} /> {err}</div>}
          <button onClick={save} disabled={saving} className="w-full panel px-3 py-2.5 flex items-center justify-center gap-2 font-pixel text-[12px] text-emerald-retro disabled:opacity-50">
            {saving ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />} {t('profile.save')}
          </button>
        </div>
      </aside>
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
