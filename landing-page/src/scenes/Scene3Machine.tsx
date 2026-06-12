import { useState } from "react"
import { motion, useTransform, useMotionValueEvent, type MotionValue } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"
import { useIsMobile } from "../hooks/useIsMobile"
import { ExtensionPopup } from "../components/ExtensionPopup"
import { SurfaceFrame } from "../components/Surfaces"
import { PersiftMark } from "../components/Brand"

type Ats = "greenhouse" | "ashby" | "custom"

type Company = {
  name: string
  role: string
  match: number
  ats: Ats
  formTitle: string
  essay: string
  tailorBullets: string[]
}

const PIPELINE: Company[] = [
  {
    name: "Stripe",
    role: "Software Engineer Intern",
    match: 94,
    ats: "greenhouse",
    formTitle: "Software Engineer Intern — Stripe · Application",
    essay:
      "I want to build payments infrastructure that millions of businesses rely on, and I care about correctness under scale.",
    tailorBullets: [
      "Built a fault-tolerant ledger service handling 12k req/s",
      "Reduced API p99 latency by 38% with request batching",
    ],
  },
  {
    name: "Anthropic",
    role: "Infrastructure Intern",
    match: 91,
    ats: "ashby",
    formTitle: "Infrastructure Intern — Anthropic · Application",
    essay:
      "I'm drawn to building reliable infrastructure for constitutional AI at scale, where safety-conscious engineering and distributed systems meet.",
    tailorBullets: [
      "Distributed training orchestration across 64-GPU clusters",
      "Safety-conscious rollout tooling with staged guardrails",
      "Infra scale: petabyte-range checkpoint pipelines",
    ],
  },
  {
    name: "Figma",
    role: "Design Engineer Intern",
    match: 87,
    ats: "greenhouse",
    formTitle: "Design Engineer Intern — Figma · Application",
    essay:
      "I want to work at the intersection of design and engineering — building tools that make creativity more accessible is exactly the kind of problem I care about.",
    tailorBullets: [
      "Built a component library used by 200+ designers daily",
      "Improved canvas rendering performance by 40% via reflow batching",
    ],
  },
]

function Logo({ name }: { name: string }) {
  return (
    <span
      style={{
        width: 28,
        height: 28,
        borderRadius: 7,
        flexShrink: 0,
        background: "linear-gradient(135deg, #3a2c1c, #241a12)",
        border: "1px solid var(--line)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 12,
        fontWeight: 700,
        color: "var(--amber-soft)",
        fontFamily: "var(--font-serif)",
      }}
    >
      {name[0]}
    </span>
  )
}

/* ====================================================================== */
/* role discovery card — the opening beat (Change 5)                       */
/* ====================================================================== */

function DiscoveryCard({ mv }: { mv: MotionValue<number> }) {
  // internal motion so the beat never feels frozen during its hold
  const fitWidth = useTransform(mv, [0.08, 0.24], ["0%", "100%"], { clamp: true })
  const matchOpacity = useTransform(mv, [0.20, 0.28], [0, 1])
  const linkedinOpacity = useTransform(mv, [0.24, 0.30], [0, 1])

  return (
    <div
      style={{
        width: 420,
        maxWidth: "90vw",
        borderRadius: 16,
        background: "linear-gradient(180deg, #211a13, #181109)",
        border: "1px solid rgba(240,163,65,0.32)",
        boxShadow: "0 30px 70px -30px rgba(0,0,0,0.85), 0 0 0 4px rgba(240,163,65,0.06)",
        padding: "22px 24px",
        fontFamily: "var(--font-sans)",
        display: "flex",
        flexDirection: "column",
        gap: 13,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <PersiftMark size={16} />
        <span style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--amber-soft)", fontWeight: 600 }}>
          New role found
        </span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          <motion.span
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.2, repeat: Infinity }}
            style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--amber)" }}
          />
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
        <Logo name="Stripe" />
        <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <span style={{ fontSize: "clamp(15px, 4.6vw, 18px)", fontWeight: 600, color: "var(--ink)", letterSpacing: "-0.01em" }}>
            Software Engineer Intern
          </span>
          <span style={{ fontSize: 13, color: "var(--ink-soft)" }}>Stripe · Posted 4 minutes ago</span>
        </div>
      </div>

      {/* fit-analysis bar — gives the beat live, scroll-driven motion */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--ink-mute)" }}>
          <span>Analyzing fit with your profile…</span>
          <motion.span style={{ opacity: matchOpacity, color: "var(--amber-soft)", fontWeight: 600 }}>94% match</motion.span>
        </div>
        <div style={{ height: 5, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
          <motion.div
            style={{
              height: "100%",
              width: fitWidth,
              borderRadius: 999,
              background: "linear-gradient(90deg, var(--amber-deep), var(--amber-soft))",
            }}
          />
        </div>
      </div>

      <motion.span style={{ opacity: linkedinOpacity, fontSize: 13, color: "var(--amber)", fontWeight: 500 }}>
        Not on LinkedIn yet.
      </motion.span>
    </div>
  )
}

/* ====================================================================== */
/* resume tailoring overlay (Change 6)                                     */
/* ====================================================================== */

function TailoringPanel({ company }: { company: Company }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 11,
        padding: "4px 2px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <motion.span
          animate={{ rotate: 360 }}
          transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
          style={{
            width: 15,
            height: 15,
            borderRadius: "50%",
            border: "2px solid rgba(240,163,65,0.25)",
            borderTopColor: "var(--amber)",
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 13, fontWeight: 600, color: "#2f3a33" }}>
          Tailoring resume for {company.name}…
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {company.tailorBullets.map((b, i) => (
          <motion.div
            key={b}
            initial={false}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 8,
              fontSize: 11.5,
              lineHeight: 1.4,
              color: "#3a4a40",
            }}
          >
            <span
              style={{
                width: 5,
                height: 5,
                borderRadius: "50%",
                background: "#3aa76d",
                marginTop: 5,
                flexShrink: 0,
                opacity: 0.6 + i * 0.15,
              }}
            />
            <span>{b}</span>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

/* ====================================================================== */
/* the application form being auto-filled — distinct per ATS (Change 7,10) */
/* ====================================================================== */

function FilledField({ label, value, done, accent }: { label: string; value: string; done: boolean; accent: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 10.5, color: "#3a4a40", fontWeight: 500 }}>{label}</span>
      <div
        style={{
          height: 32,
          borderRadius: 6,
          background: "#fff",
          border: "1px solid #d4ddd6",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 11px",
          fontSize: 12,
          color: "#2f3a33",
        }}
      >
        <span>{value}</span>
        {done && (
          <svg width="14" height="14" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke={accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
    </div>
  )
}

const ATS_STYLE: Record<Ats, { accent: string; surfaceBg: string; fieldBg: string; label: string; url: (c: string) => string }> = {
  greenhouse: {
    accent: "#3aa76d",
    surfaceBg: "#fbfaf8",
    fieldBg: "#fff",
    label: "Greenhouse",
    url: (c) => `boards.greenhouse.io/${c.toLowerCase()}/jobs/apply`,
  },
  ashby: {
    accent: "#5b62d6",
    surfaceBg: "#ffffff",
    fieldBg: "#fbfbfe",
    label: "Ashby",
    url: (c) => `jobs.ashbyhq.com/${c.toLowerCase()}/apply`,
  },
  custom: {
    accent: "#e0992f",
    surfaceBg: "#15110d",
    fieldBg: "#1c1712",
    label: "Custom",
    url: (c) => `${c.toLowerCase()}.com/careers/apply`,
  },
}

function ApplicationForm({ company, fillMV, phase }: { company: Company; fillMV: MotionValue<number>; phase: "tailoring" | "filling" }) {
  const style = ATS_STYLE[company.ats]
  const dark = company.ats === "custom"

  const ANSWER = company.essay
  const typed = useTransform(fillMV, (f) => ANSWER.slice(0, Math.round(ANSWER.length * Math.min(1, f * 1.15))))
  const caretOpacity = useTransform(fillMV, (f) => (f < 0.98 ? 1 : 0))
  const barWidth = useTransform(fillMV, (f) => `${Math.round(f * 100)}%`)

  // colors that adapt to dark (Linear) vs light (Greenhouse/Ashby) forms
  const ink = dark ? "#e9e2d6" : "#2f3a33"
  const inkMute = dark ? "#9a9183" : "#6a7a70"
  const fieldBorder = dark ? "#2e261d" : "#d4ddd6"

  return (
    <SurfaceFrame url={style.url(company.name)} accent={style.accent} width={440}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: company.ats === "ashby" ? 14 : 11,
          background: dark ? style.surfaceBg : "transparent",
          margin: -12,
          padding: 14,
          borderRadius: 8,
        }}
      >
        {/* header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{ fontSize: 13.5, fontWeight: 700, color: ink }}>{company.role}</span>
            <span style={{ fontSize: 11, color: inkMute }}>
              {company.formTitle.includes("·") ? company.formTitle.split("·")[1].trim() : `${company.name} · ${style.label}`}
            </span>
          </div>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 10,
              fontWeight: 600,
              color: "#8a5a17",
              background: "#fcefda",
              border: "1px solid #f0d8ad",
              borderRadius: 999,
              padding: "3px 9px",
            }}
          >
            <motion.span style={{ width: 6, height: 6, borderRadius: "50%", background: "#e0992f", opacity: caretOpacity }} />
            Persift autofilling
          </span>
        </div>

        {phase === "tailoring" ? (
          <div
            style={{
              borderRadius: 8,
              background: dark ? "rgba(240,163,65,0.06)" : "#f3f8f4",
              border: `1px solid ${dark ? "rgba(240,163,65,0.2)" : "#dce8e0"}`,
              padding: "12px 14px",
            }}
          >
            <TailoringPanel company={company} />
          </div>
        ) : (
          <>
            <FilledField label="Full name" value="Jordan Reyes" done accent={style.accent} />
            <FilledField label="Email" value="jordan.reyes@berkeley.edu" done accent={style.accent} />

            {/* resume */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 10.5, color: dark ? "#9a9183" : "#3a4a40", fontWeight: 500 }}>Resume / CV</span>
              <div
                style={{
                  height: 32,
                  borderRadius: 6,
                  background: dark ? "#211a13" : "#eef5f0",
                  border: `1px solid ${fieldBorder}`,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "0 11px",
                  fontSize: 12,
                  color: ink,
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: style.accent }} />
                resume_{company.name.toLowerCase()}_tailored.pdf
                <svg width="14" height="14" viewBox="0 0 12 12" fill="none" aria-hidden="true" style={{ marginLeft: "auto" }}>
                  <path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke={style.accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>

            {/* expanded real-application fields (Change 10) */}
            <FilledField label="Work authorization" value="U.S. Citizen or Permanent Resident" done accent={style.accent} />
            <div style={{ display: "flex", gap: 10 }}>
              <div style={{ flex: 1 }}>
                <FilledField label="Graduation date" value="May 2027" done accent={style.accent} />
              </div>
              <div style={{ width: 92 }}>
                <FilledField label="GPA" value="3.8" done accent={style.accent} />
              </div>
            </div>
            <FilledField label="Portfolio / GitHub" value="github.com/jordanreyes" done accent={style.accent} />

            {/* the essay being typed right now */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 10.5, color: dark ? "#9a9183" : "#3a4a40", fontWeight: 500 }}>
                Why do you want to work here?
              </span>
              <div
                style={{
                  minHeight: 78,
                  borderRadius: 6,
                  background: dark ? "#211a13" : "#fff",
                  border: `1.5px solid ${style.accent}`,
                  boxShadow: `0 0 0 3px ${style.accent}1f`,
                  padding: "8px 11px",
                  fontSize: 12,
                  lineHeight: 1.5,
                  color: ink,
                }}
              >
                <motion.span>{typed}</motion.span>
                <motion.span
                  style={{
                    opacity: caretOpacity,
                    display: "inline-block",
                    width: 1.5,
                    height: 13,
                    background: style.accent,
                    marginLeft: 1,
                    transform: "translateY(2px)",
                  }}
                />
              </div>
            </div>

            {/* fill progress */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 2 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: inkMute }}>
                <span>Auto-filling fields…</span>
              </div>
              <div style={{ height: 5, borderRadius: 999, background: dark ? "#2e261d" : "#e4ebe5", overflow: "hidden" }}>
                <motion.div
                  style={{
                    height: "100%",
                    width: barWidth,
                    borderRadius: 999,
                    background: `linear-gradient(90deg, ${style.accent}, ${style.accent})`,
                  }}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </SurfaceFrame>
  )
}

/* ====================================================================== */
/* needs-you state body (Change 8)                                         */
/* ====================================================================== */

function NeedsYouBody() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>
        <span
          style={{
            width: 24,
            height: 24,
            borderRadius: "50%",
            background: "rgba(240,163,65,0.16)",
            color: "var(--amber)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          !
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>Figma — Design Engineer Intern</span>
          <span style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.45 }}>
            Ready to submit — review before we send?
          </span>
        </div>
      </div>
      <div style={{ display: "flex", gap: 9 }}>
        <span
          style={{
            flex: 1,
            textAlign: "center",
            borderRadius: 10,
            padding: "10px 8px",
            fontSize: 12.5,
            fontWeight: 600,
            color: "#1a1206",
            background: "linear-gradient(180deg, var(--amber-soft), var(--amber))",
          }}
        >
          Review &amp; Submit
        </span>
        <span
          style={{
            flex: 1,
            textAlign: "center",
            borderRadius: 10,
            padding: "10px 8px",
            fontSize: 12.5,
            fontWeight: 600,
            color: "var(--ink-soft)",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid var(--line)",
          }}
        >
          Auto-submit this one
        </span>
      </div>
    </div>
  )
}

/* ====================================================================== */

export function Scene3Machine() {
  const p = useSceneProgress()
  const isMobile = useIsMobile()

  // discovery beat holds for the first ~28% of the band, then crossfades out
  const discoveryOpacity = useTransform(p, [0, 0.10, 0.32, 0.44], [0, 1, 1, 0])
  const workOpacity = useTransform(p, [0.38, 0.46, 0.88, 1.0], [0, 1, 1, 0])

  // applying loop: each company gets an equal slice, company boundaries at whole numbers
  // so frac resets cleanly to 0 at every switch — no mid-fill jumps
  const APPLY_START = 0.44
  const APPLY_END = 0.88
  const BAND = (APPLY_END - APPLY_START) / PIPELINE.length

  const rawIndex = useTransform(p, (v) =>
    Math.max(0, Math.min(PIPELINE.length - 0.001, (v - APPLY_START) / BAND))
  )

  const [current, setCurrent] = useState(0)
  useMotionValueEvent(rawIndex, "change", (v) => {
    const i = Math.min(PIPELINE.length - 1, Math.floor(v))
    if (i !== current) setCurrent(i)
  })

  // needs-you toggles on near the end
  const [needsYou, setNeedsYou] = useState(false)
  useMotionValueEvent(p, "change", (v) => {
    const on = v >= 0.90
    if (on !== needsYou) setNeedsYou(on)
  })

  // frac: 0→1 within each company's slot, resets cleanly at every switch
  const frac = useTransform(rawIndex, (v) => v - Math.floor(v))
  const [phase, setPhase] = useState<"tailoring" | "filling">("tailoring")
  useMotionValueEvent(frac, "change", (f) => {
    const next = f < 0.15 ? "tailoring" : "filling"
    if (next !== phase) setPhase(next)
  })
  // fillFrac: 0→1 during the filling phase (85% of each slot)
  const fillFrac = useTransform(frac, (f) => Math.max(0, Math.min(1, (f - 0.15) / 0.85)))
  const fill = useTransform(fillFrac, (f) => `${Math.round(f * 100)}%`)

  const active = PIPELINE[current]
  const queue = PIPELINE.slice(current + 1)

  const headlineOpacity = useTransform(p, [0, 0.08, 0.38, 0.46], [0, 1, 1, 0])

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
      {/* floating headline — visible during discovery beat */}
      <motion.div style={{
        opacity: headlineOpacity,
        position: "absolute",
        top: 40,
        left: 0, right: 0,
        textAlign: "center",
        pointerEvents: "none",
        padding: "0 24px",
      }}>
        <h3 style={{
          margin: "0 0 6px",
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          fontWeight: 800,
          fontSize: "clamp(26px, 3.5vw, 42px)",
          letterSpacing: "-0.025em",
          color: "var(--ink)",
        }}>
          It finds them. It applies.
        </h3>
        <p style={{
          margin: 0,
          fontFamily: "Inter, sans-serif",
          fontWeight: 400,
          fontSize: "clamp(13px, 1.3vw, 16px)",
          color: "var(--ink-soft)",
        }}>
          While you&apos;re in class, asleep, or anywhere else.
        </p>
      </motion.div>

      {/* opening discovery beat */}
      <motion.div
        style={{
          opacity: discoveryOpacity,
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "0 24px",
        }}
      >
        <DiscoveryCard mv={p} />
      </motion.div>

      {/* the working split-screen */}
      <motion.div
        style={{
          opacity: workOpacity,
          display: "flex",
          flexDirection: isMobile ? "column" : "row",
          alignItems: "center",
          justifyContent: "center",
          gap: isMobile ? 14 : 34,
          flexWrap: isMobile ? "nowrap" : "wrap",
          padding: isMobile ? "0 16px" : "0 28px",
          width: "100%",
          transform: isMobile ? "scale(0.82)" : "none",
          transformOrigin: "center",
        }}
      >
        {/* LEFT — the extension doing the work */}
        {needsYou ? (
          <ExtensionPopup status="applying" statusLabel="Needs you" pulse toggleOn footnote="Auto-apply" width={340}>
            <NeedsYouBody />
          </ExtensionPopup>
        ) : (
          <ExtensionPopup status="applying" statusLabel="Applying" toggleOn footnote="Auto-apply" width={340}>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <span style={{ fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--ink-mute)" }}>
                  {phase === "tailoring" ? "Tailoring resume for" : "Currently applying to"}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 11, marginTop: 9 }}>
                  <Logo name={active.name} />
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{active.name}</span>
                    <span style={{ fontSize: 12, color: "var(--ink-mute)" }}>{active.role}</span>
                  </div>
                </div>
                <div style={{ marginTop: 12, height: 5, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
                  <motion.div
                    style={{
                      height: "100%",
                      width: fill,
                      borderRadius: 999,
                      background: "linear-gradient(90deg, var(--amber-deep), var(--amber-soft))",
                    }}
                  />
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <span style={{ fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
                  Next in line
                </span>
                {queue.length === 0 && <span style={{ fontSize: 12.5, color: "var(--ink-mute)" }}>Queue complete.</span>}
                {queue.map((c) => (
                  <div key={c.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <Logo name={c.name} />
                      <span style={{ fontSize: 13, color: "var(--ink-soft)" }}>{c.name}</span>
                    </div>
                    <span style={{ fontSize: 12, color: "var(--amber-soft)", fontWeight: 600 }}>{c.match}% match</span>
                  </div>
                ))}
              </div>
            </div>
          </ExtensionPopup>
        )}

        {/* connective beam (desktop only) */}
        {!isMobile && (
          <div
            aria-hidden="true"
            style={{ width: 40, height: 2, background: "linear-gradient(90deg, var(--amber-soft), transparent)", alignSelf: "center", opacity: 0.6 }}
          />
        )}

        {/* RIGHT — the real form being filled */}
        <ApplicationForm company={active} fillMV={fillFrac} phase={phase} />
      </motion.div>
    </div>
  )
}
