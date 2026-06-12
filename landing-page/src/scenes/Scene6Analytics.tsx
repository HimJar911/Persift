import { motion, useTransform, type MotionValue } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"
import { useIsMobile } from "../hooks/useIsMobile"
import { DashboardShell } from "../components/DashboardShell"
import { BrowserWindow } from "../components/BrowserWindow"
import { CopyLine } from "../components/CopyLine"

const BARS = [3, 5, 4, 6, 5, 8, 7, 9, 6, 8, 11, 9, 12, 10, 13, 9, 14, 12, 11, 15]
const BAR_MAX = Math.max(...BARS)

function ChartBar({
  value,
  index,
  grow,
  highlight,
}: {
  value: number
  index: number
  grow: MotionValue<number>
  highlight: boolean
}) {
  const h = useTransform(grow, (g) => `${(value / BAR_MAX) * 100 * Math.min(1, g * (1 + index * 0.02))}%`)
  return (
    <motion.div
      style={{
        flex: 1,
        height: h,
        minHeight: 3,
        borderRadius: 3,
        background: highlight
          ? "linear-gradient(180deg, var(--amber-soft), var(--amber-deep))"
          : "linear-gradient(180deg, #4a3b29, #2e261d)",
      }}
    />
  )
}

function TimelineChart() {
  const p = useSceneProgress()
  // bars grow as the chart "draws" with scroll
  const grow = useTransform(p, [0.08, 0.5], [0, 1])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>
          Applications · last 30 days
        </span>
        <span style={{ fontSize: 11.5, color: "var(--amber-soft)", fontWeight: 600 }}>+38% vs last month</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 5, height: 100 }}>
        {BARS.map((b, i) => (
          <ChartBar key={i} value={b} index={i} grow={grow} highlight={i >= BARS.length - 4} />
        ))}
      </div>
    </div>
  )
}

function MiniStat({
  title,
  value,
  sub,
  accent,
}: {
  title: string
  value: string
  sub: string
  accent?: boolean
}) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        padding: "13px 14px",
        borderRadius: 12,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <span style={{ fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
        {title}
      </span>
      <span
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: 21,
          fontWeight: 600,
          color: accent ? "var(--amber)" : "var(--ink)",
          lineHeight: 1.1,
        }}
      >
        {value}
      </span>
      <span style={{ fontSize: 11.5, color: "var(--ink-mute)", lineHeight: 1.35 }}>{sub}</span>
    </div>
  )
}

type Row = {
  company: string
  role: string
  ats: string
  status: "Interview" | "Under review" | "Reviewing" | "No response" | "Rejected"
  response: string
}

const ROWS: Row[] = [
  { company: "Stripe", role: "SWE Intern", ats: "Greenhouse", status: "Interview", response: "3 days" },
  { company: "Anthropic", role: "Infra Intern", ats: "Ashby", status: "Under review", response: "8 days" },
  { company: "Figma", role: "Design Intern", ats: "Greenhouse", status: "No response", response: "14 days" },
  { company: "Linear", role: "Eng Intern", ats: "Custom", status: "Reviewing", response: "5 days" },
]

function statusColor(status: Row["status"]) {
  switch (status) {
    case "Interview":
      return "var(--green)"
    case "Under review":
    case "Reviewing":
      return "var(--amber-soft)"
    case "Rejected":
      return "#b15b54"
    default:
      return "var(--ink-mute)"
  }
}

function ApplicationsTable() {
  const isMobile = useIsMobile()
  // mobile: Company, Role, Status only. desktop: full set.
  const cols = isMobile ? "1.1fr 1.2fr 1fr" : "1.3fr 1.4fr 1fr 1fr 0.7fr"
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>Recent applications</span>
      <div
        style={{
          borderRadius: 12,
          border: "1px solid var(--line)",
          background: "rgba(255,255,255,0.02)",
          overflow: "hidden",
        }}
      >
        {/* header */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: cols,
            gap: isMobile ? 8 : 12,
            padding: "9px 14px",
            borderBottom: "1px solid var(--line)",
            fontSize: 10.5,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "var(--ink-faint)",
          }}
        >
          <span>Company</span>
          <span>Role</span>
          {!isMobile && <span>ATS</span>}
          <span>Status</span>
          {!isMobile && <span style={{ textAlign: "right" }}>Response</span>}
        </div>
        {ROWS.map((r, i) => (
          <div
            key={r.company}
            style={{
              display: "grid",
              gridTemplateColumns: cols,
              gap: isMobile ? 8 : 12,
              alignItems: "center",
              padding: "10px 14px",
              borderTop: i === 0 ? "none" : "1px solid rgba(255,255,255,0.04)",
              fontSize: 12.5,
            }}
          >
            <span style={{ color: "var(--ink)", fontWeight: 600 }}>{r.company}</span>
            <span style={{ color: "var(--ink-soft)" }}>{r.role}</span>
            {!isMobile && <span style={{ color: "var(--ink-mute)" }}>{r.ats}</span>}
            <span style={{ color: statusColor(r.status), fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
              {r.status}
              {r.status === "Interview" && <span aria-hidden="true">✓</span>}
            </span>
            {!isMobile && (
              <span
                style={{
                  color: "var(--ink-mute)",
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {r.response}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Scene6Analytics() {
  const p = useSceneProgress()
  const isMobile = useIsMobile()
  const opacity = useTransform(p, [0, 0.22], [0, 1])
  const y = useTransform(p, [0, 0.22], [16, 0])

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-start",
        gap: 26,
        padding: "24px 24px 0",
        width: "100%",
        height: "100%",
      }}
    >
      <motion.div style={{ opacity, y, width: "100%", display: "flex", justifyContent: "center" }}>
        <BrowserWindow url="app.persift.app/analytics" width="90vw" maxWidth={1040}>
          <DashboardShell activeTab="analytics" tone="day" embedded maxHeight="calc(100vh - 200px)">
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <TimelineChart />

              <div
                style={
                  isMobile
                    ? { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }
                    : { display: "flex", gap: 12, flexWrap: "wrap" }
                }
              >
                <MiniStat title="Response rate" value="19%" sub="up from 11% last month" accent />
                <MiniStat title="By ATS" value="2× faster" sub="Greenhouse vs Workday for you" />
                <MiniStat title="Gone quiet" value="6 roles" sub="silent 3+ weeks · likely passed" />
                <MiniStat title="Best performing" value="Infra Intern" sub="most replies of any title" />
              </div>

              <ApplicationsTable />
            </div>
          </DashboardShell>
        </BrowserWindow>
      </motion.div>

      <CopyLine from={0.55} to={0.8} size={16}>
        Finally know what&apos;s actually working.
      </CopyLine>
    </div>
  )
}
