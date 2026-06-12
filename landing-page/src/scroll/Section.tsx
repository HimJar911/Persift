import { useRef, type ReactNode } from "react"
import { useScroll, useSpring } from "framer-motion"
import { SceneProgressContext } from "./SceneContext"

type SectionProps = {
  children: ReactNode
  scrollHeight?: string
  stickyHeight?: string
  topOffset?: number
}

export function Section({
  children,
  scrollHeight = "300vh",
  stickyHeight = "100vh",
  topOffset = 0,
}: SectionProps) {
  const ref = useRef<HTMLDivElement>(null)

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end end"],
  })

  // Smooth out micro-jitter without adding perceptible lag
  const progress = useSpring(scrollYProgress, { stiffness: 400, damping: 60, restDelta: 0.0001 })

  return (
    <SceneProgressContext.Provider value={progress}>
      <div ref={ref} style={{ position: "relative", height: scrollHeight }}>
        <div style={{
          position: "sticky",
          top: topOffset,
          height: stickyHeight,
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}>
          {children}
        </div>
      </div>
    </SceneProgressContext.Provider>
  )
}
