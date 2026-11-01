import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  Activity, AlertTriangle, CheckCircle2, Clock, Cpu, DollarSign, Film, Gauge, HardDrive, Loader2, LogOut,
  RefreshCw, Search, Server, Table2, Timer, Zap,
} from 'lucide-react'
import { CostSeries, DailyBars, Heatmap, HBars, Histogram, SERIES, ShareBar, SpeedScatter, secs, usd } from './charts.jsx'

const API = '/api/v1/admin'
const getToken = () => { try { return localStorage.getItem('onspotly_admin') || '' } catch { return '' } }
const setToken = (t) => { try { t ? localStorage.setItem('onspotly_admin', t) : localStorage.removeItem('onspotly_admin') } catch { /* private mode */ } }

async function fetchDashboard(days) {
  const r = await fetch(`${API}/dashboard?days=${days}`, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (r.status === 401) throw Object.assign(new Error('auth'), { auth: true })
  if (!r.ok) throw new Error(`Dashboard failed (${r.status})`)
  return r.json()
}

function Login({ onDone }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr('')
    const r = await fetch(`${API}/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pw }) })
    setBusy(false)
    if (!r.ok) return setErr('Wrong password')
    setToken((await r.json()).token)
    onDone()
  }
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <form onSubmit={submit} className="panel w-full max-w-sm p-7">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand"><Gauge size={18} /></span>
        <h1 className="mt-5 text-2xl font-bold">OnSpotly Admin</h1>
        <p className="mt-1 text-sm text-dim">Analytics, processing and cost insights.</p>
        <label className="kicker mt-6 block" htmlFor="pw">Admin password</label>
        <input id="pw" type="password" autoFocus className="input mt-1.5" value={pw} onChange={(e) => setPw(e.target.value)} />
        {err && <p className="mt-2 text-sm text-brand">{err}</p>}
        <button className="btn mt-5 w-full bg-brand text-white hover:bg-brand/90" disabled={busy}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

function Section({ title, subtitle, children, right, className }) {
  return (
    <section className={clsx('panel p-5', className)}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div><h2 className="font-display text-base font-semibold">{title}</h2>{subtitle && <p className="mt-0.5 text-xs text-faint">{subtitle}</p>}</div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Kpi({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 text-faint"><Icon size={14} className={accent ? 'text-brand' : ''} /><span className="kicker">{label}</span></div>
      <p className="mt-2 font-display text-2xl font-bold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-faint">{sub}</p>}
    </div>
  )
}

const STATUS = {
  done: [CheckCircle2, 'text-emerald-400', 'Done'],
  failed: [AlertTriangle, 'text-brand', 'Failed'],
  running: [Loader2, 'text-amber-400 animate-spin', 'Running'],
  queued: [Clock, 'text-dim', 'Queued'],
}

function StatusLabel({ status }) {
  const [Icon, cls, label] = STATUS[status] || [Clock, 'text-dim', status]
  return <span className="inline-flex items-center gap-1.5 text-xs"><Icon size={13} className={cls} />{label}</span>
}

const ago = (d) => {
  const s = (Date.now() - new Date(d).getTime()) / 1000
  return s < 60 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`
}
const mb = (b) => (b > 2 ** 30 ? `${(b / 2 ** 30).toFixed(2)} GB` : `${(b / 2 ** 20).toFixed(1)} MB`)

const TYPE_COLOR = { project: 'bg-sky-500/15 text-sky-300', assets: 'bg-emerald-500/15 text-emerald-300', asset: 'bg-emerald-500/15 text-emerald-300',
  job: 'bg-zinc-500/20 text-zinc-300', shotlist: 'bg-violet-500/15 text-violet-300', run: 'bg-amber-500/15 text-amber-300', export: 'bg-brand-soft text-red-300' }

function CostTable({ rows }) {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('total_usd')
  const shown = useMemo(() => rows.filter((r) => r.name.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (b[sort] ?? 0) - (a[sort] ?? 0)), [rows, q, sort])
  const cols = [
    ['name', 'Project', null], ['footage_seconds', 'Footage', secs], ['processing_seconds', 'Processing', secs],
    ['cpu_seconds', 'CPU', secs], ['peak_ram_mb', 'Peak RAM', (v) => `${Math.round(v)} MB`], ['llm_tokens', 'Tokens', (v) => v.toLocaleString()],
    ['storage_mb', 'Storage', (v) => `${v} MB`], ['compute_usd', 'Compute', usd], ['llm_usd', 'LLM', usd], ['storage_usd', 'Storage $', usd],
    ['egress_usd', 'Egress', usd], ['total_usd', 'Total', usd], ['usd_per_footage_minute', '$/footage min', usd],
  ]
  return (
    <div>
      <div className="mb-3 flex items-center gap-2 rounded-xl border border-edge bg-panel-2 px-3">
        <Search size={14} className="text-faint" />
        <input className="w-full bg-transparent py-2 text-sm outline-none" placeholder="Filter projects" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-sm">
          <thead>
            <tr className="border-b border-edge text-left">
              {cols.map(([k, label]) => (
                <th key={k} className="whitespace-nowrap px-2 py-2 font-medium">
                  <button className={clsx('kicker hover:text-fg', sort === k && 'text-fg')} onClick={() => k !== 'name' && setSort(k)}>{label}{sort === k && ' ↓'}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.project_id} className="border-b border-edge/60 hover:bg-white/[.02]">
                {cols.map(([k, , fmt]) => (
                  <td key={k} className={clsx('whitespace-nowrap px-2 py-2.5 tabular-nums', k === 'name' ? 'max-w-[220px] truncate font-medium' : 'text-dim', k === 'total_usd' && 'font-semibold text-fg')}>
                    {fmt ? fmt(r[k] ?? 0) : r[k]}
                  </td>
                ))}
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={cols.length} className="px-2 py-6 text-center text-faint">No projects</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Dashboard({ onLogout }) {
  const [days, setDays] = useState(30)
  const { data: d, isLoading, error, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ['dash', days], queryFn: () => fetchDashboard(days), refetchInterval: 10000,
  })
  if (error?.auth) { setToken(''); onLogout(); return null }
  if (isLoading) return <div className="grid min-h-dvh place-items-center"><Loader2 className="animate-spin text-brand" /></div>
  if (error) return <p className="p-8 text-brand">{error.message}</p>

  const k = d.kpis
  const cat = d.cost_by_category
  const parts = Object.keys(SERIES).map((key) => ({ key, label: SERIES[key].label, color: SERIES[key].color, value: cat[key] || 0, fmt: usd(cat[key] || 0, 5) }))
  const kinds = Object.entries(d.processing.by_kind)

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b border-edge bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand"><Gauge size={16} /></span>
          <p className="font-display font-bold">OnSpotly <span className="font-medium text-faint">Admin</span></p>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden rounded-xl border border-edge p-1 sm:flex">
              {[7, 30, 90].map((n) => (
                <button key={n} onClick={() => setDays(n)} className={clsx('rounded-lg px-2.5 py-1 text-xs font-semibold', days === n ? 'bg-fg text-bg' : 'text-dim hover:text-fg')}>{n}d</button>
              ))}
            </div>
            <button onClick={() => refetch()} aria-label="Refresh" className="grid h-9 w-9 place-items-center rounded-xl border border-edge text-dim hover:text-fg">
              <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
            </button>
            <a href="/" className="btn hidden border border-edge py-2 text-dim hover:text-fg sm:inline-flex">Studio</a>
            <button onClick={() => { setToken(''); onLogout() }} aria-label="Sign out" className="grid h-9 w-9 place-items-center rounded-xl border border-edge text-dim hover:text-fg"><LogOut size={15} /></button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold sm:text-3xl">Platform overview</h1>
            <p className="text-sm text-faint">Live · updated {new Date(dataUpdatedAt).toLocaleTimeString()} · {d.config.database} · {d.config.storage} · LLM {d.config.llm}</p>
          </div>
          <div className="flex rounded-xl border border-edge p-1 sm:hidden">
            {[7, 30, 90].map((n) => (
              <button key={n} onClick={() => setDays(n)} className={clsx('rounded-lg px-2.5 py-1 text-xs font-semibold', days === n ? 'bg-fg text-bg' : 'text-dim')}>{n}d</button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          <Kpi icon={Film} label="Projects" value={k.projects} sub={`${k.videos_uploaded} videos · ${k.footage_minutes} min`} />
          <Kpi icon={Zap} label="Finder runs" value={k.finder_runs} sub={`${k.renders} renders · ${k.downloads} downloads`} />
          <Kpi icon={DollarSign} label="Total spend" value={usd(k.total_cost_usd)} sub="all categories" accent />
          <Kpi icon={DollarSign} label="Cost / video" value={usd(k.avg_cost_per_project_usd)} sub="per processed project" accent />
          <Kpi icon={Timer} label="Avg job time" value={secs(k.avg_processing_seconds)} sub={`${k.processing_speed_x}× realtime analysis`} />
          <Kpi icon={CheckCircle2} label="Success rate" value={`${Math.round(k.success_rate * 100)}%`} sub={`${k.jobs_failed} failed of ${k.jobs_total}`} />
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <Section title="Spend over time" subtitle={`Daily cost by category, last ${days} days`} className="lg:col-span-2">
            <CostSeries data={d.series} />
          </Section>
          <Section title="Cost breakdown" subtitle="Share of total platform spend">
            <p className="mb-4 font-display text-3xl font-bold tabular-nums">{usd(k.total_cost_usd, 5)}</p>
            <ShareBar parts={parts} />
            <div className="mt-5 space-y-1.5 border-t border-edge pt-4 text-xs text-faint">
              <p>Unit prices (editable in .env)</p>
              <p>vCPU-hour {usd(d.config.pricing.vcpu_hour, 3)} · storage {usd(d.config.pricing.storage_gb_month, 3)}/GB-mo · egress {usd(d.config.pricing.egress_gb, 2)}/GB</p>
              <p>LLM {usd(d.config.pricing.llm_input_per_m, 2)} in / {usd(d.config.pricing.llm_output_per_m, 2)} out per 1M tokens</p>
            </div>
          </Section>
        </div>

        <Section title="Cost per video" subtitle="Processing time, resource usage and every cost line, per project" right={<Table2 size={16} className="text-faint" />}>
          <CostTable rows={d.projects} />
        </Section>

        <div className="grid gap-5 lg:grid-cols-2">
          <Section title="Processing jobs per day" subtitle="Analyse, find and render jobs">
            <DailyBars data={d.series} dataKey="jobs" name="Jobs" />
          </Section>
          <Section title="Processing time per day" subtitle="Total job wall-clock time">
            <DailyBars data={d.series} dataKey="processing_seconds" name="Processing" fmt={secs} color="var(--color-s3)" />
          </Section>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <Section title="Where processing time goes" subtitle="Total seconds per pipeline step">
            {d.processing.steps.length ? <HBars data={d.processing.steps.slice(0, 8)} labelKey="step" valueKey="seconds" fmt={secs} /> : <p className="text-sm text-faint">No jobs yet</p>}
          </Section>
          <Section title="Speed vs footage length" subtitle="One dot per analysis job">
            {d.processing.scatter.length ? <SpeedScatter data={d.processing.scatter} /> : <p className="text-sm text-faint">No analysis jobs yet</p>}
          </Section>
          <Section title="Job statistics" subtitle="By job type">
            <div className="space-y-3">
              {kinds.map(([kind, s]) => (
                <div key={kind} className="rounded-xl bg-panel-2 p-3">
                  <div className="flex items-center justify-between"><span className="font-semibold capitalize">{kind}</span><span className="text-xs text-faint">{s.count} jobs · {s.failed} failed</span></div>
                  <div className="mt-2 grid grid-cols-4 gap-2 text-xs">
                    <div><p className="text-faint">avg</p><p className="tabular-nums">{secs(s.avg_seconds)}</p></div>
                    <div><p className="text-faint">p95</p><p className="tabular-nums">{secs(s.p95_seconds)}</p></div>
                    <div><p className="text-faint">CPU</p><p className="tabular-nums">{secs(s.avg_cpu_seconds)}</p></div>
                    <div><p className="text-faint">RAM</p><p className="tabular-nums">{Math.round(s.avg_peak_ram_mb)} MB</p></div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <Section title="Activity heatmap" subtitle="Events by weekday and hour (server time)" className="lg:col-span-2">
            <Heatmap grid={d.heatmap} />
          </Section>
          <Section title="Shot finder quality" subtitle={`${d.finder.found} found · ${d.finder.missing} reported missing`}>
            <p className="kicker mb-1">Confidence of chosen clips</p>
            <Histogram data={d.finder.confidence_hist} name="Shots" />
            <p className="kicker mb-1 mt-3">Take quality of chosen clips</p>
            <Histogram data={d.finder.quality_hist} name="Shots" color="var(--color-s3)" />
          </Section>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <Section title="Activity feed" subtitle="Latest platform events" right={<Activity size={16} className="text-faint" />}>
            <ul className="max-h-[420px] space-y-1 overflow-y-auto pr-1">
              {d.activity.map((e) => (
                <li key={e.id} className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-white/[.02]">
                  <span className={clsx('chip mt-0.5 shrink-0', TYPE_COLOR[e.type.split('.')[0]] || 'bg-zinc-500/20 text-zinc-300')}>{e.type.split('.')[0]}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{e.message}</p>
                    <p className="truncate text-xs text-faint">{e.project || '—'} · {ago(e.created_at)}</p>
                  </div>
                </li>
              ))}
              {!d.activity.length && <li className="text-sm text-faint">No activity yet</li>}
            </ul>
          </Section>
          <div className="space-y-5">
            <Section title="System health" subtitle="This server, right now" right={<Server size={16} className="text-faint" />}>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  [Cpu, 'CPU', `${d.system.cpu_percent}%`, `${d.system.cpu_count} threads`],
                  [Gauge, 'RAM', `${d.system.ram_used_gb} GB`, `of ${d.system.ram_total_gb} GB`],
                  [HardDrive, 'Disk free', `${d.system.disk_free_gb} GB`, `stored ${mb(k.storage_bytes)}`],
                  [Loader2, 'Queue', `${d.system.running_jobs} / ${d.system.queued_jobs}`, 'running / queued'],
                ].map(([Icon, label, v, sub]) => (
                  <div key={label} className="rounded-xl bg-panel-2 p-3">
                    <p className="flex items-center gap-1.5 text-faint"><Icon size={13} /><span className="kicker">{label}</span></p>
                    <p className="mt-1 font-semibold tabular-nums">{v}</p><p className="text-[11px] text-faint">{sub}</p>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-faint">Models: {d.config.vision} · Whisper {d.config.speech} · {d.config.llm}</p>
            </Section>
            <Section title="Recent jobs">
              <div className="max-h-[260px] overflow-auto">
                <table className="w-full min-w-[460px] text-sm">
                  <tbody>
                    {d.recent_jobs.map((j) => (
                      <tr key={j.id} className="border-b border-edge/60">
                        <td className="py-2 pr-2 capitalize">{j.kind}</td>
                        <td className="max-w-[160px] truncate py-2 pr-2 text-dim">{j.project}</td>
                        <td className="py-2 pr-2"><StatusLabel status={j.status} /></td>
                        <td className="py-2 pr-2 text-right tabular-nums text-dim">{j.status === 'running' ? `${Math.round(j.progress * 100)}%` : secs(j.wall_seconds)}</td>
                        <td className="py-2 text-right text-xs text-faint">{ago(j.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>
        </div>
      </main>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(true)
  return authed ? <Dashboard onLogout={() => setAuthed(false)} /> : <Login onDone={() => setAuthed(true)} />
}
