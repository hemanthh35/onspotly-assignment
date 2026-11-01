import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Film, Plus, Clapperboard, Sparkles, ScanSearch, Scissors, Search } from 'lucide-react'
import { api } from '../api.js'
import { Empty, Pagination, StatusChip } from '../components/ui.jsx'

const STEPS = [
  { icon: Sparkles, title: 'Brief → shot list', text: 'AI turns a customer’s words into an ordered, editable shot list.' },
  { icon: ScanSearch, title: 'Finds the moments', text: 'Searches every clip by sight and sound, skips blurry or dark takes.' },
  { icon: Scissors, title: 'Rough cut in minutes', text: 'Review, reorder, trim, then download the reel or an editor file.' },
]

export default function Projects() {
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') || 1)
  const q = params.get('q') || ''
  const [search, setSearch] = useState(q)
  useEffect(() => {
    const t = setTimeout(() => setParams((s) => { search ? s.set('q', search) : s.delete('q'); s.delete('page'); return s }, { replace: true }), 300)
    return () => clearTimeout(t)
  }, [search]) // eslint-disable-line
  const { data: res, isLoading } = useQuery({
    queryKey: ['projects', page, q], queryFn: () => api.projects({ page, q }), refetchInterval: 8000, placeholderData: keepPreviousData,
  })
  const data = res?.items
  return (
    <div>
      <section className="relative overflow-hidden rounded-3xl bg-ink px-6 py-10 text-white sm:px-10 sm:py-14">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand/40 blur-3xl" />
        <p className="chip bg-white/10 text-white/80">Smart Rough Cut</p>
        <h1 className="mt-4 max-w-2xl text-3xl font-bold leading-tight sm:text-5xl">
          From raw footage to a <span className="text-brand">ready reel</span>, guided by the brief.
        </h1>
        <p className="mt-4 max-w-xl text-white/70">
          Drop the creator’s clips, paste what the customer asked for, and get a timed rough cut with a clip list your editor can finish.
        </p>
        <Link to="/new" className="btn-primary mt-7"><Plus size={16} /> Start a new reel</Link>
        <div className="mt-10 grid gap-3 sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
              <Icon size={18} className="text-brand" />
              <p className="mt-2 text-sm font-semibold">{title}</p>
              <p className="mt-1 text-xs leading-relaxed text-white/60">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="mb-4 mt-10 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold">Projects <span className="ml-1 text-sm font-medium text-muted">{res?.total ?? 0}</span></h2>
        <label className="flex w-full items-center gap-2 rounded-xl border border-line bg-white px-3 sm:w-72">
          <Search size={15} className="text-muted" />
          <input className="w-full bg-transparent py-2 text-sm outline-none" placeholder="Search projects or briefs" value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => <div key={i} className="card h-32 animate-pulse bg-stone-100" />)}
        </div>
      ) : !data?.length ? (
        <Empty icon={<Clapperboard size={22} />} title={q ? 'No matching projects' : 'No projects yet'}
          action={!q && <Link to="/new" className="btn-primary"><Plus size={16} /> New reel</Link>}>
          {q ? `Nothing matches “${q}”.` : 'Create a project, upload the footage and paste the customer’s brief.'}
        </Empty>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((p) => (
            <Link key={p.id} to={`/p/${p.id}`} className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-lg hover:shadow-ink/5">
              <div className="flex items-start justify-between gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ink text-white transition group-hover:bg-brand">
                  <Film size={18} />
                </span>
                <StatusChip status={p.status} />
              </div>
              <p className="mt-4 truncate font-display text-lg font-semibold">{p.name}</p>
              <p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted">{p.brief || 'No brief yet'}</p>
              <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                <span>{p.asset_count} clips · {Math.round(p.footage_seconds)}s footage</span>
                <span>{p.target_seconds}s · {p.aspect_ratio}</span>
                {p.version_count > 0 && <span>{p.version_count} version{p.version_count > 1 ? 's' : ''}</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
      {res && <div className="mt-6"><Pagination page={res.page} pages={res.pages} total={res.total} label="projects"
        onChange={(n) => { setParams((s) => { s.set('page', n); return s }); window.scrollTo({ top: 0, behavior: 'smooth' }) }} /></div>}
    </div>
  )
}
