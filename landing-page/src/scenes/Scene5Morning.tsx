import { motion, useTransform } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"
import { DashboardShell } from "../components/DashboardShell"
import { BrowserWindow } from "../components/BrowserWindow"
import { CopyLine } from "../components/CopyLine"

function StatCard({ value, label, accent }: { value: string; label: string; accent?: boolean }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        padding: "10px 12px",
        borderRadius: 12,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: 28,
          fontWeight: 600,
          lineHeight: 1,
          color: accent ? "var(--amber)" : "var(--ink)",
        }}
      >
        {value}
      </span>
      <span style={{ fontSize: 11.5, color: "var(--ink-mute)", letterSpacing: "0.01em" }}>{label}</span>
    </div>
  )
}

const QUEUE = [
  { company: "Figma", role: "Product Design Intern", match: 88, eta: "Applying in 4 min" },
  { company: "Notion", role: "SWE Intern", match: 85, eta: "Applying in 8 min" },
  { company: "Ramp", role: "Engineering Intern", match: 81, eta: "Applying in 12 min" },
]

function CompanyBadge({ name }: { name: string }) {
  return (
    <span
      style={{
        width: 30,
        height: 30,
        flexShrink: 0,
        borderRadius: 8,
        background: "linear-gradient(150deg, #2a2118, #1a140d)",
        border: "1px solid var(--line)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 13,
        fontWeight: 700,
        color: "var(--ink-soft)",
        fontFamily: "var(--font-serif)",
      }}
    >
      {name[0]}
    </span>
  )
}

function UpNext() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <span
        style={{
          fontSize: 11,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--ink-mute)",
        }}
      >
        Up next today
      </span>
      <div
        style={{
          borderRadius: 12,
          border: "1px solid var(--line)",
          background: "rgba(255,255,255,0.02)",
          overflow: "hidden",
        }}
      >
        {QUEUE.map((q, i) => (
          <div
            key={q.company}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "8px 14px",
              borderTop: i === 0 ? "none" : "1px solid var(--line)",
            }}
          >
            <CompanyBadge name={q.company} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>{q.company}</div>
              <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>{q.role}</div>
            </div>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                fontVariantNumeric: "tabular-nums",
                color: q.match >= 90 ? "var(--green)" : "var(--amber-soft)",
                flexShrink: 0,
              }}
            >
              {q.match}% match
            </span>
            <span
              style={{
                fontSize: 11.5,
                color: "var(--ink-soft)",
                fontVariantNumeric: "tabular-nums",
                flexShrink: 0,
                width: 96,
                textAlign: "right",
              }}
            >
              {q.eta}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Scene5Morning() {
  const p = useSceneProgress()
  const headY = useTransform(p, [0, 0.25], [16, 0])
  const headOpacity = useTransform(p, [0, 0.25], [0, 1])

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
      <motion.div style={{ opacity: headOpacity, y: headY, width: "100%", display: "flex", justifyContent: "center" }}>
        <BrowserWindow url="app.persift.app/dashboard" width="90vw" maxWidth={1040}>
          <DashboardShell activeTab="overview" tone="dawn" embedded maxHeight="calc(100vh - 200px)">
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <h3
                style={{
                  margin: 0,
                  fontFamily: "var(--font-serif)",
                  fontWeight: 500,
                  fontSize: 30,
                  letterSpacing: "-0.02em",
                  color: "var(--ink)",
                }}
              >
                Good morning.
              </h3>
              <p style={{ margin: "6px 0 0", fontSize: 14.5, color: "var(--ink-soft)" }}>
                You applied to <strong style={{ color: "var(--amber-soft)", fontWeight: 600 }}>8 jobs</strong>{" "}
                while you were sleeping.
              </p>
            </div>

            {/* stat cards */}
            <div style={{ display: "flex", gap: 10 }}>
              <StatCard value="8" label="Submitted" />
              <StatCard value="3" label="Responses" />
              <StatCard value="1" label="Needs you" accent />
              <StatCard value="12" label="In queue" />
            </div>

            {/* google calendar interview alert */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 13,
                padding: "10px 15px",
                borderRadius: 13,
                background: "linear-gradient(90deg, rgba(240,163,65,0.14), rgba(240,163,65,0.04))",
                border: "1px solid rgba(240,163,65,0.32)",
              }}
            >
              <span
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 9,
                  background: "linear-gradient(135deg, var(--amber), var(--amber-deep))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  color: "#1a1206",
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <rect x="3" y="4.5" width="18" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
                  <path d="M3 9h18" stroke="currentColor" strokeWidth="1.8" />
                  <path d="M8 3v3M16 3v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </span>
              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>
                  Interview scheduled
                </span>
                <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                  Stripe · Software Engineer Intern
                </span>
                <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                  Tomorrow · 2:00 PM · Google Meet
                </span>
                <span style={{ fontSize: 11.5, color: "var(--amber-soft)" }}>
                  Added to your Google Calendar
                </span>
              </div>
            </div>

            {/* up next today — the live queue */}
            <UpNext />
          </div>
        </DashboardShell>
        </BrowserWindow>
      </motion.div>

      <CopyLine from={0.55} to={0.8} size={16}>
        This is what Thursday morning looks like now.
      </CopyLine>
    </div>
  )
}
