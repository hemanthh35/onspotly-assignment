import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { Plus, LayoutGrid } from 'lucide-react'
import Projects from './pages/Projects.jsx'
import NewProject from './pages/NewProject.jsx'
import Project from './pages/Project.jsx'

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 fill-white"><path d="M4 2.5v11l9-5.5z" /></svg>
      </span>
      <span className="font-display text-[17px] font-bold tracking-tight text-white">
        OnSpotly <span className="font-medium text-white/50">Studio</span>
      </span>
    </Link>
  )
}

export default function App() {
  const { pathname } = useLocation()
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 bg-ink/95 backdrop-blur supports-[backdrop-filter]:bg-ink/85">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <nav className="flex items-center gap-1.5">
            <Link to="/" className={`btn btn-sm ${pathname === '/' ? 'bg-white/10 text-white' : 'text-white/70 hover:text-white'}`}>
              <LayoutGrid size={15} /> <span className="hidden sm:inline">Projects</span>
            </Link>
            <Link to="/new" className="btn-primary btn-sm">
              <Plus size={15} /> New reel
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-24 pt-6 sm:px-6 sm:pt-10">
        <Routes>
          <Route path="/" element={<Projects />} />
          <Route path="/new" element={<NewProject />} />
          <Route path="/p/:id/*" element={<Project />} />
        </Routes>
      </main>
    </div>
  )
}
