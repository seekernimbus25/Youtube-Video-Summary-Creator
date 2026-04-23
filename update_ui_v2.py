import re

with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# 1. Update Fonts (Industrial/Mono)
new_fonts = '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&family=Space+Mono:wght@400;700&family=Inter:wght@400;700;900&display=swap" rel="stylesheet">'
html = re.sub(r'<link href="https://fonts\.googleapis\.com/css2\?family=Space\+Grotesk.*?rel="stylesheet">', new_fonts, html)

# 2. Complete CSS Redesign (Teenage Engineering / Rack Gear)
new_css = """    <style>
        :root {
            --bg-body: #ececec;
            --bg-panel: #fdfdfd;
            --bg-recessed: #e0e0e0;
            --text-main: #1a1a1a;
            --text-muted: #666;
            --accent-yellow: #ffe000;
            --accent-blue: #00a8ff;
            --accent-orange: #ff4e00;
            --accent-teal: #00ffc8;
            --border-width: 2px;
            --border-color: #1a1a1a;
            --shadow-flat: 4px 4px 0px rgba(0,0,0,0.1);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-body);
            background-image: url("https://www.transparenttextures.com/patterns/natural-paper.png");
            color: var(--text-main);
            line-height: 1.4;
            min-height: 100vh;
            padding: 20px;
        }

        /* Faceplate Wrapper */
        .faceplate {
            max-width: 1300px;
            margin: 0 auto;
            background: var(--bg-panel);
            border: var(--border-width) solid var(--border-color);
            box-shadow: 10px 10px 0px rgba(0,0,0,0.05);
            position: relative;
            padding: 2rem;
            min-height: calc(100vh - 40px);
            display: flex;
            flex-direction: column;
        }

        /* Nav */
        nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 2rem;
            border-bottom: var(--border-width) solid var(--border-color);
            margin-bottom: 3rem;
        }

        .logo-group { display: flex; flex-direction: column; }
        .logo { font-family: 'Space Grotesk', sans-serif; font-weight: 900; font-size: 1.8rem; color: var(--text-main); text-decoration: none; text-transform: uppercase; letter-spacing: -0.05em; line-height: 0.9; }
        .tagline { font-family: 'Space Mono', monospace; font-size: 0.6rem; color: var(--accent-orange); font-weight: 700; text-transform: uppercase; margin-top: 0.5rem; letter-spacing: 0.1em; }

        .nav-right { display: flex; gap: 1rem; }
        .nav-icon { 
            width: 40px; height: 40px; border: var(--border-width) solid var(--border-color); 
            display: flex; align-items: center; justify-content: center; cursor: pointer;
            background: #fff; transition: all 0.1s;
        }
        .nav-icon:hover { background: var(--accent-yellow); transform: translate(-2px, -2px); box-shadow: 2px 2px 0 var(--border-color); }

        /* Hero */
        .hero { text-align: left; margin-bottom: 3rem; }
        .hero h1 {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 4rem; font-weight: 900; line-height: 0.85;
            text-transform: uppercase; letter-spacing: -0.06em;
            margin-bottom: 2rem;
        }

        /* Industrial Search Bar */
        .search-area { position: relative; margin-bottom: 4rem; }
        .search-container {
            background: #fff;
            border: var(--border-width) solid var(--border-color);
            display: flex; align-items: stretch;
            padding: 0; overflow: hidden;
        }
        .search-container input {
            flex: 1; border: none; padding: 1.5rem; font-size: 1.2rem; outline: none;
            font-family: 'Space Mono', monospace; background: transparent;
        }
        .distill-btn {
            background: var(--accent-yellow);
            border: none; border-left: var(--border-width) solid var(--border-color);
            padding: 0 3rem; font-family: 'Space Grotesk', sans-serif; font-weight: 900;
            text-transform: uppercase; font-size: 1.1rem; cursor: pointer;
            transition: background 0.2s;
        }
        .distill-btn:hover { background: #ffd000; }
        .distill-btn:active { background: #333; color: #fff; }

        /* Controls Strip */
        .controls-strip {
            display: flex; gap: 2rem; align-items: center; margin-top: 1rem;
            font-family: 'Space Mono', monospace; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        }
        .toggle-unit { display: flex; align-items: center; gap: 0.5rem; }
        
        /* Custom TE Toggle */
        .switch { position: relative; display: inline-block; width: 40px; height: 20px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: #ccc; border: 2px solid var(--border-color); transition: .2s;
        }
        .slider:before {
            position: absolute; content: ""; height: 12px; width: 12px; left: 2px; bottom: 2px;
            background-color: var(--border-color); transition: .2s;
        }
        input:checked + .slider { background-color: var(--accent-blue); }
        input:checked + .slider:before { transform: translateX(20px); }

        /* Main Grid */
        .results-container-main { display: grid; grid-template-columns: 1fr 380px; gap: 2rem; margin-top: 2rem; }

        /* Modular Cards */
        .glass-card {
            background: #fff;
            border: var(--border-width) solid var(--border-color);
            padding: 1.5rem;
            position: relative;
            transition: transform 0.2s;
        }
        .glass-card::before {
            content: "•"; position: absolute; top: 5px; left: 5px; font-size: 8px; color: #ccc;
        }
        .glass-card::after {
            content: "•"; position: absolute; top: 5px; right: 5px; font-size: 8px; color: #ccc;
        }

        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        .card-header h2 { font-family: 'Space Mono', monospace; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent-orange); }

        /* Collapsibles */
        details { border: var(--border-width) solid var(--border-color); margin-bottom: 1rem; background: #fff; }
        summary {
            padding: 1rem 1.5rem; cursor: pointer; list-style: none; outline: none;
            display: flex; justify-content: space-between; align-items: center;
            font-family: 'Space Grotesk', sans-serif; font-weight: 800; font-size: 1.1rem; text-transform: uppercase;
        }
        summary::after { content: "↓"; font-family: 'Space Mono', monospace; }
        details[open] summary { background: var(--border-color); color: #fff; }
        details[open] summary::after { content: "↑"; }
        .collapsible-content { padding: 1.5rem; border-top: var(--border-width) solid var(--border-color); }

        /* Key Insights */
        .insights-list { list-style: none; }
        .insight-item { 
            display: flex; gap: 1rem; margin-bottom: 1rem; padding: 1rem; 
            border: 1px solid #eee; background: #fafafa;
        }
        .insight-number { 
            font-family: 'Space Mono', monospace; font-size: 0.7rem; font-weight: 900;
            color: #fff; background: var(--border-color); width: 24px; height: 24px;
            display: flex; align-items: center; justify-content: center; flex-shrink: 0;
        }

        /* Sidebar Stats */
        .right-col { display: flex; flex-direction: column; gap: 2rem; }
        .stats-box { 
            background: #000; color: var(--accent-teal); padding: 1.5rem; 
            font-family: 'Space Mono', monospace; border-radius: 4px;
        }
        .stats-label { color: #666; font-size: 0.6rem; text-transform: uppercase; margin-bottom: 0.5rem; display: block; }
        .stats-value { font-size: 1.4rem; font-weight: 700; }

        /* Progress Card */
        #progressCard {
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: #000; color: #fff; padding: 3rem; border: 4px solid var(--accent-yellow);
            z-index: 5000; width: 400px; text-align: center;
        }
        .progress-bar-container { background: #333; height: 10px; margin: 1.5rem 0; }
        .progress-bar { background: var(--accent-yellow); height: 100%; transition: width 0.3s; }

        /* Mindmap */
        #mindmap-card { min-height: 500px; }
        #mindmap { background: #fdfdfd; cursor: crosshair; }

        /* Export Labels */
        .export-group { display: flex; gap: 0.5rem; }
        .export-item { 
            font-family: 'Space Mono', monospace; font-size: 0.6rem; font-weight: 700;
            padding: 4px 8px; border: 1px solid var(--border-color); cursor: pointer; text-transform: uppercase;
        }
        .export-item:hover { background: var(--border-color); color: #fff; }

        /* Modal */
        .modal-overlay {
            background: rgba(0,0,0,0.8);
        }
        .settings-card { border: 4px solid var(--accent-blue) !important; background: #fff !important; }

        /* Animation */
        .reveal { animation: slideIn 0.4s cubic-bezier(0.2, 0, 0, 1) both; }
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        footer { 
            margin-top: auto; padding: 2rem 0; border-top: var(--border-width) solid var(--border-color);
            display: flex; justify-content: space-between; font-family: 'Space Mono', monospace; font-size: 0.6rem;
        }

        /* Pro Video Thumb */
        #videoProfileThumb { border: var(--border-width) solid var(--border-color); overflow: hidden; background: #000; position: relative; }
        #videoProfileThumb::after {
            content: "REC"; position: absolute; top: 10px; left: 10px; color: var(--accent-orange); font-weight: 900; font-size: 10px;
        }

        /* 90s Segment Display style */
        .segment-display { font-family: 'Space Mono', monospace; font-variant-numeric: tabular-nums; }

    </style>"""

# Replace the style block
html = re.sub(r'<style>.*?</style>', new_css, html, flags=re.DOTALL, count=1)

# 3. Update Body Structure (Add Faceplate)
if '<div class="faceplate">' not in html:
    html = html.replace('<body>', '<body><div class="faceplate">')
    html = html.replace('</footer>', '</footer></div>')

# 4. Remove duplicate style blocks if they exist (clean up from previous attempts)
# (The rsplit/rsplit logic in update_ui.py was good, but let's just make sure)
# I'll also add a "gear" and "screws" to the UI via CSS/HTML

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Updated successfully.")
