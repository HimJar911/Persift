import { useState } from "react"
import { motion, AnimatePresence, useTransform, useMotionValueEvent } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"
import { ExtensionPopup } from "../components/ExtensionPopup"

const TIMES = [
  "01:54 AM", "01:58 AM", "02:02 AM",
  "02:07 AM", "02:09 AM", "02:11 AM",
  "02:13 AM", "02:16 AM", "02:18 AM",
  "02:21 AM", "02:24 AM",
  "02:27 AM", "02:30 AM", "02:33 AM",
]

const C_FOUND    = "#f0a341"
const C_TAILORED = "#c084fc"
const C_APPLIED  = "#5fd07f"
const C_DIM      = "rgba(255,255,255,0.13)"

type Company = {
  name: string
  role: string
  match: number
  submittedTime: string
  foundIdx: number
  tailoredIdx: number
  submittedIdx: number
}

const COMPANIES: Company[] = [
  { name: "Stripe",    role: "Software Engineer Intern",  match: 94, submittedTime: "02:02 AM", foundIdx: 0,  tailoredIdx: 1,  submittedIdx: 2  },
  { name: "Anthropic", role: "Infrastructure Intern",     match: 91, submittedTime: "02:11 AM", foundIdx: 3,  tailoredIdx: 4,  submittedIdx: 5  },
  { name: "Figma",     role: "Design Engineer Intern",    match: 87, submittedTime: "02:18 AM", foundIdx: 6,  tailoredIdx: 7,  submittedIdx: 8  },
  { name: "Notion",    role: "Growth Intern",             match: 83, submittedTime: "02:24 AM", foundIdx: 9,  tailoredIdx: 9,  submittedIdx: 10 },
  { name: "Vercel",    role: "Frontend Engineer Intern",  match: 85, submittedTime: "",         foundIdx: 11, tailoredIdx: 12, submittedIdx: 99 },
]

const COL_ICON     = 16
const COL_PIPELINE = 61
const COL_MATCH    = 52
const COL_TIME     = 72
const ROW_GAP      = 10

function PipelineDots({ tailored, submitted, active }: { tailored: boolean; submitted: boolean; active: boolean }) {
  const d2 = tailored ? C_TAILORED : C_DIM
  const l1 = tailored ? "rgba(255,255,255,0.2)" : C_DIM
  const l2 = submitted ? "rgba(255,255,255,0.2)" : active ? "rgba(240,163,65,0.25)" : C_DIM

  return (
    <div style={{ width: COL_PIPELINE, display: "flex", alignItems: "center", gap: 3, flexShrink: 0 }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: C_FOUND, flexShrink: 0 }} />
      <span style={{ width: 14, height: 1, background: l1, flexShrink: 0 }} />
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: d2, flexShrink: 0 }} />
      <span style={{ width: 14, height: 1, background: l2, flexShrink: 0 }} />
      {active ? (
        <motion.span
          style={{ width: 7, height: 7, borderRadius: "50%", background: C_FOUND, flexShrink: 0, display: "inline-block" }}
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
        />
      ) : (
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: submitted ? C_APPLIED : C_DIM, flexShrink: 0 }} />
      )}
    </div>
  )
}

function CompanyRow({ c, clockIndex }: { c: Company; clockIndex: number }) {
  const tailored  = clockIndex >= c.tailoredIdx
  const submitted = clockIndex >= c.submittedIdx
  const active    = !submitted

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{
        display: "flex", alignItems: "center", gap: ROW_GAP,
        fontFamily: "var(--font-sans)", fontSize: 12.5,
        borderRadius: 8,
        padding: active ? "5px 6px" : "5px 6px",
        background: active ? "rgba(240,163,65,0.05)" : "transparent",
        border: active ? "1px solid rgba(240,163,65,0.14)" : "1px solid transparent",
        marginLeft: -6, marginRight: -6,
      }}
    >
      <span style={{ width: COL_ICON, flexShrink: 0, textAlign: "center", color: submitted ? C_APPLIED : C_FOUND, fontSize: 13 }}>
        {submitted ? "✓" : "→"}
      </span>

      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        <span style={{ color: "var(--ink)", fontWeight: 500 }}>{c.name}</span>
        {" "}<span style={{ color: "var(--ink-faint)" }}>— {c.role}</span>
      </span>

      <PipelineDots tailored={tailored} submitted={submitted} active={active} />

      <span
        style={{
          width: COL_MATCH,
          flexShrink: 0,
          textAlign: "center",
          fontSize: 10.5,
          fontWeight: 600,
          color: submitted ? "rgba(95,208,127,0.85)" : "var(--amber-soft)",
          padding: "2px 0",
          borderRadius: 999,
          border: submitted ? "1px solid rgba(95,208,127,0.3)" : "1px solid rgba(240,163,65,0.28)",
          background: submitted ? "rgba(95,208,127,0.08)" : "rgba(240,163,65,0.08)",
        }}
      >
        {c.match}%
      </span>

      <div style={{ width: COL_TIME, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 5 }}>
        {active ? (
          <>
            <motion.span
              animate={{ rotate: 360 }}
              transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
              style={{
                width: 9, height: 9, borderRadius: "50%",
                border: "1.5px solid rgba(240,163,65,0.3)",
                borderTopColor: C_FOUND,
                display: "inline-block", flexShrink: 0,
              }}
            />
            <span style={{ fontSize: 11, color: C_FOUND, fontWeight: 500, whiteSpace: "nowrap" }}>Applying</span>
          </>
        ) : (
          <span style={{ fontSize: 11, fontVariantNumeric: "tabular-nums", color: "var(--ink-mute)", whiteSpace: "nowrap" }}>
            {c.submittedTime}
          </span>
        )}
      </div>
    </motion.div>
  )
}

export function Scene4Overnight() {
  const p = useSceneProgress()

  const clockMV = useTransform(p, [0, 1], [0, TIMES.length - 1])
  const [clockIndex, setClockIndex] = useState(0)
  useMotionValueEvent(clockMV, "change", (v) => {
    const i = Math.min(TIMES.length - 1, Math.max(0, Math.round(v)))
    if (i !== clockIndex) setClockIndex(i)
  })

  const glowScale   = useTransform(p, [0, 0.5, 1], [0.92, 1.06, 0.96])
  const glowOpacity = useTransform(p, [0, 0.2, 0.85, 1], [0.5, 0.95, 0.95, 0.7])
  const asleepOpacity = useTransform(p, [0.05, 0.22], [0, 1])
  const asleepY       = useTransform(p, [0.05, 0.22], [18, 0])
  const isntOpacity   = useTransform(p, [0.18, 0.36], [0, 1])
  const isntY         = useTransform(p, [0.18, 0.36], [14, 0])

  // Only show companies that have been found; newest first (highest foundIdx on top)
  const visible = COMPANIES
    .filter(c => clockIndex >= c.foundIdx)
    .slice()
    .reverse()

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 20,
        padding: "0 24px",
      }}
    >
      <motion.div
        style={{
          position: "absolute",
          top: "50%", left: "50%",
          width: 900, height: 900,
          x: "-50%", y: "-50%",
          scale: glowScale,
          opacity: glowOpacity,
          background: "radial-gradient(circle, rgba(240,163,65,0.22) 0%, rgba(201,122,31,0.10) 32%, transparent 62%)",
          pointerEvents: "none",
        }}
      />

      <div style={{ position: "relative", textAlign: "center", zIndex: 2 }}>
        <motion.h2
          style={{
            opacity: asleepOpacity, y: asleepY,
            margin: 0,
            fontFamily: "var(--font-serif)",
            fontWeight: 500,
            fontSize: "clamp(34px, 7vw, 78px)",
            letterSpacing: "-0.02em",
            color: "var(--ink)",
            lineHeight: 1,
          }}
        >
          You&apos;re asleep.
        </motion.h2>
        <motion.p
          style={{
            opacity: isntOpacity, y: isntY,
            margin: "10px 0 0",
            fontFamily: "var(--font-serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: "clamp(26px, 4.5vw, 46px)",
            color: "var(--amber)",
            lineHeight: 1,
          }}
        >
          It isn&apos;t.
        </motion.p>
      </div>

      <div style={{ position: "relative", zIndex: 2 }}>
        <ExtensionPopup status="applying" statusLabel="Applying" pulse toggleOn footnote="Auto-apply" width={500}>
          <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>

            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--ink-mute)" }}>
                Tonight · {TIMES[clockIndex]}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: "var(--font-sans)" }}>
                {([["Found", C_FOUND], ["Tailored", C_TAILORED], ["Applied", C_APPLIED]] as const).map(([label, color]) => (
                  <span key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
                    <span style={{ fontSize: 11, fontWeight: 500, color: "var(--ink-soft)" }}>{label}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* Company rows — newest on top, completed sink to bottom */}
            <AnimatePresence initial={false}>
              {visible.map((c) => (
                <CompanyRow key={c.name} c={c} clockIndex={clockIndex} />
              ))}
            </AnimatePresence>

          </div>
        </ExtensionPopup>
      </div>
    </div>
  )
}
