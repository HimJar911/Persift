import { type ReactNode } from "react"
import { Wordmark } from "./Brand"

type Tab = "overview" | "analytics"

type DashboardShellProps = {
  activeTab: Tab
  children: ReactNode
  tone?: "dawn" | "day"
  width?: number | string
  embedded?: boolean
  maxHeight?: string
}

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "analytics", label: "Analytics" },
]

/**
 * The Persift dashboard chrome — shared topbar, logo and nav tabs across
 * scenes 5 and 6. Only the active tab and body change.
 */
export function DashboardShell({ activeTab, children, tone = "day", width = 720, embedded = false, maxHeight }: DashboardShellProps) {
  return (
    <div
      style={{
        width: embedded ? "100%" : width,
        maxWidth: embedded ? "none" : "92vw",
        borderRadius: embedded ? 0 : 20,
        overflow: "hidden",
        maxHeight,
        background: embedded ? "transparent" : "linear-gradient(180deg, #1a150f, #14100b)",
        border: embedded ? "none" : "1px solid var(--line)",
        boxShadow: embedded ? "none" : "0 40px 90px -40px rgba(0,0,0,0.85), 0 10px 30px -16px rgba(0,0,0,0.6)",
        fontFamily: "var(--font-sans)",
      }}
    >
      {/* topbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "13px 18px",
          borderBottom: "1px solid var(--line)",
          background:
            tone === "dawn"
              ? "linear-gradient(90deg, rgba(240,163,65,0.08), rgba(255,255,255,0.01))"
              : "rgba(255,255,255,0.015)",
        }}
      >
        <Wordmark height={22} />
        <nav style={{ display: "flex", gap: 4 }}>
          {TABS.map((t) => {
            const active = t.id === activeTab
            return (
              <span
                key={t.id}
                style={{
                  fontSize: 12.5,
                  fontWeight: 500,
                  padding: "6px 12px",
                  borderRadius: 999,
                  color: active ? "var(--bg)" : "var(--ink-mute)",
                  background: active ? "var(--amber-soft)" : "transparent",
                }}
              >
                {t.label}
              </span>
            )
          })}
        </nav>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #3a2c1c, #221a12)",
            border: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            fontWeight: 600,
            color: "var(--ink-soft)",
          }}
        >
          HJ
        </div>
      </div>

      {/* body */}
      <div style={{ padding: embedded ? "20px 28px 20px" : "22px 24px 26px" }}>{children}</div>
    </div>
  )
}
