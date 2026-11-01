import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { FileVideo, X, Loader2, Wand2 } from 'lucide-react'
import { api, fmtBytes } from '../api.js'
import { Dropzone, Progress, Segmented } from '../components/ui.jsx'

const SAMPLE = `Hi! We just opened our little café, Bean & Bloom, and want a 30-second Instagram reel from today's grand opening. It should feel warm, cosy and energetic. Start outside so people see where we are, then show our coffee being made — especially the latte art, our barista is amazing at it. Show happy customers, a slow look at our pastries, and me welcoming everyone (please use the bit where I actually say welcome!). We also did a ribbon cutting at the door. End with everyone raising a toast. Nothing blurry or too dark, please — we want it to look professional.`

const ASPECTS = [
  { value: '9:16', label: '9:16 Reel' }, { value: '16:9', label: '16:9' },
  { value: '1:1', label: '1:1' }, { value: '4:5', label: '4:5' },
]

export default function NewProject() {
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const [length, setLength] = useState(30)
  const [aspect, setAspect] = useState('9:16')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)

  const addFiles = (list) => setFiles((f) => [...f, ...list.filter((n) => !f.some((x) => x.name === n.name))])

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return toast.error('Give the project a name')
    setBusy(true)
    try {
      const p = await api.createProject({ name: name.trim(), brief, target_seconds: Number(length), aspect_ratio: aspect })
      if (files.length) {
        const res = await api.uploadFootage(p.id, files, setProgress)
        if (res?.skipped?.length) toast.message(`Skipped: ${res.skipped.join(', ')}`)
      }
      toast.success('Project created — analysing footage')
      nav(`/p/${p.id}`)
    } catch (err) {
      toast.error(err.message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl">
      <p className="chip bg-brand-soft text-brand">New reel</p>
      <h1 className="mt-3 text-3xl font-bold sm:text-4xl">Tell us what the customer wants</h1>
      <p className="mt-2 text-muted">Paste their brief in their own words. The AI plans the shots from it.</p>

      <div className="card mt-8 space-y-6 p-5 sm:p-7">
        <div>
          <label className="label" htmlFor="name">Project name</label>
          <input id="name" className="input" placeholder="e.g. Bean & Bloom grand opening" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <label className="label" htmlFor="brief">Customer brief</label>
            <button type="button" className="mb-1.5 inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
              onClick={() => { setBrief(SAMPLE); if (!name) setName('Bean & Bloom grand opening') }}>
              <Wand2 size={13} /> Use sample brief
            </button>
          </div>
          <textarea id="brief" rows={7} className="input resize-y leading-relaxed" value={brief} onChange={(e) => setBrief(e.target.value)}
            placeholder="“We want a 30-second reel of our opening. Start outside, show the coffee being made…”" />
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <span className="label">Reel length</span>
            <div className="flex items-center gap-2">
              <Segmented value={length} onChange={setLength} options={[15, 30, 60].map((v) => ({ value: v, label: `${v}s` }))} />
              <input type="number" min={5} max={300} className="input w-20" value={length} onChange={(e) => setLength(e.target.value)} aria-label="Custom length in seconds" />
            </div>
          </div>
          <div>
            <span className="label">Format</span>
            <Segmented value={aspect} onChange={setAspect} options={ASPECTS} />
          </div>
        </div>
        <div>
          <span className="label">Footage</span>
          <Dropzone onFiles={addFiles} />
          {files.length > 0 && (
            <ul className="mt-3 divide-y divide-line rounded-xl border border-line">
              {files.map((f) => (
                <li key={f.name} className="flex items-center gap-3 px-3.5 py-2.5 text-sm">
                  <FileVideo size={16} className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="shrink-0 text-xs text-muted">{fmtBytes(f.size)}</span>
                  {!busy && (
                    <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles((x) => x.filter((y) => y !== f))}
                      className="rounded-md p-1 text-muted hover:bg-stone-100 hover:text-ink"><X size={14} /></button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="sticky bottom-0 -mx-4 mt-6 border-t border-line bg-paper/95 px-4 py-4 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
        {busy && files.length > 0 && (
          <div className="mb-3">
            <div className="mb-1 flex justify-between text-xs text-muted"><span>Uploading footage…</span><span>{Math.round(progress * 100)}%</span></div>
            <Progress value={progress} />
          </div>
        )}
        <button className="btn-primary w-full py-3 sm:w-auto" disabled={busy}>
          {busy ? <><Loader2 size={16} className="animate-spin" /> Creating…</> : 'Create project'}
        </button>
      </div>
    </form>
  )
}
