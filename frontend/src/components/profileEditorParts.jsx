// profileEditorParts.jsx — reusable inputs for the profile editor.
// ChipInput: add/remove string chips. LabeledInput/TextArea: simple fields.
// RepeatList: repeatable items with add/remove.

import { useState } from 'react'
import { Plus, X, Trash2 } from 'lucide-react'

export function ChipInput({ values = [], onChange, placeholder, accent = '#06b6d4' }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const v = draft.trim()
    if (v && !values.includes(v)) onChange([...values, v])
    setDraft('')
  }
  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-1.5">
        {values.map((v) => (
          <span key={v} className="font-mono text-[12px] px-2 py-0.5 border flex items-center gap-1" style={{ color: accent, borderColor: accent }}>
            {v}
            <button onClick={() => onChange(values.filter((x) => x !== v))} className="opacity-60 hover:opacity-100"><X size={11} /></button>
          </span>
        ))}
        {values.length === 0 && <span className="font-mono text-[12px] text-slate-600">—</span>}
      </div>
      <div className="flex gap-1.5">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder={placeholder}
          className="flex-1 panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro"
        />
        <button onClick={add} className="panel px-2 py-1.5 font-mono text-[12px] text-amber-retro"><Plus size={14} /></button>
      </div>
    </div>
  )
}

export function LabeledInput({ label, value, onChange, type = 'text', placeholder }) {
  return (
    <label className="block">
      <span className="font-mono text-[12px] text-slate-500">{label}</span>
      <input
        type={type}
        value={value ?? ''}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.type === 'number' ? (e.target.value ? Number(e.target.value) : undefined) : e.target.value)}
        className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro"
      />
    </label>
  )
}

export function TextArea({ label, value, onChange, rows = 3 }) {
  return (
    <label className="block">
      <span className="font-mono text-[12px] text-slate-500">{label}</span>
      <textarea
        value={value ?? ''}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className="w-full panel-inset px-2 py-1.5 font-mono text-[12px] text-slate-200 focus:outline-none focus:border-amber-retro resize-y"
      />
    </label>
  )
}

export function RepeatList({ items = [], onChange, blank, render, addLabel }) {
  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="panel-inset p-2.5 relative">
          <button
            onClick={() => onChange(items.filter((_, j) => j !== i))}
            className="absolute top-2 right-2 text-slate-500 hover:text-rose-retro"
            title="remove"
          ><Trash2 size={14} /></button>
          {render(item, (next) => onChange(items.map((x, j) => (j === i ? { ...x, ...next } : x))))}
        </div>
      ))}
      <button
        onClick={() => onChange([...items, blank()])}
        className="font-mono text-[12px] px-2 py-1.5 panel text-emerald-retro flex items-center gap-1.5"
      >
        <Plus size={14} /> {addLabel}
      </button>
    </div>
  )
}
