import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Cpu, Zap, Loader2, CheckCircle2, AlertTriangle, ExternalLink, Save, PlugZap } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../api.js'

function Option({ active, onClick, icon: Icon, title, text, badge }) {
  return (
    <button type="button" onClick={onClick}
      className={clsx('flex w-full items-start gap-3 rounded-2xl border-2 p-4 text-left transition',
        active ? 'border-brand bg-brand-soft/50' : 'border-line bg-white hover:border-ink/30')}>
      <span className={clsx('grid h-10 w-10 shrink-0 place-items-center rounded-xl', active ? 'bg-brand text-white' : 'bg-stone-100 text-muted')}><Icon size={18} /></span>
      <span className="min-w-0">
        <span className="flex items-center gap-2 font-semibold">{title}{badge && <span className="chip bg-ink text-white">{badge}</span>}</span>
        <span className="mt-0.5 block text-sm text-muted">{text}</span>
      </span>
    </button>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['compute'], queryFn: api.compute })
  const [mode, setMode] = useState('local')
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [fallback, setFallback] = useState(true)
  const [test, setTest] = useState(null) // {ok, gpu, device} | {error}
  const [busy, setBusy] = useState('')

  useEffect(() => {
    if (!data) return
    setMode(data.mode); setUrl(data.remote_url || ''); setFallback(data.fallback_to_local)
  }, [data])

  const body = { mode, remote_url: url, remote_token: token || null, fallback_to_local: fallback }

  async function runTest() {
    setBusy('test'); setTest(null)
    try { setTest(await api.testCompute(body)) } catch (e) { setTest({ error: e.message }) }
    setBusy('')
  }

  async function save() {
    setBusy('save')
    try {
      await api.saveCompute(body)
      setToken('')
      toast.success(mode === 'remote' ? 'New analyses will run on the Colab GPU' : 'New analyses will run on this computer')
      qc.invalidateQueries({ queryKey: ['compute'] })
    } catch (e) { toast.error(e.message) }
    setBusy('')
  }

  return (
    <div className="mx-auto max-w-3xl">
      <p className="chip bg-brand-soft text-brand">Settings</p>
      <h1 className="mt-3 text-3xl font-bold">Processing</h1>
      <p className="mt-2 text-muted">Choose where the heavy video analysis (scene detection, CLIP, Whisper) runs. Shot search and rendering always run here.</p>

      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        <Option active={mode === 'local'} onClick={() => setMode('local')} icon={Cpu} title="Local CPU"
          text="Runs on this computer. Works offline, no setup. About 1.4 s per second of footage on a 6-core laptop." />
        <Option active={mode === 'remote'} onClick={() => setMode('remote')} icon={Zap} title="Google Colab GPU" badge="Free T4"
          text="Sends videos to a free Colab T4 worker. Roughly 10× faster analysis. Needs the notebook running." />
      </div>

      {mode === 'remote' && (
        <div className="card mt-6 space-y-5 p-5 sm:p-6">
          <div className="rounded-xl bg-stone-50 p-4 text-sm leading-relaxed">
            <p className="font-semibold">How to connect (2 minutes)</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">
              <li>Open <b className="text-ink">notebooks/colab_gpu_worker.ipynb</b> in Google Colab (File → Upload notebook).</li>
              <li>Runtime → Change runtime type → <b className="text-ink">T4 GPU</b>, then Runtime → Run all.</li>
              <li>The last cell prints a <b className="text-ink">Worker URL</b> and a <b className="text-ink">token</b>. Paste both below.</li>
            </ol>
            <a href="https://colab.research.google.com/" target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline">
              Open Google Colab <ExternalLink size={12} />
            </a>
          </div>
          <div>
            <label className="label" htmlFor="url">Worker URL</label>
            <input id="url" className="input font-mono text-xs" placeholder="https://something-random.trycloudflare.com" value={url} onChange={(e) => setUrl(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="tok">Worker token</label>
            <input id="tok" type="password" className="input font-mono text-xs" autoComplete="off"
              placeholder={data?.has_token ? `Saved (${data.token_hint}). Leave empty to keep it` : 'Paste the token from the notebook'}
              value={token} onChange={(e) => setToken(e.target.value)} />
          </div>
          <label className="flex items-start gap-2.5 text-sm">
            <input type="checkbox" className="mt-1 accent-brand" checked={fallback} onChange={(e) => setFallback(e.target.checked)} />
            <span><b>Fall back to local CPU</b><span className="block text-xs text-muted">If Colab disconnects (free sessions time out), the job continues on this computer instead of failing.</span></span>
          </label>
          <button className="btn-ghost w-full" onClick={runTest} disabled={busy || !url}>
            {busy === 'test' ? <Loader2 size={15} className="animate-spin" /> : <PlugZap size={15} />} Test connection
          </button>
          {test && (test.error ? (
            <p className="flex items-start gap-2 rounded-xl bg-brand-soft p-3 text-sm text-brand"><AlertTriangle size={16} className="mt-0.5 shrink-0" />{test.error}</p>
          ) : (
            <p className="flex items-start gap-2 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 size={16} className="mt-0.5 shrink-0" />
              Connected. Worker is on <b className="mx-1">{test.gpu || test.device.toUpperCase()}</b>{test.device !== 'cuda' && ' (no GPU: check the Colab runtime type)'}{test.busy && ', currently busy'}</p>
          ))}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between gap-3">
        <p className="text-xs text-muted">Currently: <b className="text-ink">{data?.mode === 'remote' ? 'Google Colab GPU' : 'Local CPU'}</b></p>
        <button className="btn-primary" onClick={save} disabled={busy}>{busy === 'save' ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Save</button>
      </div>
    </div>
  )
}
