import { useRef, useEffect } from "react"
import { motion, useScroll, useMotionValue, useTransform } from "framer-motion"
import { Section } from "./scroll/Section"
import { Wordmark } from "./components/Brand"
import { Scene0Hero } from "./scenes/Scene0Hero"
import { Scene2Install } from "./scenes/Scene2Install"
import { Scene2Setup } from "./scenes/Scene2Setup"
import { Scene3Machine } from "./scenes/Scene3Machine"
import { Scene4Overnight } from "./scenes/Scene4Overnight"
import { Scene5Morning } from "./scenes/Scene5Morning"
import { Scene6Analytics } from "./scenes/Scene6Analytics"
import { SceneBridge } from "./scenes/SceneBridge"
import { Scene7Ask } from "./scenes/Scene7Ask"

const HEADER_H = 48

export default function App() {
  const pageRef = useRef<HTMLDivElement>(null)

  const { scrollYProgress } = useScroll()
  const progress = useMotionValue(0)
  useEffect(() => scrollYProgress.on("change", (v) => progress.set(v)), [scrollYProgress])
  const barScale = useTransform(progress, [0, 1], [0, 1])

  return (
    <main ref={pageRef} style={{ background: "var(--bg)" }}>
      {/* scroll progress bar */}
      <motion.div style={{
        position: "fixed",
        top: 0, left: 0, right: 0,
        height: 2,
        transformOrigin: "0% 50%",
        scaleX: barScale,
        background: "linear-gradient(90deg, var(--amber-deep), var(--amber-soft))",
        zIndex: 120,
      }} />

      {/* header */}
      <header style={{
        position: "fixed",
        top: 0, left: 0, right: 0,
        height: HEADER_H,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 32px",
        zIndex: 110,
        background: "transparent",
      }}>
        <Wordmark height={30} />
        <button
          onClick={() => {
            const el = document.getElementById("section-cta")
            el?.scrollIntoView({ behavior: "smooth" })
          }}
          style={{
            border: "none",
            cursor: "pointer",
            borderRadius: 9,
            padding: "8px 18px",
            fontSize: 13,
            fontWeight: 600,
            color: "#1a1206",
            background: "linear-gradient(180deg, var(--amber-soft), var(--amber))",
            whiteSpace: "nowrap",
          }}
        >
          Join waitlist
        </button>
      </header>

      {/* ── Hero — full-viewport, no scroll travel needed ── */}
      <div style={{ height: "100vh", position: "relative" }}>
        <Scene0Hero />
      </div>

      {/* ── Bridge — product announcement ── */}
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <SceneBridge />
      </div>

      {/* ── Install ── */}
      <Section scrollHeight="250vh" stickyHeight={`calc(100vh - ${HEADER_H}px)`} topOffset={HEADER_H}>
        <Scene2Install />
      </Section>

      {/* ── Setup — profile fill ── */}
      <Section scrollHeight="350vh" stickyHeight={`calc(100vh - ${HEADER_H}px)`} topOffset={HEADER_H}>
        <Scene2Setup />
      </Section>

      {/* ── Machine — autofill ── */}
      <Section scrollHeight="400vh" stickyHeight={`calc(100vh - ${HEADER_H}px)`} topOffset={HEADER_H}>
        <Scene3Machine />
      </Section>

      {/* ── Overnight ── */}
      <Section scrollHeight="300vh" stickyHeight={`calc(100vh - ${HEADER_H}px)`} topOffset={HEADER_H}>
        <Scene4Overnight />
      </Section>

      {/* ── Morning dashboard ── */}
      <Section scrollHeight="200vh" stickyHeight={`calc(100vh - ${HEADER_H}px)`} topOffset={HEADER_H}>
        <Scene5Morning />
      </Section>

      {/* ── Analytics ── */}
      <Section scrollHeight="200vh" stickyHeight={`calc(100vh - ${HEADER_H}px)`} topOffset={HEADER_H}>
        <Scene6Analytics />
      </Section>

      {/* ── CTA — static, no scroll animation needed ── */}
      <div id="section-cta" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Scene7Ask />
      </div>
    </main>
  )
}
