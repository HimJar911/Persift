import { useState } from "react"
import { motion, useTransform, useMotionValueEvent } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"

// Left column: identity + resume
const IDENTITY_FIELDS = [
  { label: "NAME",        value: "Jordan Reyes",   band: [0.04, 0.11] },
  { label: "UNIVERSITY",  value: "UC Berkeley",     band: [0.11, 0.18] },
  { label: "GRADUATION",  value: "May 2027",        band: [0.18, 0.24] },
  { label: "VISA STATUS", value: "U.S. Citizen",    band: [0.24, 0.30] },
]

// Right column: preferences
const PREF_FIELDS = [
  { label: "ROLE TYPES",  value: "SWE Intern · Data Intern", band: [0.32, 0.40] },
  { label: "LOCATIONS",   value: "Remote · SF · NYC",         band: [0.40, 0.47] },
  { label: "MIN MATCH",   value: "75%",                       band: [0.47, 0.52] },
]

const CHECKS = [
  { label: "Resume uploaded", at: 0.56 },
  { label: "Preferences set", at: 0.62 },
  { label: "Ready to run",    at: 0.68 },
]

const TOGGLE_ON_AT = 0.78
const RESUME_AT    = 0.52

function TypedField({ label, value, fillStart, fillEnd, p }: {
  label: string; value: string; fillStart: number; fillEnd: number
  p: ReturnType<typeof useSceneProgress>
}) {
  const typed = useTransform(p, (v) => {
    const frac = Math.max(0, Math.min(1, (v - fillStart) / (fillEnd - fillStart)))
    return value.slice(0, Math.round(value.length * frac))
  })
  const caretOpacity = useTransform(p, (v) => {
    const frac = (v - fillStart) / (fillEnd - fillStart)
    return frac > 0 && frac < 1 ? 1 : 0
  })
  const checkOpacity = useTransform(p, (v) => v >= fillEnd ? 1 : 0)
  const placeholderOpacity = useTransform(p, (v) => v < fillStart ? 1 : 0)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 9, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
        {label}
      </span>
      <div style={{
        height: 34, borderRadius: 8,
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--line)",
        display: "flex", alignItems: "center",
        padding: "0 10px", gap: 4,
        position: "relative",
      }}>
        <motion.span style={{ fontSize: 12.5, color: "var(--ink-faint)", fontStyle: "italic", flex: 1, minWidth: 0, opacity: placeholderOpacity, position: "absolute", pointerEvents: "none" }}>
          {label.toLowerCase()}
        </motion.span>
        <motion.span style={{ fontSize: 12.5, color: "var(--ink)", fontWeight: 500, flex: 1, minWidth: 0 }}>
          {typed}
        </motion.span>
        <motion.span style={{
          opacity: caretOpacity, display: "inline-block",
          width: 1.5, height: 13, background: "var(--amber)", flexShrink: 0,
        }} />
        <motion.span style={{ opacity: checkOpacity, flexShrink: 0 }}>
          <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke="var(--green)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </motion.span>
      </div>
    </div>
  )
}

function CheckItem({ label, at, p }: { label: string; at: number; p: ReturnType<typeof useSceneProgress> }) {
  const opacity = useTransform(p, [at, at + 0.04], [0, 1])
  const y = useTransform(p, [at, at + 0.04], [6, 0])
  return (
    <motion.div style={{ opacity, y, display: "flex", alignItems: "center", gap: 9, padding: "8px 10px", borderRadius: 9, background: "rgba(255,255,255,0.025)", border: "1px solid var(--line)" }}>
      <span style={{
        width: 16, height: 16, borderRadius: "50%",
        background: "rgba(95,208,127,0.15)",
        display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
          <path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke="var(--green)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span style={{ fontSize: 12, color: "var(--ink)", fontWeight: 500 }}>{label}</span>
    </motion.div>
  )
}

export function Scene2Setup() {
  const p = useSceneProgress()

  const resumeOpacity = useTransform(p, [RESUME_AT, RESUME_AT + 0.04], [0, 1])
  const toggleOpacity = useTransform(p, [TOGGLE_ON_AT - 0.04, TOGGLE_ON_AT], [0, 1])
  const toggleY = useTransform(p, [TOGGLE_ON_AT - 0.04, TOGGLE_ON_AT], [8, 0])

  const [isOn, setIsOn] = useState(false)
  useMotionValueEvent(p, "change", (v) => setIsOn(v >= TOGGLE_ON_AT))

  return (
    <div style={{
      width: "100%", height: "100%",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "20px 32px",
      boxSizing: "border-box",
      gap: 20,
    }}>
      {/* Section headline */}
      <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 8 }}>
        <h3 style={{
          margin: 0,
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          fontWeight: 800,
          fontSize: "clamp(26px, 3.5vw, 42px)",
          letterSpacing: "-0.025em",
          color: "var(--ink)",
        }}>
          Tell it what you&apos;re looking for.
        </h3>
        <p style={{
          margin: 0,
          fontFamily: "Inter, sans-serif",
          fontWeight: 400,
          fontSize: "clamp(13px, 1.3vw, 16px)",
          color: "var(--ink-soft)",
        }}>
          Once. Persift handles every application from here.
        </p>
      </div>
      <div style={{
        width: "100%",
        maxWidth: 780,
        borderRadius: 18,
        background: "linear-gradient(180deg, #1a150f, #14100b)",
        border: "1px solid var(--line)",
        boxShadow: "0 30px 60px -24px rgba(0,0,0,0.8), 0 8px 24px -12px rgba(0,0,0,0.6)",
        fontFamily: "var(--font-sans)",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "13px 20px",
          borderBottom: "1px solid var(--line)",
          background: "rgba(255,255,255,0.015)",
        }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>Your profile</span>
        </div>

        {/* Two-column body */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 0,
          padding: "20px 20px 20px",
        }}>
          {/* LEFT — identity + resume */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, paddingRight: 24 }}>
            <span style={{ fontSize: 9, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
              About you
            </span>
            {IDENTITY_FIELDS.map((f) => (
              <TypedField key={f.label} label={f.label} value={f.value}
                fillStart={f.band[0]} fillEnd={f.band[1]} p={p} />
            ))}

            {/* Resume */}
            <motion.div style={{ opacity: resumeOpacity, display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
              <span style={{ fontSize: 9, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
                Resume
              </span>
              <div style={{
                display: "flex", alignItems: "center", gap: 9,
                padding: "9px 10px", borderRadius: 9,
                background: "rgba(255,255,255,0.025)", border: "1px solid var(--line)",
              }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--amber)", flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: "var(--ink)", flex: 1 }}>resume_v12_final.pdf</span>
                <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
                  <path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke="var(--green)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </motion.div>
          </div>

          {/* RIGHT — preferences + checklist + toggle */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, paddingLeft: 24, borderLeft: "1px solid var(--line)" }}>
            <span style={{ fontSize: 9, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
              Job preferences
            </span>
            {PREF_FIELDS.map((f) => (
              <TypedField key={f.label} label={f.label} value={f.value}
                fillStart={f.band[0]} fillEnd={f.band[1]} p={p} />
            ))}

            {/* Checklist */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
              {CHECKS.map((c) => (
                <CheckItem key={c.label} label={c.label} at={c.at} p={p} />
              ))}
            </div>

            {/* Auto-apply toggle */}
            <motion.div style={{
              opacity: toggleOpacity,
              y: toggleY,
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "11px 12px", borderRadius: 11,
              background: isOn ? "rgba(240,163,65,0.08)" : "rgba(255,255,255,0.025)",
              border: `1px solid ${isOn ? "rgba(240,163,65,0.3)" : "var(--line)"}`,
              transition: "background 0.4s, border-color 0.4s",
              marginTop: 2,
            }}>
              <div>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: isOn ? "var(--amber-soft)" : "var(--ink)" }}>
                  Auto-apply
                </div>
                <div style={{ fontSize: 10.5, color: isOn ? "var(--amber)" : "var(--ink-mute)", marginTop: 1 }}>
                  {isOn ? "Persift is running" : "Off"}
                </div>
              </div>
              <div style={{
                width: 40, height: 22, borderRadius: 11,
                background: isOn ? "var(--amber)" : "rgba(255,255,255,0.1)",
                position: "relative", flexShrink: 0,
                transition: "background 0.3s",
              }}>
                <motion.div
                  animate={{ x: isOn ? 20 : 2 }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  style={{
                    position: "absolute", top: 2,
                    width: 18, height: 18, borderRadius: "50%",
                    background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
                  }}
                />
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  )
}
