// MiloChat.jsx — chat with Milo (Agent 0, the CV intake / exploratory summarizer).
// Talks to POST /api/milo/chat (JSON or multipart with file attachments)
// and loads history from GET /api/milo/history/{id}.

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Send, LoaderCircle, MessageSquare, Paperclip } from 'lucide-react'
import { api } from '../lib/api'

const ACCEPT = '.pdf,.txt,.md,.json,.docx,.text,.csv'
const MAX_FILES = 3
const MAX_BYTES = 5 * 1024 * 1024

function attachmentNames(m) {
  if (m.attachments?.length) return m.attachments
  const hit = (m.content || '').match(/\[Attached: ([^\]]+)\]/)
  return hit ? hit[1].split(',').map((s) => s.trim()).filter(Boolean) : []
}

function displayContent(m) {
  return (m.content || '')
    .replace(/\[Attached: [^\]]+\]\n?/g, '')
    .replace(/\[CV imported into profile\]\n?/g, '')
    .trim()
}

export default function MiloChat({ candidateId, onClose }) {
  const { t } = useTranslation()
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [files, setFiles] = useState([])
  const [sending, setSending] = useState(false)
  const [loadingHist, setLoadingHist] = useState(true)
  const [histErr, setHistErr] = useState(null)
  const [attachErr, setAttachErr] = useState(null)
  const scrollRef = useRef(null)
  const fileRef = useRef(null)

  useEffect(() => {
    let active = true
    setLoadingHist(true); setHistErr(null)
    api.miloHistory(candidateId)
      .then((res) => { if (active) setMessages(res.messages || []) })
      .catch((e) => { if (active) setHistErr(String(e.detail || e.message || e)) })
      .finally(() => active && setLoadingHist(false))
    return () => { active = false }
  }, [candidateId])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length])

  function addFiles(list) {
    if (!list || list.length === 0) return
    setAttachErr(null)
    const next = [...files]
    for (const f of list) {
      if (next.length >= MAX_FILES) {
        setAttachErr(t('milo.maxFiles'))
        break
      }
      if (f.size > MAX_BYTES) {
        setAttachErr(t('milo.tooLarge', { name: f.name }))
        continue
      }
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue
      next.push(f)
    }
    setFiles(next)
    if (fileRef.current) fileRef.current.value = ''
  }

  async function send() {
    const text = draft.trim()
    if ((!text && files.length === 0) || sending) return
    setSending(true)
    setAttachErr(null)
    const pending = files
    const userMsg = {
      role: 'user',
      content: text,
      attachments: pending.map((f) => f.name),
      created_at: new Date().toISOString(),
    }
    setMessages((m) => [...m, userMsg])
    setDraft('')
    setFiles([])
    try {
      const res = await api.miloChat(candidateId, text, pending)
      if (res?.reply) {
        setMessages((m) => [...m, {
          role: 'assistant',
          content: res.reply,
          imported: res.imported_files || [],
          created_at: new Date().toISOString(),
        }])
      }
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${String(e.detail || e.message || e)}`, created_at: new Date().toISOString() }])
    } finally {
      setSending(false)
    }
  }

  const canSend = !sending && (draft.trim() || files.length > 0)

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <aside className="relative w-full max-w-md panel border-l-4 h-full flex flex-col" style={{ borderColor: '#a78bfa' }}>
        <div className="flex items-center justify-between p-3 border-b-2 border-ink-700">
          <div className="flex items-center gap-2">
            <MessageSquare size={18} style={{ color: '#a78bfa' }} />
            <h3 className="font-pixel text-[13px]" style={{ color: '#a78bfa' }}>{t('milo.title')}</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-rose-retro"><X size={20} /></button>
        </div>

        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 kanban-scroll">
          {loadingHist && (
            <div className="flex items-center gap-2 font-mono text-[12px] text-slate-500">
              <LoaderCircle size={14} className="animate-spin" /> {t('milo.loadingHistory')}
            </div>
          )}
          {histErr && !loadingHist && messages.length === 0 && (
            <div className="font-mono text-[12px] text-amber-retro">{t('milo.historyError')}</div>
          )}
          {messages.length === 0 && !loadingHist && !histErr && (
            <div className="font-mono text-[12px] text-slate-600">{t('milo.empty')}</div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className="max-w-[85%] panel-inset px-3 py-2"
                style={{ borderColor: m.role === 'user' ? '#a78bfa' : '#1e293b' }}
              >
                <div className="font-mono text-[10px] mb-1" style={{ color: m.role === 'user' ? '#a78bfa' : '#64748b' }}>
                  {m.role === 'user' ? t('milo.you') : 'Milo'}
                </div>
                {attachmentNames(m).length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-1.5">
                    {attachmentNames(m).map((name) => (
                      <span key={name} className="font-mono text-[10px] px-1.5 py-0.5 border" style={{ color: '#a78bfa', borderColor: '#a78bfa' }}>
                        {name}
                      </span>
                    ))}
                  </div>
                )}
                {displayContent(m) && (
                  <div className="font-sans text-[13px] text-slate-200 whitespace-pre-wrap leading-relaxed">{displayContent(m)}</div>
                )}
                {(m.imported?.length > 0 || /\[CV imported into profile\]/.test(m.content || '')) && (
                  <div className="font-mono text-[11px] text-emerald-retro mt-1">{t('milo.imported')}</div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="p-3 border-t-2 border-ink-700">
          {files.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {files.map((f) => (
                <span key={`${f.name}-${f.size}`} className="font-mono text-[11px] px-1.5 py-0.5 border flex items-center gap-1" style={{ color: '#a78bfa', borderColor: '#a78bfa' }}>
                  {f.name}
                  <button
                    onClick={() => setFiles((cur) => cur.filter((x) => x !== f))}
                    className="opacity-70 hover:opacity-100"
                    title={t('milo.removeFile')}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {attachErr && <div className="font-mono text-[11px] text-rose-retro mb-1.5">{attachErr}</div>}
          <div className="flex items-end gap-2">
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={sending}
              title={t('milo.attach')}
              className="panel px-2.5 py-2 flex items-center justify-center disabled:opacity-50"
              style={{ color: '#a78bfa', borderColor: '#a78bfa' }}
            >
              <Paperclip size={16} />
            </button>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder={t('milo.placeholder')}
              rows={2}
              className="flex-1 panel-inset px-2.5 py-2 font-sans text-[13px] text-slate-200 focus:outline-none resize-none"
            />
            <button
              onClick={send}
              disabled={!canSend}
              className="panel px-3 py-2 flex items-center justify-center disabled:opacity-50"
              style={{ color: '#a78bfa', borderColor: '#a78bfa' }}
            >
              {sending ? <LoaderCircle size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
          <div className="font-mono text-[10px] text-slate-600 mt-1.5">{t('milo.attachHint')}</div>
        </div>
      </aside>
    </div>
  )
}
