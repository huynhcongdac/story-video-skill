import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont } from "@remotion/google-fonts/BeVietnamPro";
import timeline from "./timeline.json";

const { fontFamily } = loadFont("normal", { weights: ["600", "800", "900"], subsets: ["vietnamese", "latin"] });

type Card = { n: string; title: string; sub: string };
type Shot = { from: number; dur: number; img: string; fx: string; card?: Card; cd?: { start: number; n: number } };
type Word = { w: string; from: number; to: number; hl: boolean };
type Caption = { from: number; to: number; words: Word[] };

// On-screen labels — override any of them with "labels" in story.json (e.g. for English videos)
const LB = {
  suspect: "NGHI PHẠM", clue: "MANH MỐI", episode: "VỤ ÁN SỐ", question1: "BẠN ĐOÁN", question2: "AI LÀ HUNG THỦ?",
  comment: "Bình luận trước khi xem tiếp 👇", next: "Vụ án tiếp theo?", follow: "Theo dõi kênh ngay",
  ...((timeline as any).labels || {}),
};

// Shots that enter with a HARD CUT (no crossfade): a shock has to hit immediately
const HARD = new Set(["shock", "punch", "glitch", "flashshock", "reveal"]);
const FADE = 7;
const W = 1080, H = 1920;

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Decaying shake: amp px over the first `len` frames
const shake = (f: number, seed: number, amp: number, len: number) => {
  const k = Math.max(0, 1 - f / len);
  return [(random(`x${seed}-${f}`) - 0.5) * 2 * amp * k, (random(`y${seed}-${f}`) - 0.5) * 2 * amp * k];
};

const ImgLayer: React.FC<{ src: string; style?: React.CSSProperties }> = ({ src, style }) => (
  <Img src={staticFile(src)} style={{ position: "absolute", width: W, height: H, objectFit: "cover", ...style }} />
);

const ShotView: React.FC<{ shot: Shot; idx: number; lead: number }> = ({ shot, idx, lead }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = frame - lead;                       // frames since the shot officially starts
  const d = shot.dur;
  const fx = shot.fx;
  const t = interpolate(f, [0, d], [0, 1], clamp);
  const dir = idx % 2 ? 1 : -1;

  let scale = 1.06 + 0.12 * t, tx = 0, ty = -20 * t;
  if (fx === "pan") { scale = 1.22; tx = dir * interpolate(t, [0, 1], [-55, 55]); ty = 0; }
  if (fx === "slow" || fx === "end") { scale = 1.04 + 0.07 * t; ty = -10 * t; }
  if (fx === "reveal") { scale = 1.0 + 0.4 * t; ty = 0; }
  const punchy = ["punch", "shock", "flashshock", "reveal"].includes(fx);
  if (punchy) {
    const sp = spring({ frame: Math.max(0, f), fps, config: { damping: 14, stiffness: 180 } });
    scale += interpolate(sp, [0, 1], [0.35, 0]);
  }
  const [sx, sy] = ["shock", "flashshock", "reveal"].includes(fx) ? shake(Math.max(0, f), idx, 26, 16)
    : fx === "shake" ? shake(f % 9, idx * 7 + Math.floor(f / 9), 7, 12) : [0, 0];

  const isFlash = fx.startsWith("flash");
  const filter = isFlash ? "grayscale(1) contrast(1.25) brightness(0.95) sepia(0.18)" : "contrast(1.06) saturate(1.05)";
  const opacity = HARD.has(fx) || shot.from === 0 ? 1 : interpolate(frame, [0, FADE], [0, 1], clamp);
  const transform = `translate(${tx + sx}px, ${ty + sy}px) scale(${scale})`;

  // RGB split: first 10 frames of a shock, and on glitch beats
  const glitchOn = fx === "glitch" && (f % 14 < 3 || f < 6);
  const rgb = (["shock", "flashshock", "reveal"].includes(fx) && f < 10) || glitchOn ? (glitchOn ? 16 : 22 * (1 - f / 10)) : 0;

  return (
    <AbsoluteFill style={{ opacity, overflow: "hidden", backgroundColor: "#000" }}>
      <AbsoluteFill style={{ transform, filter }}>
        <ImgLayer src={shot.img} />
        {rgb > 0 && <>
          <ImgLayer src={shot.img} style={{ left: -rgb, mixBlendMode: "screen", opacity: 0.55, filter: "sepia(1) saturate(8) hue-rotate(-40deg)" }} />
          <ImgLayer src={shot.img} style={{ left: rgb, mixBlendMode: "screen", opacity: 0.45, filter: "sepia(1) saturate(8) hue-rotate(150deg)" }} />
        </>}
        {glitchOn && [0, 1, 2].map((k) => {
          const y0 = random(`gy${idx}-${f}-${k}`) * 85;
          return <ImgLayer key={k} src={shot.img} style={{ clipPath: `inset(${y0}% 0 ${100 - y0 - 6}% 0)`, left: (random(`gx${idx}-${f}-${k}`) - 0.5) * 120 }} />;
        })}
      </AbsoluteFill>
      {/* white flash on hard openings */}
      {punchy && <AbsoluteFill style={{ backgroundColor: "#fff", opacity: interpolate(f, [0, 4], [0.75, 0], clamp) }} />}
      {fx === "reveal" && <AbsoluteFill style={{ backgroundColor: "#7a0000", mixBlendMode: "multiply", opacity: 0.25 + 0.15 * Math.sin(f / 6) }} />}
      {isFlash && <AbsoluteFill style={{ boxShadow: "inset 0 0 260px 90px rgba(0,0,0,.85)" }} />}
      {shot.card && <CardView fx={fx} card={shot.card} f={f} />}
      {fx === "title" && <TitleView f={f} />}
      {fx === "question" && <QuestionView f={f} cd={shot.cd ? { at: shot.cd.start - shot.from, n: shot.cd.n } : undefined} />}
      {fx === "end" && <EndView f={f} />}
    </AbsoluteFill>
  );
};

const pop = (f: number, at = 0) => spring({ frame: Math.max(0, f - at), fps: 30, config: { damping: 13, stiffness: 160 } });

const CardView: React.FC<{ fx: string; card: Card; f: number }> = ({ fx, card, f }) => {
  const clue = fx === "clue";
  const p = pop(f, 4);
  return (
    <div style={{ position: "absolute", left: 70, top: 250, transform: `translateX(${interpolate(p, [0, 1], [-700, 0])}px)`, fontFamily }}>
      <div style={{ display: "inline-block", padding: "12px 26px", borderRadius: 12, background: clue ? "#f5c518" : "#d62828",
        color: clue ? "#1a1300" : "#fff", fontSize: 40, fontWeight: 900, letterSpacing: 2, transform: `rotate(-2deg) scale(${interpolate(pop(f, 8), [0, 1], [1.6, 1])})` }}>
        {clue ? `${LB.clue} #${card.n}` : `${LB.suspect} #${card.n}`}
      </div>
      <div style={{ marginTop: 18, padding: "18px 30px", background: "rgba(8,8,10,.82)", borderLeft: `10px solid ${clue ? "#f5c518" : "#d62828"}`,
        color: "#fff", maxWidth: 860 }}>
        <div style={{ fontSize: clue ? 56 : 92, fontWeight: 900, lineHeight: 1.05, letterSpacing: -1 }}>{card.title}</div>
        {card.sub && <div style={{ fontSize: 40, fontWeight: 600, color: "#d8d2c8", marginTop: 8 }}>{card.sub}</div>}
      </div>
    </div>
  );
};

// Split the title into two lines of similar length
const splitTitle = (t: string) => {
  const w = t.split(" "); let best = 1, diff = 1e9;
  for (let i = 1; i < w.length; i++) {
    const d = Math.abs(w.slice(0, i).join(" ").length - w.slice(i).join(" ").length);
    if (d < diff) { diff = d; best = i; }
  }
  return <>{w.slice(0, best).join(" ")}<br />{w.slice(best).join(" ")}</>;
};

const TitleView: React.FC<{ f: number }> = ({ f }) => {
  const p = pop(f, 2);
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", fontFamily, background: `rgba(0,0,0,${0.45 * p})` }}>
      {timeline.series && <div style={{ color: "#fff", fontSize: 34, fontWeight: 800, letterSpacing: 6, opacity: p, background: "#d62828", padding: "6px 18px" }}>{timeline.series}</div>}
      <div style={{ color: "#f5c518", fontSize: 40, fontWeight: 800, letterSpacing: 14, opacity: p, marginTop: 22 }}>{LB.episode} {timeline.episode ?? 1}</div>
      <div style={{ color: "#fff", fontSize: 92, fontWeight: 900, textAlign: "center", lineHeight: 1.0, whiteSpace: "nowrap", letterSpacing: interpolate(p, [0, 1], [30, -2]),
        textShadow: "0 10px 50px rgba(0,0,0,.9)", opacity: p, marginTop: 20, maxWidth: 980 }}>{splitTitle(timeline.title)}</div>
    </AbsoluteFill>
  );
};

// Countdown after the question: the number beats each second, the ring empties every second, the screen darkens.
// Do NOT highlight suspects one by one — the last one highlighted reads as a hint.
const Countdown: React.FC<{ f: number; n: number }> = ({ f, n }) => {
  if (f < 0 || f >= n * 30) return null;
  const k = Math.floor(f / 30), within = f % 30, num = n - k;
  const beat = spring({ frame: within, fps: 30, config: { damping: 9, stiffness: 220 } });
  const R = 150, C = 2 * Math.PI * R;
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", fontFamily }}>
      <AbsoluteFill style={{ backgroundColor: "#000", opacity: 0.35 + 0.12 * k }} />
      <div style={{ position: "relative", width: 380, height: 380, transform: `scale(${interpolate(beat, [0, 1], [1.25, 1])})`, marginTop: 120 }}>
        <svg width={380} height={380} style={{ position: "absolute", inset: 0 }}>
          <circle cx={190} cy={190} r={R} fill="rgba(10,10,12,.72)" stroke="rgba(255,255,255,.18)" strokeWidth={14} />
          <circle cx={190} cy={190} r={R} fill="none" stroke={num === 1 ? "#d62828" : "#f5c518"} strokeWidth={14} strokeLinecap="round"
            strokeDasharray={C} strokeDashoffset={C * (within / 30)} transform="rotate(-90 190 190)" />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
          color: num === 1 ? "#ff4d4d" : "#fff", fontSize: 220, fontWeight: 900, textShadow: "0 10px 40px rgba(0,0,0,.9)" }}>{num}</div>
      </div>
    </AbsoluteFill>
  );
};

const QuestionView: React.FC<{ f: number; cd?: { at: number; n: number } }> = ({ f, cd }) => (
  <AbsoluteFill style={{ fontFamily, alignItems: "center", paddingTop: 260 }}>
    {cd && <Countdown f={f - cd.at} n={cd.n} />}
    <div style={{ color: "#fff", fontSize: 96, fontWeight: 900, textAlign: "center", lineHeight: 1.02, transform: `scale(${pop(f, 3)})`,
      textShadow: "0 10px 40px rgba(0,0,0,.9)" }}>{LB.question1}<br /><span style={{ color: "#f5c518" }}>{LB.question2}</span></div>
    <div style={{ marginTop: 30, padding: "14px 34px", borderRadius: 999, background: "#d62828", color: "#fff", fontSize: 44, fontWeight: 800,
      opacity: interpolate(f, [20, 30], [0, 1], clamp) }}>{LB.comment}</div>
  </AbsoluteFill>
);

const EndView: React.FC<{ f: number }> = ({ f }) => (
  <AbsoluteFill style={{ fontFamily, justifyContent: "center", alignItems: "center", background: `rgba(0,0,0,${interpolate(f, [0, 20], [0, 0.55], clamp)})` }}>
    <div style={{ color: "#fff", fontSize: 84, fontWeight: 900, textAlign: "center", transform: `scale(${pop(f, 4)})` }}>{LB.next}</div>
    <div style={{ marginTop: 26, padding: "18px 40px", borderRadius: 999, background: "#f5c518", color: "#1a1300", fontSize: 50, fontWeight: 900,
      opacity: interpolate(f, [14, 24], [0, 1], clamp) }}>{LB.follow}</div>
  </AbsoluteFill>
);

// Captions appear WORD BY WORD as spoken; current word yellow + slight pop, keywords orange-red
const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const c = (timeline.captions as Caption[]).find((x) => frame >= x.from && frame < x.to);
  if (!c) return null;
  return (
    <div style={{ position: "absolute", left: 80, right: 140, top: 1250, textAlign: "center", fontFamily, fontWeight: 900, fontSize: 74,
      lineHeight: 1.22, letterSpacing: -0.5 }}>
      {c.words.filter((w) => frame >= w.from - 2).map((w, i) => {
        const cur = frame >= w.from - 2 && frame < w.to + 2;
        const s = interpolate(frame, [w.from - 2, w.from + 3], [1.14, 1], clamp);
        return (
          <span key={i} style={{ display: "inline-block", margin: "0 18px", transform: `scale(${cur ? s * 1.04 : 1})`,
            color: w.hl ? "#ff6b3d" : cur ? "#ffd84d" : "#fff",
            WebkitTextStroke: "3px #000", paintOrder: "stroke fill", textShadow: "0 6px 18px rgba(0,0,0,.85)" }}>{w.w}</span>
        );
      })}
    </div>
  );
};

const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ pointerEvents: "none", mixBlendMode: "overlay", opacity: 0.12 }}>
      <svg width={W} height={H}>
        <filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={frame % 12} /></filter>
        <rect width={W} height={H} filter="url(#g)" />
      </svg>
    </AbsoluteFill>
  );
};

export const Story: React.FC = () => {
  const shots = timeline.shots as Shot[];
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {shots.map((s, i) => {
        const lead = HARD.has(s.fx) || s.from === 0 ? 0 : FADE;
        return (
          <Sequence key={i} from={s.from - lead} durationInFrames={s.dur + lead + 1}>
            <ShotView shot={s} idx={i} lead={lead} />
          </Sequence>
        );
      })}
      <AbsoluteFill style={{ pointerEvents: "none", background: "radial-gradient(120% 85% at 50% 45%, transparent 55%, rgba(0,0,0,.65) 100%)" }} />
      <Grain />
      <Captions />
      <Audio src={staticFile("audio.wav")} />
    </AbsoluteFill>
  );
};
