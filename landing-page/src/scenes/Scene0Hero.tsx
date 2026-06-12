import deskImg from "../assets/desk.png"
import { WorkbenchAnimation } from "../components/WorkbenchAnimation"

const BG = "#0c0a08"
const IMG_W = 1522
const IMG_H = 688

// WorkflowAnimation position in image-natural coordinate space
const ANIM_L = 538
const ANIM_T = 37
const ANIM_W = 501
const ANIM_H = 331

export function Scene0Hero() {
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      {/* Single cover unit — image + animation scale together */}
      <div style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        width: `max(100%, calc(100vh * ${IMG_W} / ${IMG_H}))`,
        height: `max(100%, calc(100vw * ${IMG_H} / ${IMG_W}))`,
      }}>
        <img
          src={deskImg}
          alt=""
          draggable={false}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block", userSelect: "none" }}
        />
        <div style={{
          position: "absolute",
          left: `${(ANIM_L / IMG_W * 100).toFixed(3)}%`,
          top: `${(ANIM_T / IMG_H * 100).toFixed(3)}%`,
          width: `${(ANIM_W / IMG_W * 100).toFixed(3)}%`,
          height: `${(ANIM_H / IMG_H * 100).toFixed(3)}%`,
          borderRadius: 6,
          overflow: "hidden",
          background: "#0c0a08",
          isolation: "isolate",
        }}>
          <div style={{ position: "absolute", inset: 0, borderRadius: 6, overflow: "hidden" }}>
            <WorkbenchAnimation />
          </div>
        </div>
      </div>

      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 300, background: `linear-gradient(to top, ${BG}, transparent)`, pointerEvents: "none" }} />

      {/* Tagline — sits just above the bottom fade */}
      <div style={{
        position: "absolute",
        bottom: 48,
        left: 0, right: 0,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}>
        <p style={{
          margin: 0,
          fontFamily: "Inter, sans-serif",
          fontSize: "clamp(13px, 1.2vw, 17px)",
          fontWeight: 500,
          color: "rgba(243,236,225,0.95)",
          letterSpacing: "0.01em",
          textAlign: "center",
          textShadow: "0 2px 24px rgba(0,0,0,0.9), 0 1px 4px rgba(0,0,0,0.8)",
        }}>
          Your job search doesn&apos;t stop when <span style={{ color: "var(--amber)" }}>YOU</span> do.
        </p>
      </div>
      <div style={{ position: "absolute", top: 0, left: 0, bottom: 0, width: "27%", background: `linear-gradient(to right, ${BG}, transparent)`, pointerEvents: "none" }} />
      <div style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: "27%", background: `linear-gradient(to left, ${BG}, transparent)`, pointerEvents: "none" }} />
    </div>
  )
}
