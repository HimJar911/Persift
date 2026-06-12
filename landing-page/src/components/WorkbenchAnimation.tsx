import { useState, useEffect, useRef } from "react"
import { Wordmark } from "./Brand"

const COMPANIES = [
  { n: "Ramp",       c: "#8B89F2", role: "Software Engineer Intern", svg: '<line x1="6" y1="17" x2="6" y2="13"/><line x1="12" y1="17" x2="12" y2="9"/><line x1="18" y1="17" x2="18" y2="5"/>' },
  { n: "Notion",     c: "#E8B04B", role: "Growth Engineer",          svg: '<circle cx="9" cy="12" r="4.5" fill="none"/><circle cx="15" cy="12" r="4.5" fill="none"/>' },
  { n: "Linear",     c: "#7A78E0", role: "Product Engineer",         svg: '<path d="M5 14 L12 5 L19 14" fill="none"/><line x1="8" y1="18" x2="16" y2="18"/>' },
  { n: "Figma",      c: "#E2725B", role: "Frontend Engineer",        svg: '<circle cx="9" cy="8" r="3.2"/><circle cx="9" cy="15" r="3.2"/><circle cx="15" cy="8" r="3.2" fill="none"/>' },
  { n: "Stripe",     c: "#6E8BE0", role: "Backend Engineer",         svg: '<path d="M7 8 Q14 8 14 11 Q14 14 7 14 Q14 14 14 17" fill="none"/>' },
  { n: "DoorDash",   c: "#E04B3A", role: "Full Stack Engineer",      svg: '<path d="M5 14 L12 14 L9 18 Z"/><path d="M19 10 L12 10 L15 6 Z"/>' },
  { n: "Databricks", c: "#E89B4B", role: "ML Engineer Intern",       svg: '<path d="M5 9 L12 6 L19 9 L12 12 Z" fill="none"/><path d="M5 14 L12 17 L19 14" fill="none"/>' },
  { n: "Anthropic",  c: "#D4855E", role: "Software Engineer Intern", svg: '<path d="M7 18 L12 6 L17 18" fill="none"/><line x1="9" y1="14" x2="15" y2="14"/>' },
  { n: "Vercel",     c: "#B8B6C9", role: "Platform Engineer",        svg: '<path d="M12 6 L19 18 L5 18 Z" fill="none"/>' },
  { n: "Plaid",      c: "#9B97E8", role: "Backend Engineer",         svg: '<rect x="6" y="6" width="5" height="5" rx="1"/><rect x="13" y="13" width="5" height="5" rx="1"/><rect x="13" y="6" width="5" height="5" rx="1" fill="none"/>' },
  { n: "Airtable",   c: "#E8B84B", role: "Product Engineer",         svg: '<path d="M5 9 L12 6 L19 9 L12 12 Z"/><line x1="12" y1="12" x2="12" y2="18"/><line x1="19" y1="9" x2="19" y2="15"/>' },
  { n: "Retool",     c: "#6FA8E0", role: "Frontend Engineer",        svg: '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="none"/><line x1="6" y1="11" x2="18" y2="11"/><line x1="11" y1="11" x2="11" y2="18"/>' },
  { n: "Brex",       c: "#E0954B", role: "Software Engineer Intern", svg: '<path d="M7 7 L14 7 Q17 7 17 10 L17 17" fill="none"/><path d="M7 13 L13 13 Q16 13 16 16" fill="none"/>' },
  { n: "Scale AI",   c: "#7C7AE0", role: "ML Engineer Intern",       svg: '<line x1="7" y1="18" x2="7" y2="11"/><line x1="12" y1="18" x2="12" y2="6"/><line x1="17" y1="18" x2="17" y2="14"/><line x1="5" y1="9" x2="19" y2="5"/>' },
  { n: "Mercury",    c: "#5E9B9B", role: "Backend Engineer",         svg: '<circle cx="12" cy="12" r="6.5" fill="none"/><path d="M12 5.5 Q15 9 12 12 Q9 15 12 18.5" fill="none"/>' },
  { n: "Cursor",     c: "#C8C6D4", role: "Software Engineer Intern", svg: '<path d="M7 5 L7 17 L11 13 L14 19 L16 18 L13 12 L18 12 Z"/>' },
  { n: "Sentry",     c: "#9B6FD4", role: "Platform Engineer",        svg: '<path d="M12 5 L18 17 L6 17 Z" fill="none"/><circle cx="12" cy="13" r="2"/>' },
  { n: "Webflow",    c: "#4FB3C4", role: "Frontend Engineer",        svg: '<path d="M5 8 L8 16 L11 9 L14 16 L17 8" fill="none"/>' },
  { n: "Modal",      c: "#E07C5E", role: "ML Engineer Intern",       svg: '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="none"/><path d="M9 15 L9 9 L12 13 L15 9 L15 15" fill="none"/>' },
  { n: "Rippling",   c: "#5EA8C9", role: "Full Stack Engineer",      svg: '<circle cx="12" cy="12" r="2.5"/><circle cx="12" cy="12" r="6" fill="none" opacity="0.55"/>' },
]

const CYCLE_INTERVAL = 4200
const APPLYING_HOLD  = 2400
const START_COUNT    = 23
const MAX_ROWS       = 6
const SEED_COUNT     = 5

interface Row {
  id: number
  company: typeof COMPANIES[0]
  state: "applying" | "applied"
  stamp: string
}

let _id = 0

function fmtTime(d: Date) {
  let h = d.getHours()
  const m = d.getMinutes()
  const ap = h >= 12 ? "PM" : "AM"
  h = h % 12; if (h === 0) h = 12
  return `${h}:${String(m).padStart(2, "0")} ${ap}`
}

function hexToRgba(hex: string, a: number) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${a})`
}

function Tile({ co }: { co: typeof COMPANIES[0] }) {
  return (
    <div style={{
      width: 32, height: 32, borderRadius: 8, flexShrink: 0,
      background: hexToRgba(co.c, 0.14),
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <svg
        width="18" height="18" viewBox="0 0 24 24"
        fill={co.c} stroke={co.c}
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        dangerouslySetInnerHTML={{ __html: co.svg }}
      />
    </div>
  )
}

function Check({ visible }: { visible: boolean }) {
  return (
    <div style={{
      width: 15, height: 15, borderRadius: "50%",
      background: "#97C459",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      transform: visible ? "scale(1)" : "scale(0.2)",
      opacity: visible ? 1 : 0,
      transition: "transform 0.45s cubic-bezier(0.34,1.56,0.64,1), opacity 0.3s ease",
    }}>
      <svg width="9" height="9" viewBox="0 0 24 24" fill="none"
        stroke="#1a1816" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
        <path
          d="M5 12l5 5L20 7"
          strokeDasharray="24"
          strokeDashoffset={visible ? 0 : 24}
          style={{ transition: "stroke-dashoffset 0.4s ease 0.15s" }}
        />
      </svg>
    </div>
  )
}

function AppRow({ row, visible }: { row: Row; visible: boolean }) {
  const applying = row.state === "applying"
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "11px 10px", borderRadius: 8,
      opacity: applying ? 1 : 0.62,
      background: applying ? "rgba(239,159,39,0.06)" : "transparent",
      transition: "opacity 0.5s ease, background 0.5s ease",
      maxHeight: visible ? 60 : 0,
      overflow: "hidden",
      transition2: "max-height 0.45s ease",
    } as React.CSSProperties}>
      <Tile co={row.company} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: "#f5f3ee", fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {row.company.n}
        </div>
        <div style={{ color: "rgba(245,243,238,0.4)", fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {row.company.role}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0, minWidth: 84, justifyContent: "flex-end" }}>
        {applying ? (
          <>
            <Spinner />
            <span style={{ fontSize: 12, fontWeight: 500, color: "#EF9F27" }}>Applying</span>
          </>
        ) : (
          <>
            <Check visible={!applying} />
            <span style={{ fontSize: 12, fontWeight: 500, color: "#97C459" }}>Applied</span>
          </>
        )}
      </div>
      <div style={{ color: "rgba(245,243,238,0.3)", fontSize: 11, flexShrink: 0, width: 52, textAlign: "right" }}>
        {applying ? "" : row.stamp}
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <div style={{
      width: 13, height: 13, borderRadius: "50%",
      border: "1.5px solid rgba(239,159,39,0.25)",
      borderTopColor: "#EF9F27",
      animation: "wb-spin 0.8s linear infinite",
      display: "inline-block",
    }} />
  )
}

export function WorkbenchAnimation() {
  const [rows,  setRows]  = useState<Row[]>(() => {
    const now = new Date()
    return Array.from({ length: SEED_COUNT }, (_, k) => ({
      id: _id++,
      company: COMPANIES[(k + 1) % COMPANIES.length],
      state: "applied" as const,
      stamp: fmtTime(now),
    }))
  })
  const [count,    setCount]    = useState(START_COUNT)
  const [clockStr, setClockStr] = useState(fmtTime(new Date()))
  const idxRef    = useRef(0)
  const cancelRef = useRef(false)

  useEffect(() => {
    const t = setInterval(() => setClockStr(fmtTime(new Date())), 15000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    cancelRef.current = false

    function cycle() {
      if (cancelRef.current) return
      const co = COMPANIES[idxRef.current % COMPANIES.length]
      const now = new Date()
      const stamp = fmtTime(now)
      const id = _id++

      setRows(prev => {
        const next = [{ id, company: co, state: "applying" as const, stamp }, ...prev]
        return next.slice(0, MAX_ROWS)
      })

      setTimeout(() => {
        if (cancelRef.current) return
        setRows(prev => prev.map(r => r.id === id ? { ...r, state: "applied" as const } : r))
        setCount(c => c >= 60 ? START_COUNT : c + 1)
      }, APPLYING_HOLD)

      idxRef.current++
    }

    const t1 = setTimeout(cycle, 700)
    const t2 = setInterval(cycle, CYCLE_INTERVAL)
    return () => {
      cancelRef.current = true
      clearTimeout(t1)
      clearInterval(t2)
    }
  }, [])

  return (
    <>
      <style>{`@keyframes wb-spin { to { transform: rotate(360deg); } }`}</style>
      <div style={{
        width: "100%", height: "100%",
        background: "#1a1816",
        display: "flex", flexDirection: "column",
        fontFamily: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`,
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 18px",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <Wordmark height={16} color="#f5f3ee" />
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#97C459", display: "block", flexShrink: 0 }} />
          </div>
          <span style={{ color: "rgba(245,243,238,0.45)", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
            {clockStr}
          </span>
        </div>

        {/* Counter */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "16px 18px 12px", flexShrink: 0 }}>
          <span style={{ color: "#EF9F27", fontSize: 28, fontWeight: 500, lineHeight: 1 }}>{count}</span>
          <span style={{ color: "rgba(245,243,238,0.45)", fontSize: 13 }}>applications submitted automatically</span>
        </div>

        {/* Feed */}
        <div style={{ padding: "0 10px 14px", display: "flex", flexDirection: "column", gap: 2, overflow: "hidden" }}>
          {rows.map(row => (
            <AppRow key={row.id} row={row} visible />
          ))}
        </div>
      </div>
    </>
  )
}
