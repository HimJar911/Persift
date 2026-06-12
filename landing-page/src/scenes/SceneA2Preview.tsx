import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Wordmark } from "../components/Brand"
import { JOBS, TOTAL_FIELDS, FORM_HEIGHT } from "../components/WorkflowAnimation"

const JOB_COUNT = JOBS.length // 3

type Stage = "enter" | "filling" | "clicking" | "submitted" | "exit"

const STAGE_MS: Record<Stage, number> = {
  enter:     800,
  filling:  4500,
  clicking:  500,
  submitted: 1800,
  exit:      600,
}

const LOG_LINES: Record<string, string[]> = {
  ashby:      ["Detected Ashby ATS", "Parsing 12 fields", "Resume matched", "Submitting…"],
  greenhouse: ["Detected Greenhouse ATS", "Parsing 18 fields", "Resume matched", "Submitting…"],
  lever:      ["Detected Lever ATS", "Parsing 14 fields", "Resume matched", "Submitting…"],
}

const QUEUE_EXTRA = [
  { company: "Databricks", logoBg: "#f0f4ff" },
  { company: "Cursor",     logoBg: "#f5f5f5" },
]

export function PersiftCommandCenter() {
  const [idx, setIdx] = useState(0)
  const [stage, setStage] = useState<Stage>("enter")
  const [logs, setLogs] = useState<string[]>([])
  const [appliedToday, setAppliedToday] = useState(17)
  const cancelRef = useRef(false)

  useEffect(() => {
    cancelRef.current = false
    let currentIdx = 0
    let total = 17

    async function run() {
      while (!cancelRef.current) {
        const job = JOBS[currentIdx % JOB_COUNT]
        const logLines = LOG_LINES[job.ats]

        setIdx(currentIdx % JOB_COUNT)
        setStage("enter")
        setLogs([])
        await sleep(STAGE_MS.enter)
        if (cancelRef.current) break

        setStage("filling")
        const logInterval = (STAGE_MS.filling * 0.85) / logLines.length
        for (let i = 0; i < logLines.length; i++) {
          await sleep(logInterval)
          if (cancelRef.current) break
          setLogs(logLines.slice(0, i + 1))
        }
        await sleep(STAGE_MS.filling * 0.15)
        if (cancelRef.current) break

        setStage("clicking")
        await sleep(STAGE_MS.clicking)
        if (cancelRef.current) break

        total += 1
        setAppliedToday(total)
        setStage("submitted")
        await sleep(STAGE_MS.submitted)
        if (cancelRef.current) break

        setStage("exit")
        await sleep(STAGE_MS.exit)
        if (cancelRef.current) break

        currentIdx = (currentIdx + 1) % JOB_COUNT
      }
    }

    run()
    return () => { cancelRef.current = true }
  }, [])

  const job = JOBS[idx]
  const upNext  = JOBS[(idx + 1) % JOB_COUNT]
  const inQueue = [
    JOBS[(idx + 2) % JOB_COUNT],
    QUEUE_EXTRA[0],
    QUEUE_EXTRA[1],
  ]

  const isSubmitted = stage === "submitted"

  return (
    <div style={{
      width: "100%", height: "100%",
      display: "flex", flexDirection: "column",
      background: "#0c0a08",
      fontFamily: "Inter, sans-serif",
      overflow: "hidden",
    }}>
      {/* Wordmark header */}
      <div style={{
        padding: "7px 12px",
        borderBottom: "1px solid #1e1c1a",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexShrink: 0,
      }}>
        <Wordmark height={14} color="var(--ink)" />
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <motion.div
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.4, repeat: Infinity }}
            style={{ width: 5, height: 5, borderRadius: "50%", background: "#5fd07f" }}
          />
          <span style={{ fontSize: 8, color: "#5fd07f" }}>Running</span>
        </div>
      </div>

      {/* Two-column layout */}
      <div style={{
        flex: 1, display: "flex", gap: 8, padding: "8px 10px",
        minHeight: 0, overflow: "hidden",
      }}>

        {/* ── Left: logs card + gmail confirm ── */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 7, minWidth: 0 }}>

          {/* Logs card */}
          <div style={{
            flex: 1, minWidth: 0,
            background: "#161412", border: "1px solid #252220",
            borderRadius: 8, padding: "10px 12px",
            display: "flex", flexDirection: "column", overflow: "hidden",
          }}>
            {/* Job header */}
            <AnimatePresence mode="wait">
              <motion.div key={job.company} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                  <div style={{ width: 18, height: 18, borderRadius: 4, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <span style={{ fontSize: 7, fontWeight: 700, color: "#444" }}>{job.company.slice(0, 2).toUpperCase()}</span>
                  </div>
                  <div>
                    <div style={{ fontSize: 9.5, fontWeight: 600, color: "#faf8f5", lineHeight: 1.2 }}>{job.company}</div>
                    <div style={{ fontSize: 8, color: "#5a5550", lineHeight: 1.2 }}>{job.role}</div>
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
            <div style={{ height: 1, background: "#1e1c1a", marginBottom: 8 }} />
            {/* Log lines */}
            <div style={{ display: "flex", flexDirection: "column", gap: 5, flex: 1 }}>
              {logs.map((line, i) => (
                <motion.div
                  key={line}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2 }}
                  style={{ display: "flex", alignItems: "center", gap: 5 }}
                >
                  <span style={{ fontSize: 8, color: "#5fd07f", flexShrink: 0 }}>✓</span>
                  <span style={{ fontSize: 8.5, color: i === logs.length - 1 ? "#c8c0b4" : "#5a5550" }}>{line}</span>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Gmail confirmation — fixed height slot */}
          <div style={{ height: 52, flexShrink: 0 }}>
            <AnimatePresence>
              {isSubmitted && (
                <motion.div
                  initial={{ opacity: 0, y: 6, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 26 }}
                  style={{
                    height: "100%",
                    background: "#161412",
                    border: "1px solid #252220",
                    borderRadius: 8,
                    padding: "8px 10px",
                    display: "flex", alignItems: "center", gap: 8,
                  }}
                >
                  <div style={{ width: 20, height: 20, borderRadius: 4, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <svg viewBox="0 0 24 24" width="11" height="11">
                      <path fill="#EA4335" d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z" />
                    </svg>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, fontWeight: 600, color: "#faf8f5", marginBottom: 2 }}>Application Received · {job.company}</div>
                    <div style={{ fontSize: 8, color: "#6a6560", lineHeight: 1.4 }}>Thank you for applying to {job.role}…</div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

        </div>

        {/* ── Right: counter + queue ── */}
        <div style={{ width: 130, display: "flex", flexDirection: "column", gap: 7, flexShrink: 0 }}>

          {/* Counter */}
          <div style={{
            background: "#161412", border: "1px solid #252220",
            borderRadius: 9, padding: "10px 12px",
            textAlign: "center", flexShrink: 0,
          }}>
            <AnimatePresence mode="wait">
              <motion.div
                key={appliedToday}
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 5 }}
                transition={{ duration: 0.2 }}
                style={{ fontSize: 28, fontWeight: 700, color: "#f0a341", lineHeight: 1 }}
              >
                {appliedToday}
              </motion.div>
            </AnimatePresence>
            <div style={{ fontSize: 7.5, color: "#5a5550", marginTop: 3, letterSpacing: "0.02em" }}>applied today</div>
          </div>

          {/* Departures queue */}
          <div style={{
            background: "#161412", border: "1px solid #252220",
            borderRadius: 9, padding: "10px 11px",
            flex: 1, display: "flex", flexDirection: "column",
            overflow: "hidden",
          }}>
            {/* Now Applying */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 7, fontWeight: 600, color: "#f0a341", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
                <motion.div animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }}
                  style={{ width: 4, height: 4, borderRadius: "50%", background: "#f0a341" }} />
                Now Applying
              </div>
              <AnimatePresence mode="wait">
                <motion.div key={job.company} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.22 }}
                  style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 16, height: 16, borderRadius: 3, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <span style={{ fontSize: 6, fontWeight: 700, color: "#444" }}>{job.company.slice(0, 2).toUpperCase()}</span>
                  </div>
                  <span style={{ fontSize: 9.5, fontWeight: 600, color: "#faf8f5" }}>{job.company}</span>
                </motion.div>
              </AnimatePresence>
            </div>

            <div style={{ height: 1, background: "#1e1c1a", marginBottom: 8 }} />

            {/* Up Next */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 7, color: "#4a4540", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Up Next</div>
              <AnimatePresence mode="wait">
                <motion.div key={upNext.company} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.22 }}
                  style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 14, height: 14, borderRadius: 3, background: upNext.logoBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <span style={{ fontSize: 5, fontWeight: 700, color: "#444" }}>{upNext.company.slice(0, 2).toUpperCase()}</span>
                  </div>
                  <span style={{ fontSize: 9, color: "#8a857d" }}>{upNext.company}</span>
                </motion.div>
              </AnimatePresence>
            </div>

            <div style={{ height: 1, background: "#1e1c1a", marginBottom: 8 }} />

            {/* In Queue */}
            <div>
              <div style={{ fontSize: 7, color: "#3a3530", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 5 }}>In Queue</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {inQueue.map(j => (
                  <div key={j.company} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 2, background: j.logoBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <span style={{ fontSize: 4.5, fontWeight: 700, color: "#444" }}>{j.company.slice(0, 2).toUpperCase()}</span>
                    </div>
                    <span style={{ fontSize: 8.5, color: "#3a3530" }}>{j.company}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function SceneA2Preview() {
  return (
    <div style={{ position: "absolute", inset: 0, background: "#0c0a08" }}>
      <PersiftCommandCenter />
    </div>
  )
}

function sleep(ms: number) {
  return new Promise<void>(r => setTimeout(r, ms))
}
