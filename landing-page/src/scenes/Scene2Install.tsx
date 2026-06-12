import { motion, useTransform } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"
import { PersiftMark } from "../components/Brand"

/**
 * The "install Persift" beat — a full Chrome Web Store page (light theme)
 * inside a browser window that fills the viewport. The "Add to Chrome"
 * button resolves into an "Added" state as the scene progresses: the
 * moment the student actually adopts the tool.
 */

function StorePill({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: 11,
        color: "#5f6b62",
        background: "#eef2ee",
        border: "1px solid #dde4dd",
        borderRadius: 999,
        padding: "4px 11px",
      }}
    >
      {children}
    </span>
  )
}

function ScreenshotTile({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        borderRadius: 10,
        background: "linear-gradient(160deg, #14100b, #0c0907)",
        border: "1px solid #e2e6e0",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          height: 150,
          padding: 12,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        {children}
      </div>
      <div
        style={{
          padding: "8px 12px",
          borderTop: "1px solid #1f1a13",
          fontSize: 10.5,
          color: "#8c7a55",
          fontWeight: 500,
        }}
      >
        {label}
      </div>
    </div>
  )
}

/* ---------- mini product previews (real UI, scaled to fit the tiles) ---------- */

function MiniCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        width: "100%",
        borderRadius: 9,
        background: "linear-gradient(180deg, #221a13, #181109)",
        border: "1px solid #2e261d",
        padding: "9px 10px",
        display: "flex",
        flexDirection: "column",
        gap: 7,
        fontFamily: "var(--font-sans)",
      }}
    >
      {children}
    </div>
  )
}

function MiniApplyingPreview() {
  return (
    <MiniCard>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <PersiftMark size={11} />
          <span style={{ fontSize: 9, fontWeight: 600, color: "#f3ece1", fontFamily: "var(--font-serif)" }}>
            Persift
          </span>
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#f0a341" }} />
          <span style={{ fontSize: 8, fontWeight: 600, color: "#f6c178" }}>Applying</span>
        </span>
      </div>
      <span style={{ fontSize: 7.5, letterSpacing: "0.1em", textTransform: "uppercase", color: "#8a8071" }}>
        Currently applying to
      </span>
      <span style={{ fontSize: 10, fontWeight: 600, color: "#f3ece1" }}>Stripe</span>
      <div style={{ height: 4, borderRadius: 999, background: "#2e261d", overflow: "hidden" }}>
        <div style={{ height: "100%", width: "64%", borderRadius: 999, background: "linear-gradient(90deg, #c97a1f, #f6c178)" }} />
      </div>
      {["Anthropic", "Linear"].map((c) => (
        <div key={c} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 9, color: "#cdc3b4" }}>{c}</span>
          <span style={{ fontSize: 8.5, color: "#f6c178", fontWeight: 600 }}>{c === "Anthropic" ? "91%" : "82%"}</span>
        </div>
      ))}
    </MiniCard>
  )
}

function MiniMorningPreview() {
  return (
    <MiniCard>
      <span style={{ fontSize: 12, fontWeight: 500, color: "#f3ece1", fontFamily: "var(--font-serif)" }}>
        Good morning.
      </span>
      <span style={{ fontSize: 8.5, color: "#cdc3b4" }}>
        You applied to <span style={{ color: "#f6c178", fontWeight: 600 }}>8 jobs</span> overnight.
      </span>
      <div style={{ display: "flex", gap: 5 }}>
        {[
          { v: "8", l: "Sent" },
          { v: "3", l: "Replies" },
          { v: "1", l: "Needs you", a: true },
        ].map((s) => (
          <div
            key={s.l}
            style={{
              flex: 1,
              borderRadius: 6,
              border: "1px solid #2e261d",
              padding: "5px 6px",
              display: "flex",
              flexDirection: "column",
              gap: 1,
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, color: s.a ? "#f0a341" : "#f3ece1", fontFamily: "var(--font-serif)" }}>
              {s.v}
            </span>
            <span style={{ fontSize: 7, color: "#8a8071" }}>{s.l}</span>
          </div>
        ))}
      </div>
      <div
        style={{
          borderRadius: 6,
          border: "1px solid rgba(240,163,65,0.32)",
          background: "rgba(240,163,65,0.1)",
          padding: "5px 7px",
          fontSize: 8,
          color: "#f6c178",
        }}
      >
        Interview · Stripe · tomorrow 2 PM
      </div>
    </MiniCard>
  )
}

function MiniAnalyticsPreview() {
  const bars = [4, 6, 5, 8, 7, 9, 11, 10, 13, 12, 14, 15]
  const max = Math.max(...bars)
  return (
    <MiniCard>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 9, fontWeight: 600, color: "#f3ece1" }}>Applications</span>
        <span style={{ fontSize: 8, color: "#f6c178", fontWeight: 600 }}>+38%</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 46 }}>
        {bars.map((b, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: `${(b / max) * 100}%`,
              borderRadius: 2,
              background: i >= bars.length - 3 ? "linear-gradient(180deg, #f6c178, #c97a1f)" : "#4a3b29",
            }}
          />
        ))}
      </div>
      <div style={{ display: "flex", gap: 5 }}>
        {[
          { v: "19%", l: "Reply rate", a: true },
          { v: "2×", l: "Faster ATS" },
        ].map((s) => (
          <div key={s.l} style={{ flex: 1, borderRadius: 6, border: "1px solid #2e261d", padding: "5px 6px" }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: s.a ? "#f0a341" : "#f3ece1", fontFamily: "var(--font-serif)" }}>
              {s.v}
            </span>
            <div style={{ fontSize: 7, color: "#8a8071" }}>{s.l}</div>
          </div>
        ))}
      </div>
    </MiniCard>
  )
}

export function Scene2Install() {
  const p = useSceneProgress()

  // the window settles in
  const scale = useTransform(p, [0, 0.3], [0.95, 1])
  const winY = useTransform(p, [0, 0.3], [22, 0])

  // button flips from "Add to Chrome" to "Added" partway through
  const addOpacity = useTransform(p, [0.42, 0.52], [1, 0])
  const addedOpacity = useTransform(p, [0.52, 0.62], [0, 1])
  const installedBadgeOpacity = useTransform(p, [0.58, 0.72], [0, 1])
  const installedBadgeY = useTransform(p, [0.58, 0.72], [10, 0])

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
          One click to install.
        </h3>
      </div>
      <motion.div
        style={{
          scale,
          y: winY,
          width: "90vw",
          maxWidth: 1040,
          borderRadius: 16,
          overflow: "hidden",
          background: "#ffffff",
          border: "1px solid rgba(0,0,0,0.14)",
          boxShadow: "0 50px 110px -40px rgba(0,0,0,0.9), 0 14px 40px -20px rgba(0,0,0,0.7)",
          color: "#1f2a23",
          fontFamily: "var(--font-sans)",
        }}
      >
        {/* browser chrome */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "10px 14px",
            background: "#e9ece7",
            borderBottom: "1px solid rgba(0,0,0,0.08)",
          }}
        >
          <span style={{ display: "flex", gap: 6 }}>
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#e06c5b" }} />
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#e3b14a" }} />
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#7bb86f" }} />
          </span>
          <span
            style={{
              flex: 1,
              maxWidth: 460,
              margin: "0 auto",
              background: "#fff",
              border: "1px solid rgba(0,0,0,0.1)",
              borderRadius: 8,
              padding: "5px 12px",
              fontSize: 11.5,
              color: "#6a655e",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              textAlign: "center",
            }}
          >
            chromewebstore.google.com/detail/persift
          </span>
          <span style={{ width: 40 }} aria-hidden="true" />
        </div>

        {/* store top bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 28px",
            borderBottom: "1px solid #edf0ec",
          }}
        >
          <span style={{ fontSize: 14, fontWeight: 600, color: "#3aa76d" }}>chrome</span>
          <span style={{ fontSize: 14, color: "#5f6b62" }}>web store</span>
        </div>

        {/* listing */}
        <div style={{ padding: "26px 28px 30px", display: "flex", flexDirection: "column", gap: 22 }}>
          {/* heading row */}
          <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
            <span
              style={{
                width: 64,
                height: 64,
                borderRadius: 15,
                background: "linear-gradient(135deg, #211a13, #100c09)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                border: "1px solid rgba(0,0,0,0.1)",
              }}
            >
              <PersiftMark size={50} />
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, flex: 1, minWidth: 220 }}>
              <span
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: "#202124",
                  fontFamily: "'Plus Jakarta Sans', var(--font-sans)",
                  letterSpacing: "-0.02em",
                }}
              >
                Job applications on autopilot.
              </span>
              <span style={{ fontSize: 12.5, color: "#6a7a70" }}>persift.com · Early access</span>
            </div>

            {/* add to chrome button with state flip */}
            <div style={{ position: "relative", width: 200, height: 46, flexShrink: 0 }}>
              <motion.div
                style={{
                  opacity: addOpacity,
                  position: "absolute",
                  inset: 0,
                  borderRadius: 23,
                  background: "#0875e1",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  color: "#fff",
                  fontSize: 14.5,
                  fontWeight: 600,
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#fff" }} />
                Add to Chrome
              </motion.div>
              <motion.div
                style={{
                  opacity: addedOpacity,
                  position: "absolute",
                  inset: 0,
                  borderRadius: 23,
                  background: "#eef5f0",
                  border: "1px solid #cdd9d0",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  color: "#2f7a4f",
                  fontSize: 14.5,
                  fontWeight: 600,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke="#2f7a4f" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Added to Chrome
              </motion.div>
            </div>
          </div>

          {/* meta pills */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <StorePill>Finds roles before LinkedIn</StorePill>
            <StorePill>Tailors resume per company</StorePill>
            <StorePill>Tracks everything automatically</StorePill>
          </div>

          {/* screenshots — real product UI */}
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <ScreenshotTile label="It applies for you">
              <MiniApplyingPreview />
            </ScreenshotTile>
            <ScreenshotTile label="Wake up to results">
              <MiniMorningPreview />
            </ScreenshotTile>
            <ScreenshotTile label="See what's working">
              <MiniAnalyticsPreview />
            </ScreenshotTile>
          </div>
        </div>

        {/* installed toast bar */}
        <motion.div
          style={{
            opacity: installedBadgeOpacity,
            y: installedBadgeY,
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "13px 28px",
            background: "#211a13",
            color: "#f4efe6",
          }}
        >
          <PersiftMark size={16} />
          <span style={{ fontSize: 12.5, fontWeight: 500 }}>Persift was added to your browser.</span>
          <span style={{ fontSize: 11.5, color: "#c9a86a", marginLeft: "auto" }}>Pinned to toolbar</span>
        </motion.div>
      </motion.div>

    </div>
  )
}
