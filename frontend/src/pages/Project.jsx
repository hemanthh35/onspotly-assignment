import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronDown, Trash2, Film, ListChecks, Clapperboard, Download } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../api.js'
import { StatusChip } from '../components/ui.jsx'
import FootageStep from '../components/project/FootageStep.jsx'
import ShotListStep from '../components/project/ShotListStep.jsx'
import EditorStep from '../components/project/EditorStep.jsx'
import ExportStep from '../components/project/ExportStep.jsx'

const TABS = [
  { id: 'footage', label: 'Footage', icon: Film },
  { id: 'shots', label: 'Shot list', icon: ListChecks },
  { id: 'editor', label: 'Editor', icon: Clapperboard },
  { id: 'export', label: 'Export', icon: Download },
]

export default function Project() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [briefOpen, setBriefOpen] = useState(false)
  const { data: p, isLoading, error } = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.project(id),
    refetchInterval: (q) => {
      const d = q.state.data
      const busy = d?.jobs?.some((j) => ['queued', 'running'].includes(j.status))
      return busy ? 1500 : 8000
    },
  })
  const tab = params.get('tab') || (p ? (p.runs.length ? 'editor' : p.shot_lists.length ? 'shots' : 'footage') : 'footage')
  const setTab = (t) => setParams((s) => { s.set('tab', t); return s }, { replace: true })
  const refresh = () => qc.invalidateQueries({ queryKey: ['project', id] })

  if (isLoading) return <div className="card h-40 animate-pulse bg-stone-100" />
  if (error) return <p className="text-brand">{error.message}</p>

  async function remove() {
    if (!confirm(`Delete “${p.name}” and all its files?`)) return
    await api.deleteProject(p.id)
    toast.success('Project deleted')
    nav('/')
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><StatusChip status={p.status} /><span className="text-xs text-muted">{p.target_seconds}s · {p.aspect_ratio}</span></div>
          <h1 className="mt-2 truncate text-2xl font-bold sm:text-3xl">{p.name}</h1>
        </div>
        <button onClick={remove} className="btn-ghost btn-sm text-muted hover:text-brand"><Trash2 size={14} /> Delete</button>
      </div>

      <button onClick={() => setBriefOpen((o) => !o)} className="card mt-4 w-full p-4 text-left">
        <div className="flex items-center justify-between">
          <span className="label mb-0">Customer brief</span>
          <ChevronDown size={16} className={clsx('text-muted transition', briefOpen && 'rotate-180')} />
        </div>
        <p className={clsx('mt-1.5 text-sm leading-relaxed text-ink/80', !briefOpen && 'line-clamp-2')}>{p.brief || 'No brief'}</p>
      </button>

      <nav className="scrollbar-none sticky top-14 z-20 -mx-4 mt-6 overflow-x-auto border-b border-line bg-paper/95 px-4 backdrop-blur sm:mx-0 sm:px-0">
        <div className="flex min-w-max gap-1">
          {TABS.map((t, i) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={clsx('flex items-center gap-2 border-b-2 px-3 py-3 text-sm font-semibold transition sm:px-4',
                tab === t.id ? 'border-brand text-ink' : 'border-transparent text-muted hover:text-ink')}>
              <span className={clsx('grid h-5 w-5 place-items-center rounded-full text-[11px]', tab === t.id ? 'bg-brand text-white' : 'bg-stone-200 text-muted')}>{i + 1}</span>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <div className="mt-6">
        {tab === 'footage' && <FootageStep project={p} refresh={refresh} next={() => setTab('shots')} />}
        {tab === 'shots' && <ShotListStep project={p} refresh={refresh} next={(runId) => setParams((s) => {
          s.set('tab', 'editor')
          if (runId) s.set('run', runId)
          return s
        }, { replace: true })} />}
        {tab === 'editor' && <EditorStep project={p} refresh={refresh} next={() => setTab('export')} goShots={() => setTab('shots')} />}
        {tab === 'export' && <ExportStep project={p} refresh={refresh} goEditor={() => setTab('editor')} />}
      </div>
    </div>
  )
}
