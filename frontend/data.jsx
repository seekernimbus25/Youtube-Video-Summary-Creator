/* Sample "demo" payload - mirrors the SSE response shape */
const DEMO_DATA = {
  video_id: "dm-001",
  metadata: {
    title: "How Modular Synthesizers Actually Work - A Signal-Flow Primer",
    channel: "Signal Path Lab",
    duration: "28:14",
    published: "Mar 12, 2025",
    views: "412K",
    thumbnail_url: "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?auto=format&fit=crop&q=80&w=1280",
  },
  summary: {
    video_type: "tutorial",
    key_insights: {
      bullets: [
        "The video reduces modular synthesis to a small set of reusable ideas: sound generation, shaping, control, and routing.",
        "Instead of treating modules as isolated gear categories, it explains the rack as one voltage language where audio and control signals share the same patching mindset.",
        "A major takeaway is that timbral richness comes less from buying more modules and more from understanding how filters, envelopes, and utilities interact inside a minimal voice.",
        "The walkthrough repeatedly reframes utility modules as force multipliers, which makes the case that better routing and modulation discipline matter more than expanding the rack quickly.",
        "By ending on a live patch built from almost nothing, the video argues that strong synthesis thinking is really about signal flow literacy rather than gear accumulation.",
      ],
    },
    deep_dive: {
      sections: [
        {
          heading: "What This Video Is Really Teaching",
          paragraphs: [
            "The video is strongest when it stops treating modular synthesis as a list of modules and instead reframes it as a language of signal flow. That shift matters because it lets the viewer understand the rack as a system rather than a shopping list.",
            "The opening examples make this point quickly by showing how a very small patch can still create meaningful variation. The lesson is that complexity in sound often comes from interaction and modulation, not from raw module count."
          ]
        },
        {
          heading: "How The Process Actually Works",
          paragraphs: [
            "A second major theme is that audio and control voltage should be understood together. The walkthrough keeps collapsing the mental barrier between them so the viewer starts thinking in terms of signal behavior instead of product categories.",
            "The oscillator section is useful because it grounds the abstract theory in audible differences. The video does not just name waveform types; it ties them to what later stages in the chain will do with them."
          ]
        },
        {
          heading: "Tools, Concepts, And Decision Points",
          paragraphs: [
            "The filter comparison deepens that by showing that timbre is not just about subtracting frequencies. It is also about character, resonance behavior, and how a topology responds under modulation.",
            "The utility-module argument is one of the most valuable parts of the whole video. By emphasizing attenuverters, mults, and mixers, it makes the case that flexible routing has more long-term value than buying more headline modules too early."
          ]
        },
        {
          heading: "Mistakes, Limits, And Trade-Offs",
          paragraphs: [
            "That leads into the broader educational payoff of the modulation section. The viewer is encouraged to think in relationships: source, destination, depth, polarity, and timing.",
            "The ending reinforces a pragmatic lesson about creative constraint. Expressive synthesis does not depend on owning a huge system if the underlying signal logic is clear."
          ]
        },
        {
          heading: "What The Viewer Should Actually Do",
          paragraphs: [
            "By building a living patch from a very small set of modules, the video turns the final demonstration into proof of its thesis. Mastery comes less from rack expansion and more from understanding how a few signals can be shaped, routed, and recombined with intention."
          ]
        }
      ]
    },
  },
  pitch: "A hands-on tour of the modular synthesizer signal chain - from oscillators and filters to envelopes and modulation matrices - explained by building a patch from scratch and listening to each component isolate the sound.",
  insights: [
    "Every modular synth reduces to three primitives: sound sources (VCOs), shapers (VCFs/VCAs), and controllers (LFOs/envelopes) - everything else is routing.",
    "Voltage is the universal currency: 1V/octave pitch CV, 0-5V gate, and bipolar LFOs all share the same cable and mixer topology.",
    "The filter is where character lives. Ladder filters self-oscillate cleanly; state-variable filters stay musical under heavy modulation.",
    "Envelopes are just slow, one-shot LFOs triggered by gates. Everything you do with an ADSR, you can do with a function generator.",
    "The trick to patching is not adding modules - it is finding the minimum routing that produces an interesting, evolving sound.",
  ],
  sections: [
    { t: "00:00", title: "Cold open: one patch, four mutations", body: "Starts on a single VCO -> VCF -> VCA chain, then tweaks cutoff, resonance, and envelope amount to show how much timbral space three modules cover." },
    { t: "03:42", title: "Signal vs. control voltage", body: "Explains the two kinds of cables: audio-rate signal (what you hear) and control voltage (what you modulate). Every jack is secretly both." },
    { t: "09:18", title: "Oscillators and waveform palette", body: "Saw, square, triangle, sine - each one's harmonic content and what the filter will do to it. Pulse-width modulation as a first taste of modulation." },
    { t: "14:05", title: "Filters: ladder vs. state-variable", body: "Side-by-side of a Moog-style 24dB ladder and a 12dB SVF on identical source material. Resonance behavior, self-oscillation, and tracking." },
    { t: "20:11", title: "Envelopes, LFOs, and the modulation matrix", body: "ADSR shapes, LFO shapes, and how to think about modulation depth. Introduces the attenuverter as the most underrated module on any rack." },
    { t: "25:40", title: "Building from zero: a living patch", body: "Starts with nothing plugged in and builds a 6-cable patch that evolves for two minutes without any knob movement." },
  ],
  concepts: [
    { term: "VCO", def: "Voltage-controlled oscillator - the primary sound source; pitch follows CV at 1V/octave." },
    { term: "VCF", def: "Voltage-controlled filter - shapes the harmonic content of a signal under CV control." },
    { term: "VCA", def: "Voltage-controlled amplifier - scales a signal's amplitude, usually driven by an envelope." },
    { term: "CV", def: "Control voltage - any DC-coupled signal used to modulate another module's parameter." },
    { term: "Attenuverter", def: "A knob that can both attenuate and invert an incoming CV signal. Unreasonably useful." },
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
    "Start with a single voice - VCO, VCF, VCA, one envelope, one LFO - before buying a second oscillator.",
    "Invest in utility modules (attenuverters, mults, mixers) before more sound sources; they multiply what you already have.",
    "Patch by ear, not by diagram. Plug something in, listen, then decide if it stays.",
    "Record every patch. The best-sounding patches are usually the ones you will never recreate exactly.",
  ],
  conclusion: "Modular synthesis is not about owning the biggest rack - it is about understanding voltage as a language. Once the signal chain clicks, a six-module system becomes functionally infinite.",
  transcript: {
    text: "Modular synthesis starts with understanding the signal path. Audio and control voltage are different roles in the same language, and most creative range comes from how modules are connected rather than how many are present. Filters, envelopes, and utilities become more powerful once the viewer understands how they shape and redirect signal relationships over time.",
    segments: [
      { text: "Modular synthesis starts with understanding the signal path rather than memorizing isolated modules.", start: 0, duration: 6 },
      { text: "The video shows how a simple oscillator, filter, and amplifier chain can already generate major sonic variation.", start: 6, duration: 7 },
      { text: "A core lesson is that audio and control voltage are different roles inside the same patching language.", start: 13, duration: 7 },
      { text: "Oscillator waveform choice matters because it determines what later stages in the chain can shape or remove.", start: 20, duration: 7 },
      { text: "The filter section compares ladder and state-variable behavior to show how timbre and resonance define character.", start: 27, duration: 8 },
      { text: "Envelopes and LFOs are presented as timing tools that control how the patch moves, not just whether it is loud or soft.", start: 35, duration: 8 },
      { text: "Utility modules like attenuverters and mixers are framed as force multipliers because they expand how one signal can be reused.", start: 43, duration: 8 },
      { text: "The closing patch demonstrates that a small system can remain expressive when the routing logic is intentional.", start: 51, duration: 8 },
    ],
  },
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
        { name: "Function generators combine envelope and LFO - loopable, triggerable, voltage-controllable." },
      ]},
      { name: "Utilities & Routing", children: [
        { name: "Attenuverters scale and invert CV, letting one source do work of two - underrated essentials." },
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
