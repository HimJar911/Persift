import { type ReactNode } from "react"
import { motion } from "framer-motion"
import { Wordmark } from "./Brand"

export type PopupStatus = "ready" | "applying"

type ExtensionPopupProps = {
  status: PopupStatus
  /** label shown next to the status dot in the header */
  statusLabel: string
  /** whether the header dot should pulse (e.g. while applying overnight) */
  pulse?: boolean
  /** body content for the popup */
  children: ReactNode
  /** auto-apply toggle state */
  toggleOn?: boolean
  /** footer caption */
  footnote?: string
  width?: number
}

/**
 * The Persift Chrome extension popup. One consistent shell across scenes
 * 2, 3 and 4 — only the body + status change so the user recognizes it as
 * the same product in different states.
 */
export function ExtensionPopup({
  status,
  statusLabel,
  pulse = false,
  children,
  toggleOn = true,
  footnote = "Auto-apply",
  width = 340,
}: ExtensionPopupProps) {
  const dotColor = status === "applying" ? "var(--amber)" : "var(--green)"

  return (
    <div
      style={{
        width,
        maxWidth: "90vw",
        borderRadius: 18,
        background: "linear-gradient(180deg, #211a13, #191309)",
        border: "1px solid var(--line)",
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.04) inset, 0 30px 60px -24px rgba(0,0,0,0.8), 0 8px 24px -12px rgba(0,0,0,0.6)",
        overflow: "hidden",
        fontFamily: "var(--font-sans)",
      }}
    >
      {/* header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "13px 15px",
          borderBottom: "1px solid var(--line)",
          background: "rgba(255,255,255,0.015)",
        }}
      >
        <Wordmark height={22} />
        {status === "applying" ? (
          <div style={{
            display: "flex", alignItems: "center", gap: 7,
            background: "rgba(240,163,65,0.10)",
            border: "1px solid rgba(240,163,65,0.28)",
            borderRadius: 999,
            padding: "4px 10px 4px 7px",
          }}>
            <motion.span
              animate={{ rotate: 360 }}
              transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
              style={{
                width: 11, height: 11, borderRadius: "50%",
                border: "1.5px solid rgba(240,163,65,0.3)",
                borderTopColor: "var(--amber)",
                display: "inline-block", flexShrink: 0,
              }}
            />
            <span style={{
              fontSize: 11, fontWeight: 600,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--amber-soft)",
            }}>
              {statusLabel}
            </span>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ position: "relative", width: 8, height: 8, display: "inline-block" }}>
              <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: dotColor }} />
            </span>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", color: "var(--green)" }}>
              {statusLabel}
            </span>
          </div>
        )}
      </div>

      {/* body */}
      <div style={{ padding: "16px 15px" }}>{children}</div>

      {/* footer toggle */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 15px",
          borderTop: "1px solid var(--line)",
          background: "rgba(0,0,0,0.22)",
        }}
      >
        <span style={{ fontSize: 12.5, color: "var(--ink-soft)", fontWeight: 500 }}>{footnote}</span>
        <div
          style={{
            width: 38,
            height: 22,
            borderRadius: 999,
            background: toggleOn ? "var(--amber)" : "var(--line)",
            display: "flex",
            alignItems: "center",
            padding: 2,
            justifyContent: toggleOn ? "flex-end" : "flex-start",
            transition: "background 0.2s",
          }}
        >
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: "50%",
              background: "#fff",
              boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
            }}
          />
        </div>
      </div>

      <style>{`
        @keyframes popupPulse {
          0% { transform: scale(0.8); opacity: 0.9; }
          100% { transform: scale(2.4); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
