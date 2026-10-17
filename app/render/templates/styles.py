"""Styles.css — Tekno Pusula marka stili (referans tasarıma birebir uygun)."""
CSS = """
@font-face {
  font-family: 'Bebas Neue';
  src: url('{{ font_bebas }}') format('truetype');
  font-weight: 400;
  font-display: block;
}
@font-face {
  font-family: 'Montserrat';
  src: url('{{ font_montserrat }}') format('truetype');
  font-weight: 100 900;
  font-display: block;
}
@font-face {
  font-family: 'Inter';
  src: url('{{ font_inter }}') format('truetype');
  font-weight: 100 900;
  font-display: block;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body {
  width: {{ width }}px;
  height: {{ height }}px;
  overflow: hidden;
  background: #07090d;
}

.slide {
  position: relative;
  width: {{ width }}px;
  height: {{ height }}px;
  overflow: hidden;
  background: #07090d;
  font-family: 'Inter', 'Noto Color Emoji', sans-serif;
  color: #FFFFFF;
}

.slide-bg {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center top;
}
/* Kapak: üst %58 görsel net görünür, aşağı doğru yumuşakça siyaha erir */
.slide-bg.cover-mask::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(7,9,13,0.18) 0%,
    rgba(7,9,13,0.10) 38%,
    rgba(7,9,13,0.75) 56%,
    #07090d 66%,
    #07090d 100%
  );
}
/* İç slaytlar: arka plan görseli hafif blur + koyu karartma ama görünür doku */
.slide-bg.inner-mask {
  filter: blur(4px) brightness(0.42);
  transform: scale(1.04);
}
.slide-bg.inner-mask::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(7,9,13,0.35) 0%,
    rgba(7,9,13,0.55) 50%,
    rgba(7,9,13,0.92) 100%
  );
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 12px 26px;
  border-radius: 999px;
  background: rgba(18,20,24,0.82);
  border: 1px solid rgba(255,255,255,0.12);
  color: #FFFFFF;
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 21px;
  letter-spacing: 0.5px;
}

.handle-pill {
  position: absolute;
  top: 48px;
  left: 56px;
  z-index: 5;
}

.source-tags {
  position: absolute;
  top: 48px;
  right: 56px;
  display: flex;
  gap: 14px;
  z-index: 5;
}
.source-tag {
  padding: 14px 28px;
  border-radius: 999px;
  background: rgba(12,18,32,0.88);
  border: 1.5px solid rgba(160,185,220,0.35);
  color: #FFFFFF;
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 19px;
  letter-spacing: 1.5px;
}

/* ---------- KAPAK ---------- */
.cover-center {
  position: absolute;
  left: 56px;
  right: 56px;
  top: 710px;
  bottom: 130px;
  overflow: hidden;
  z-index: 4;
}
.cover-divider {
  position: relative;
  height: 1px;
  background: linear-gradient(to right, rgba(255,255,255,0.06), rgba(255,255,255,0.22), rgba(255,255,255,0.06));
  margin: 0 0 36px;
}
.cover-logo {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: #0d1118;
  border: 1.5px solid rgba(255,255,255,0.22);
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover-logo svg, .cover-logo img { width: 28px; height: 28px; }
.cover-logo .logo-empty {
  width: 22px; height: 2px;
  background: rgba(255,255,255,0.4);
}

.category-label {
  display: inline-block;
  padding: 9px 20px;
  background: rgba(0, 60, 80, 0.35);
  border: 1.5px solid rgba(0, 216, 255, 0.55);
  border-radius: 8px;
  color: #00D8FF;
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 20px;
  letter-spacing: 2.2px;
  margin-bottom: 24px;
}

.cover-title {
  font-family: 'Bebas Neue', sans-serif;
  font-size: {{ cover_title_px }}px;
  line-height: 1.22;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #FFFFFF;
  margin-bottom: 18px;
}
.cover-title .hl-yellow { color: #FFE000; text-shadow: 0 0 32px rgba(255,224,0,0.28); }
.cover-title .hl-cyan { color: #00D8FF; text-shadow: 0 0 32px rgba(0,216,255,0.32); }

.cover-subtitle {
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 25px;
  line-height: 1.38;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: #9AA6B8;
}

.cover-bottom-bar {
  position: absolute;
  left: 56px;
  right: 56px;
  bottom: 120px;
  height: 1px;
  background: rgba(255,255,255,0.08);
  z-index: 4;
}

.cover-bottom-left {
  position: absolute;
  bottom: 42px;
  left: 56px;
  z-index: 5;
}
.kaydir-btn {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  padding: 14px 30px;
  border-radius: 999px;
  background: rgba(18,22,30,0.92);
  border: 1.5px solid rgba(255,255,255,0.18);
  color: #FFFFFF;
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 20px;
  letter-spacing: 1.8px;
}
.kaydir-btn .arrow { color: #FFE000; font-size: 24px; }

.progress {
  position: absolute;
  bottom: 54px;
  right: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 5;
}
.progress .dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: rgba(169,180,194,0.42);
}
.progress .dot.active {
  width: 42px;
  background: #00D8FF;
  box-shadow: 0 0 16px rgba(0,216,255,0.65);
}

/* ---------- İÇ SLAYT ---------- */
.slide-tag {
  position: absolute;
  top: 52px;
  left: 56px;
  z-index: 5;
  padding: 12px 26px;
  border-radius: 999px;
  background: rgba(12,20,30,0.78);
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 19px;
  letter-spacing: 2px;
  text-transform: uppercase;
}
.slide-tag.yellow { border: 1.5px solid rgba(255,224,0,0.65); color: #FFE000; }
.slide-tag.cyan { border: 1.5px solid rgba(0,216,255,0.65); color: #00D8FF; }

.page-counter {
  position: absolute;
  top: 52px;
  right: 56px;
  z-index: 5;
  padding: 12px 24px;
  border-radius: 999px;
  background: rgba(38,44,54,0.85);
  border: 1px solid rgba(255,255,255,0.16);
  color: #FFFFFF;
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 20px;
}

.inner-content {
  position: absolute;
  top: 290px;
  left: 56px;
  right: 56px;
  bottom: 130px;
  z-index: 4;
}

.inner-heading {
  font-family: 'Montserrat', sans-serif;
  font-weight: 900;
  font-size: {{ heading_px }}px;
  line-height: 1.24;
  color: #FFFFFF;
  margin-bottom: 34px;
}
.inner-heading .hl-yellow { color: #FFE000; text-shadow: 0 0 28px rgba(255,224,0,0.28); }
.inner-heading .hl-cyan { color: #00D8FF; text-shadow: 0 0 28px rgba(0,216,255,0.35); }

.card {
  position: relative;
  background: rgba(24,28,36,0.78);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 16px;
  padding: 32px 38px 34px 46px;
  margin-bottom: 26px;
  overflow: hidden;
}
.card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
}
.card.yellow::before { background: #FFE000; }
.card.cyan::before { background: #00D8FF; }

.card-badge {
  display: inline-block;
  padding: 5px 14px;
  margin-bottom: 14px;
  border-radius: 999px;
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 17px;
  letter-spacing: 1px;
  background: rgba(0,216,255,0.14);
  border: 1px solid rgba(0,216,255,0.32);
  color: #00D8FF;
}

.card-title {
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 31px;
  line-height: 1.26;
  color: #FFFFFF;
  margin-bottom: 12px;
}
.card-body {
  font-family: 'Inter', sans-serif;
  font-weight: 400;
  font-size: 24px;
  line-height: 1.46;
  color: #C5CEDB;
}

/* ---------- RAKAM SLAYTI ---------- */
.stat-wrap {
  position: absolute;
  top: 410px;
  left: 56px;
  right: 56px;
  z-index: 4;
}
.stat-card {
  position: relative;
  background: rgba(28,32,40,0.82);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 18px;
  padding: 56px 54px 56px 60px;
  text-align: center;
  overflow: hidden;
}
.stat-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  background: #FFE000;
}
.big-stat {
  font-family: 'Montserrat', sans-serif;
  font-weight: 900;
  font-size: {{ stat_px }}px;
  line-height: 1.26;
  color: #FFE000;
  margin-bottom: 22px;
}
.stat-caption {
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 29px;
  line-height: 1.32;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #FFFFFF;
  margin-bottom: 24px;
}
.stat-quote {
  font-family: 'Inter', sans-serif;
  font-weight: 400;
  font-size: 23px;
  line-height: 1.48;
  color: #B8C2D0;
}

/* ---------- CTA SLAYTI ---------- */
.cta-wrap {
  position: absolute;
  top: 280px;
  left: 56px;
  right: 56px;
  bottom: 130px;
  z-index: 4;
}
.cta-card {
  position: relative;
  background: rgba(22,28,38,0.82);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 18px;
  padding: 46px 48px 46px 54px;
  text-align: center;
  overflow: hidden;
  margin-bottom: 34px;
}
.cta-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
}
.cta-card.cyan::before { background: #00D8FF; }
.cta-card.yellow::before { background: #FFE000; }

.cta-kicker {
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 21px;
  letter-spacing: 1.5px;
  margin-bottom: 20px;
}
.cta-card.cyan .cta-kicker { color: #FFE000; text-transform: uppercase; }
.cta-card.yellow .cta-kicker { color: #B8C2D0; font-weight: 600; font-size: 22px; }

.cta-question {
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 38px;
  line-height: 1.30;
  color: #FFFFFF;
  margin-bottom: 22px;
}
.cta-note {
  font-family: 'Inter', sans-serif;
  font-size: 22px;
  line-height: 1.45;
  color: #8E9BAE;
}
.cta-big {
  font-family: 'Montserrat', sans-serif;
  font-weight: 900;
  font-size: 34px;
  line-height: 1.34;
  color: #FFE000;
  margin-bottom: 18px;
}
.cta-actions {
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 22px;
  line-height: 1.45;
  color: #FFFFFF;
}

/* ---------- ORTAK ALT ALAN ---------- */
.inner-footer {
  position: absolute;
  bottom: 48px;
  left: 56px;
  right: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 5;
}
.inner-footer .handle {
  color: #9AA6B8;
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 22px;
  letter-spacing: 0.5px;
}
.inner-footer .progress {
  position: static;
}

/* ---------- KOD KUTUSU (eğitim) ---------- */
.code-box {
  background: rgba(10,14,20,0.92);
  border: 1px solid rgba(0,216,255,0.35);
  border-radius: 12px;
  padding: 22px 26px;
  margin-top: 16px;
  font-family: 'Noto Sans Mono', 'Consolas', monospace;
  font-size: 21px;
  line-height: 1.5;
  color: #00D8FF;
  white-space: pre-wrap;
  word-break: break-word;
}
"""