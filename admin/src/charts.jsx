/* Chart building blocks. Thin marks, rounded data-ends, recessive grid, hover tooltips. */
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { useState } from 'react'

export const SERIES = {
  compute: { color: 'var(--color-s1)', label: 'Compute' },
  llm: { color: 'var(--color-s2)', label: 'LLM' },
  storage: { color: 'var(--color-s3)', label: 'Storage' },
  egress: { color: 'var(--color-s4)', label: 'Egress' },
}

export const usd = (v, d = 4) => (v == null ? '–' : v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(d)}`)
export const secs = (v) => (v == null ? '–' : v >= 3600 ? `${(v / 3600).toFixed(1)}h` : v >= 60 ? `${(v / 60).toFixed(1)}m` : `${v.toFixed(1)}s`)

const axis = { stroke: 'transparent', tick: { fill: '#71717a', fontSize: 11 }, tickLine: false }
const grid = <CartesianGrid stroke="#2a2a2e" strokeDasharray="0" vertical={false} />

export function TooltipBox({ active, payload, label, fmt = (v) => v, labelFmt = (l) => l }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-edge bg-panel-2/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <p className="mb-1 font-semibold text-fg">{labelFmt(label)}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-dim">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color || p.fill }} />
          <span className="flex-1">{p.name}</span>
          <span className="font-semibold tabular-nums text-fg">{fmt(p.value, p.dataKey)}</span>
        </p>
      ))}
    </div>
  )
}

export function Legend({ keys }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-dim">
      {keys.map((k) => (
        <span key={k} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[k].color }} />{SERIES[k].label}</span>
      ))}
    </div>
  )
}

const shortDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

/** Stacked daily cost by category. */
export function CostSeries({ data }) {
  const keys = ['compute', 'llm', 'storage', 'egress']
  return (
    <div>
      <Legend keys={keys} />
      <div className="mt-3 h-56">
        <ResponsiveContainer>
          <BarChart data={data} barCategoryGap="25%">
            {grid}
            <XAxis dataKey="date" {...axis} tickFormatter={shortDate} minTickGap={24} />
            <YAxis {...axis} width={56} tickFormatter={(v) => usd(v, 3)} />
            <Tooltip cursor={{ fill: '#ffffff08' }} content={<TooltipBox fmt={(v) => usd(v, 5)} labelFmt={shortDate} />} />
            {keys.map((k, i) => (
              <Bar key={k} dataKey={k} name={SERIES[k].label} stackId="c" fill={SERIES[k].color}
                stroke="var(--color-panel)" strokeWidth={2} radius={i === keys.length - 1 ? [4, 4, 0, 0] : 0} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** Single-series daily bars (jobs, processing seconds...). */
export function DailyBars({ data, dataKey, name, fmt = (v) => v, color = 'var(--color-s1)' }) {
  return (
    <div className="h-48">
      <ResponsiveContainer>
        <BarChart data={data} barCategoryGap="25%">
          {grid}
          <XAxis dataKey="date" {...axis} tickFormatter={shortDate} minTickGap={24} />
          <YAxis {...axis} width={40} tickFormatter={fmt} allowDecimals={false} />
          <Tooltip cursor={{ fill: '#ffffff08' }} content={<TooltipBox fmt={fmt} labelFmt={shortDate} />} />
          <Bar dataKey={dataKey} name={name} fill={color} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Horizontal bars for a ranked breakdown (one series, so no legend). */
export function HBars({ data, labelKey, valueKey, fmt, color = 'var(--color-s1)', height }) {
  return (
    <div style={{ height: height || Math.max(120, data.length * 34) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" barCategoryGap="28%" margin={{ left: 4, right: 24 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey={labelKey} {...axis} width={110} tick={{ fill: '#a1a1aa', fontSize: 12 }} />
          <Tooltip cursor={{ fill: '#ffffff08' }} content={<TooltipBox fmt={fmt} />} />
          <Bar dataKey={valueKey} name="Value" fill={color} radius={[0, 4, 4, 0]}
            label={{ position: 'right', fill: '#a1a1aa', fontSize: 11, formatter: fmt }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function Histogram({ data, name, color = 'var(--color-s1)' }) {
  return (
    <div className="h-40">
      <ResponsiveContainer>
        <BarChart data={data} barCategoryGap="12%">
          {grid}
          <XAxis dataKey="bucket" {...axis} />
          <YAxis {...axis} width={28} allowDecimals={false} />
          <Tooltip cursor={{ fill: '#ffffff08' }} content={<TooltipBox labelFmt={(l) => `${l}–${(+l + 0.1).toFixed(1)}`} />} />
          <Bar dataKey="count" name={name} fill={color} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function SpeedScatter({ data }) {
  return (
    <div className="h-56">
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 8, right: 12 }}>
          {grid}
          <XAxis type="number" dataKey="footage_seconds" name="Footage" unit="s" {...axis} />
          <YAxis type="number" dataKey="processing_seconds" name="Processing" unit="s" {...axis} width={44} />
          <ZAxis range={[90, 90]} />
          <Tooltip cursor={{ stroke: '#3f3f46' }} content={({ active, payload }) => active && payload?.length ? (
            <div className="rounded-xl border border-edge bg-panel-2 px-3 py-2 text-xs">
              <p className="font-semibold">{payload[0].payload.project}</p>
              <p className="text-dim">{payload[0].payload.footage_seconds}s footage → {payload[0].payload.processing_seconds}s processing</p>
            </div>) : null} />
          <Scatter data={data} fill="var(--color-s1)" stroke="var(--color-panel)" strokeWidth={2} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Weekday x hour activity heatmap, single-hue sequential (brand red). */
export function Heatmap({ grid: cells }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(1, ...cells.flat())
  return (
    <div>
      <div className="scrollbar-none overflow-x-auto">
        <div className="min-w-[560px]">
          <div className="grid grid-cols-[36px_repeat(24,minmax(0,1fr))] gap-[2px]">
            <span />
            {Array.from({ length: 24 }, (_, h) => <span key={h} className="text-center text-[10px] text-faint">{h % 3 === 0 ? h : ''}</span>)}
            {cells.map((row, d) => [
              <span key={`l${d}`} className="pr-1 text-right text-[11px] leading-5 text-faint">{DAYS[d]}</span>,
              ...row.map((v, h) => (
                <button key={`${d}-${h}`} type="button" aria-label={`${DAYS[d]} ${h}:00, ${v} events`}
                  onMouseEnter={() => setHover({ d, h, v })} onFocus={() => setHover({ d, h, v })} onMouseLeave={() => setHover(null)}
                  className="h-5 rounded-[4px] outline-none ring-fg focus-visible:ring-2"
                  style={{ background: v ? `rgba(225, 29, 46, ${0.18 + 0.82 * (v / max)})` : '#1f1f23' }} />
              )),
            ])}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-faint">
        <span>{hover ? <><b className="text-fg">{hover.v}</b> events · {DAYS[hover.d]} {String(hover.h).padStart(2, '0')}:00</> : 'Hover a cell for details'}</span>
        <span className="flex items-center gap-1.5">less
          {[0.18, 0.4, 0.6, 0.8, 1].map((o) => <span key={o} className="h-3 w-3 rounded-[3px]" style={{ background: `rgba(225,29,46,${o})` }} />)} more</span>
      </div>
    </div>
  )
}

/** Share-of-total as one stacked bar with labelled parts (instead of a pie). */
export function ShareBar({ parts }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  return (
    <div>
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-full">
        {parts.filter((p) => p.value > 0).map((p) => (
          <div key={p.key} title={`${p.label}: ${p.fmt}`} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {parts.map((p) => (
          <div key={p.key} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
            <span className="text-dim">{p.label}</span>
            <span className="ml-auto font-semibold tabular-nums">{p.fmt}</span>
            <span className="w-9 text-right tabular-nums text-faint">{Math.round((p.value / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export { Cell }
