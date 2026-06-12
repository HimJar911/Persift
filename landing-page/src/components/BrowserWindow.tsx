import { type ReactNode } from "react"

/**
 * A full-size, dark-themed browser window used by the dashboard scenes.
 * Provides real browser chrome (traffic lights + address bar) so the
 * product reads as an actual screen you're looking at, not a floating card.
 */
export function BrowserWindow({
  url,
  children,
  width = "90vw",
  maxWidth = 1080,
}: {
  url: string
  children: ReactNode
  width?: number | string
  maxWidth?: number
}) {
  return (
    <div
      style={{
        width,
        maxWidth,
        borderRadius: 16,
        overflow: "hidden",
        background: "#0f0c08",
        border: "1px solid var(--line)",
        boxShadow: "0 50px 110px -40px rgba(0,0,0,0.9), 0 14px 40px -20px rgba(0,0,0,0.7)",
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
          background: "#171209",
          borderBottom: "1px solid var(--line)",
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
            maxWidth: 420,
            margin: "0 auto",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: "5px 12px",
            fontSize: 11.5,
            color: "var(--ink-mute)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "flex",
            alignItems: "center",
            gap: 7,
            textAlign: "center",
            justifyContent: "center",
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="5" y="11" width="14" height="10" rx="2" stroke="var(--ink-faint)" strokeWidth="2" />
            <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="var(--ink-faint)" strokeWidth="2" />
          </svg>
          {url}
        </span>
        <span style={{ width: 56 }} aria-hidden="true" />
      </div>

      {/* page body */}
      {children}
    </div>
  )
}
