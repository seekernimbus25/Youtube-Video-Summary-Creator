/* Sample "demo" payload - mirrors the SSE response shape */
const DEMO_DATA = {
  video_id: "demo",
  metadata: {
    title: "Introduction to AI Synthesis (Demo)",
    channel: "Youtube Buddy Lab",
    duration: "12:45",
    published: "May 5, 2026",
    views: "Portfolio Demo",
    thumbnail_url: "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&q=80&w=800",
  },
  summary: {
    video_type: "lecture",
    video_overview: {
      title: "The Future of AI Synthesis",
      elevator_pitch: "Explore how automated intelligence distillation transforms the way we consume video content.",
    },
    key_insights: {
      bullets: [
        "AI video synthesis is positioned as a way to compress long-form content into a faster first-pass understanding without losing the main logic of the source.",
        "The product's real value comes from structure, not just shortening: section backbones, insight bullets, and mind maps each help the viewer retain different layers of the material.",
        "Mind maps are framed as the most visual summary surface, giving users a fast conceptual layout before they decide whether to read sections or watch the original video.",
        "The strongest workflow is sequential: scan the key insights, inspect the section backbone, then export the distilled result for later reference or team sharing.",
      ],
    },
    deep_dive: {
      sections: [
        {
          heading: "What This Demo Is Really Arguing",
          paragraphs: [
            "The demo frames AI synthesis as a structural reading aid rather than a simple compression trick. Its core argument is that most people do not fail because they lack access to information; they fail because long videos hide the hierarchy of ideas, the important transitions, and the practical implications inside a linear stream.",
          ],
        },
        {
          heading: "How The Summary Surfaces Divide Their Jobs",
          paragraphs: [
            "A second layer of the argument is that different summary surfaces serve different cognitive jobs. Key insights provide a fast, high-signal scan of the whole video and help the user decide whether the source is worth deeper attention.",
            "Key sections serve a different role. They preserve chronology and let the viewer move through the original material in a way that still respects the order in which the speaker built the argument.",
          ],
        },
        {
          heading: "Why The Mind Map Matters",
          paragraphs: [
            "The mind map is positioned as the visual counterpart to the section backbone. Instead of asking the viewer to hold the whole structure in working memory, it externalizes the conceptual layout of the video.",
          ],
        },
        {
          heading: "What Makes The Product More Than A Short Summary",
          paragraphs: [
            "The demo also implies that compression alone is not enough. A short summary without explicit structure can still leave the user unable to navigate, verify, or reuse what they learned.",
            "That is why the product leans on multiple outputs rather than one monolithic answer. The user can scan, inspect, branch outward, and export according to the task in front of them.",
          ],
        },
        {
          heading: "How A User Is Supposed To Work With It",
          paragraphs: [
            "There is also a practical workflow embedded in the product design. Start with the overall synthesis, move into the section backbone to inspect the structure, and then export the relevant surface into notes or team documentation.",
          ],
        },
        {
          heading: "Why The Positioning Is Strong",
          paragraphs: [
            "Taken together, the demo presents AI synthesis as a way to make video consumption more intentional, navigable, and reusable. The claim is not that watching disappears, but that structured distillation makes watching more selective and more valuable.",
          ],
        },
      ],
    },
    key_sections: [
      {
        title: "The Problem of Information Overload",
        timestamp: "0:00",
        timestamp_seconds: 0,
        description: "Why we struggle to keep up with the volume of educational video content.",
        steps: ["Identify cognitive limits", "Measure watch-time vs retention"],
        trade_offs: ["Time spent vs value extracted"],
        notable_detail: "The average professional watches 4 hours of video weekly but retains only 15%.",
      },
      {
        title: "The Synthesis Engine",
        timestamp: "4:30",
        timestamp_seconds: 270,
        description: "How LLMs extract structural meaning from raw transcripts.",
        steps: ["Semantic chunking", "Relational mapping"],
        trade_offs: ["Depth vs Granularity"],
        notable_detail: "Context-aware extraction is 4x more accurate than keyword-based methods.",
      },
    ],
    important_concepts: [
      {
        concept: "Semantic Distillation",
        explanation: "The process of extracting core intent while discarding redundancy.",
        why_it_matters: "Increases learning speed by up to 300%.",
        example_from_video: "Reducing the transcript to its core logical skeleton.",
      },
      {
        concept: "Structural Mapping",
        explanation: "Organizing ideas into an explicit hierarchy so the viewer can see how concepts connect.",
        why_it_matters: "Improves recall and makes dense content easier to revisit.",
      },
    ],
    comparison_table: {
      applicable: true,
      headers: ["Feature", "Traditional Watching", "Youtube Buddy"],
      rows: [
        ["Speed", "1x (Real-time)", "10x (Summary)"],
        ["Structure", "Linear", "Multidimensional"],
        ["Searchability", "Low", "Instant"],
      ],
    },
    practical_recommendations: [
      "Distill complex technical roadmaps before deep-diving.",
      "Use the Mindmap to build a mental directory before watching.",
      "Share distilled DOCX files with teams for faster alignment.",
    ],
    conclusion: "AI synthesis isn't about replacing watching - it's about making your watching intentional and hyper-efficient.",
  },
  pitch: "Explore how automated intelligence distillation transforms the way we consume video content.",
  insights: [
    "AI video synthesis is positioned as a way to compress long-form content into a faster first-pass understanding without losing the main logic of the source.",
    "The product's real value comes from structure, not just shortening: section backbones, insight bullets, and mind maps each help the viewer retain different layers of the material.",
    "Mind maps are framed as the most visual summary surface, giving users a fast conceptual layout before they decide whether to read sections or watch the original video.",
    "The strongest workflow is sequential: scan the key insights, inspect the section backbone, then export the distilled result for later reference or team sharing.",
  ],
  sections: [
    {
      t: "00:00",
      title: "The Problem of Information Overload",
      body: "The demo explains why people struggle to extract usable value from long educational videos when the important ideas are buried inside a linear stream.",
    },
    {
      t: "04:30",
      title: "The Synthesis Engine",
      body: "It outlines how transcript structure, semantic chunking, and relational mapping combine to produce a more usable summary surface.",
    },
  ],
  concepts: [
    {
      term: "Semantic Distillation",
      def: "The process of extracting core intent while discarding redundancy.",
    },
    {
      term: "Structural Mapping",
      def: "Turning a long linear explanation into an explicit hierarchy of ideas and transitions.",
    },
  ],
  comparison: {
    headers: ["Feature", "Traditional Watching", "Youtube Buddy"],
    rows: [
      ["Speed", "1x (Real-time)", "10x (Summary)"],
      ["Structure", "Linear", "Multidimensional"],
      ["Searchability", "Low", "Instant"],
    ],
  },
  recommendations: [
    "Distill complex technical roadmaps before deep-diving.",
    "Use the Mindmap to build a mental directory before watching.",
    "Share distilled DOCX files with teams for faster alignment.",
  ],
  conclusion: "AI synthesis isn't about replacing watching - it's about making your watching intentional and hyper-efficient.",
  transcript: {
    text: "AI synthesis helps people process long videos faster by surfacing structure, insight bullets, and reusable outputs. The demo explains that summaries are most useful when they preserve hierarchy rather than only compressing text. It also shows why exports and mind maps matter for review and collaboration.",
    segments: [
      {
        text: "AI synthesis helps people process long videos faster by surfacing structure, insight bullets, and reusable outputs.",
        start: 0,
        duration: 8,
      },
      {
        text: "The demo explains that summaries are most useful when they preserve hierarchy rather than only compressing text.",
        start: 8,
        duration: 8,
      },
      {
        text: "It also shows why exports and mind maps matter for review and collaboration.",
        start: 16,
        duration: 7,
      },
    ],
  },
  mindmap: {
    name: "AI Synthesis",
    children: [
      {
        name: "Core Tech",
        children: [
          { name: "LLMs" },
          { name: "Transcription" },
        ],
      },
      {
        name: "Benefits",
        children: [
          { name: "Time Saving" },
          { name: "Retention" },
        ],
      },
      {
        name: "Output",
        children: [
          { name: "Mindmaps" },
          { name: "Tables" },
        ],
      },
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
