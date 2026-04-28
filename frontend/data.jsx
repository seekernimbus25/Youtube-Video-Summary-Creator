/* Sample "demo" payload — mirrors the SSE response shape */
const DEMO_DATA = {
  video_id: "dm-001",
  metadata: {
    title: "How Modular Synthesizers Actually Work — A Signal-Flow Primer",
    channel: "Signal Path Lab",
    duration: "28:14",
    published: "Mar 12, 2025",
    views: "412K",
    thumbnail_url: "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?auto=format&fit=crop&q=80&w=1280",
  },
  screenshots: [
    { url: "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&q=80&w=960", caption: "Patch cable routing — control vs audio" },
    { url: "https://images.unsplash.com/photo-1511379938547-c1f69419868d?auto=format&fit=crop&q=80&w=960", caption: "Envelope shaping a VCA stage" },
  ],
  pitch: "A hands-on tour of the modular synthesizer signal chain — from oscillators and filters to envelopes and modulation matrices — explained by building a patch from scratch and listening to each component isolate the sound.",
  insights: [
    "Every modular synth reduces to three primitives: sound sources (VCOs), shapers (VCFs/VCAs), and controllers (LFOs/envelopes) — everything else is routing.",
    "Voltage is the universal currency: 1V/octave pitch CV, 0–5V gate, and bipolar LFOs all share the same cable and mixer topology.",
    "The filter is where 'character' lives. Ladder filters self-oscillate cleanly; state-variable filters stay musical under heavy modulation.",
    "Envelopes are just slow, one-shot LFOs triggered by gates. Everything you do with an ADSR, you can do with a function generator.",
    "The trick to patching isn't adding modules — it's finding the minimum routing that produces an interesting, evolving sound.",
  ],
  sections: [
    { t: "00:00", title: "Cold open: one patch, four mutations", body: "Starts on a single VCO → VCF → VCA chain, then tweaks cutoff, resonance, and envelope amount to show how much timbral space three modules cover.", shots: [
      { src: "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&q=80&w=800", caption: "00:00 · Initial three-module voice" },
      { src: "https://images.unsplash.com/photo-1511379938547-c1f69419868d?auto=format&fit=crop&q=80&w=800", caption: "00:45 · Same chain, resonance opened" },
    ] },
    { t: "03:42", title: "Signal vs. control voltage", body: "Explains the two kinds of cables: audio-rate signal (what you hear) and control voltage (what you modulate). Every jack is secretly both." },
    { t: "09:18", title: "Oscillators and waveform palette", body: "Saw, square, triangle, sine — each one's harmonic content and what the filter will do to it. Pulse-width modulation as a first taste of modulation." },
    { t: "14:05", title: "Filters: ladder vs. state-variable", body: "Side-by-side of a Moog-style 24dB ladder and a 12dB SVF on identical source material. Resonance behavior, self-oscillation, and tracking." },
    { t: "20:11", title: "Envelopes, LFOs, and the modulation matrix", body: "ADSR shapes, LFO shapes, and how to think about modulation depth. Introduces the 'attenuverter' as the most underrated module on any rack." },
    { t: "25:40", title: "Building from zero: a living patch", body: "Starts with nothing plugged in and builds a 6-cable patch that evolves for two minutes without any knob movement." },
  ],
  concepts: [
    { term: "VCO", def: "Voltage-controlled oscillator — the primary sound source; pitch follows CV at 1V/octave." },
    { term: "VCF", def: "Voltage-controlled filter — shapes the harmonic content of a signal under CV control." },
    { term: "VCA", def: "Voltage-controlled amplifier — scales a signal's amplitude, usually driven by an envelope." },
    { term: "CV", def: "Control voltage — any DC-coupled signal used to modulate another module's parameter." },
    { term: "Attenuverter", def: "A knob that can both attenuate AND invert an incoming CV signal. Unreasonably useful." },
    { term: "Self-oscillation", def: "When a filter's resonance is turned up enough that it becomes a sine-wave oscillator." },
  ],
  comparison: {
    headers: ["Filter Type", "Slope", "Character", "Self-Oscillates", "Best for"],
    rows: [
      ["Moog-style ladder", "24 dB/oct", "Warm, fat, grumbly", "Yes, cleanly", "Bass, leads"],
      ["State-variable (SVF)", "12 dB/oct", "Neutral, precise", "Yes, brightly", "Plucks, FM"],
      ["Sallen-Key", "12 dB/oct", "Bright, clean", "Sometimes", "Chirpy leads"],
      ["Diode ladder", "24 dB/oct", "Gritty, aggressive", "Yes, rough", "Acid, bass"],
    ],
  },
  recommendations: [
    "Start with a single voice — VCO, VCF, VCA, one envelope, one LFO — before buying a second oscillator.",
    "Invest in utility modules (attenuverters, mults, mixers) before more sound sources; they multiply what you already have.",
    "Patch by ear, not by diagram. Plug something in, listen, then decide if it stays.",
    "Record every patch. The best-sounding patches are usually the ones you'll never recreate exactly.",
  ],
  conclusion: "Modular synthesis isn't about owning the biggest rack — it's about understanding voltage as a language. Once the signal chain clicks, a six-module system becomes functionally infinite.",

  mindmap: {
    name: "How Modular Synths Work",
    children: [
      { name: "Sound Sources", children: [
        { name: "VCOs produce the core waveforms; pitch tracks voltage at 1V per octave for musical scaling." },
        { name: "Noise generators output broadband signal, useful for percussion and random modulation." },
        { name: "Sample & Hold captures a voltage on a clock tick, generating stepped random sequences." },
      ]},
      { name: "Shapers", children: [
        { name: "Voltage-controlled filters remove harmonics; cutoff and resonance define timbral character." },
        { name: "Ladder topologies sound warm and grumbly; SVFs stay neutral and precise under heavy mod." },
        { name: "VCAs scale amplitude under CV, shaping loudness contour independently from pitch." },
        { name: "Waveshapers and folders add harmonics nonlinearly, turning sines into brass-like textures." },
      ]},
      { name: "Controllers", children: [
        { name: "ADSR envelopes apply one-shot shapes to CV on every gate, most often driving VCA and VCF." },
        { name: "LFOs provide slow periodic modulation for vibrato, tremolo, and filter sweeps." },
        { name: "Function generators combine envelope and LFO — loopable, triggerable, voltage-controllable." },
      ]},
      { name: "Utilities & Routing", children: [
        { name: "Attenuverters scale and invert CV, letting one source do work of two — underrated essentials." },
        { name: "Mults copy a signal to many destinations without degradation for parallel processing." },
        { name: "Mixers sum audio or CV; summing CV is how a mod matrix is built from simple parts." },
      ]},
    ],
  },
};

const PROGRESS_STEPS = [
  "VALIDATE",
  "FETCH META",
  "TRANSCRIBE",
  "DISTILL",
  "RENDER",
];

Object.assign(window, { DEMO_DATA, PROGRESS_STEPS });
