import re

html_path = 'frontend/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

new_css = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Helvetica+Neue:wght@400;700;900&family=Inter:wght@400;600;800&family=Space+Mono:wght@400;700&display=swap');

        :root {
            /* Extreme Skeuomorphic Palette */
            --plastic-base: #e5e3db;
            --plastic-light: #f5f4ef;
            --plastic-dark: #d1cfc7;
            --metal-silver: #d8d8d8;
            --metal-dark: #888888;
            
            --btn-orange-top: #ff8c00;
            --btn-orange-bottom: #e65c00;
            --btn-orange-side: #993300;
            
            --screen-bg: #111111;
            --text-dark: #2b2b2b;
            --text-muted: #6b6b6b;
            
            --accent-cyan: #00e5ff;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
            background-color: #2a2a2a; /* Dark background so the device pops */
            background-image: radial-gradient(circle at center, #3a3a3a, #1a1a1a);
            color: var(--text-dark);
            line-height: 1.5;
            min-height: 100vh;
            padding: 40px 20px;
            display: flex;
            align-items: flex-start;
            justify-content: center;
        }

        /* The Main Device Body */
        .faceplate {
            width: 100%;
            max-width: 1200px;
            background: var(--plastic-base);
            border: 2px solid #b8b6b0;
            border-radius: 24px;
            box-shadow: 
                inset 0 4px 6px rgba(255,255,255,0.8), 
                inset 0 -4px 6px rgba(0,0,0,0.1),
                0 20px 50px rgba(0,0,0,0.6),
                0 0 0 10px #c4c2ba; /* Outer rim */
            position: relative;
            padding: 3rem;
            min-height: 80vh;
            display: flex;
            flex-direction: column;
        }

        /* Screws in the corners */
        .faceplate::before, .faceplate::after {
            content: ""; position: absolute; width: 20px; height: 20px;
            border-radius: 50%;
            background: linear-gradient(135deg, #eee 0%, #aaa 100%);
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.4), 0 1px 1px rgba(255,255,255,0.8);
            border: 1px solid #777;
        }
        .faceplate::before { top: 20px; left: 20px; }
        .faceplate::after { top: 20px; right: 20px; }
        
        /* Pseudo elements for bottom screws */
        .screw-bl { position: absolute; bottom: 20px; left: 20px; width: 20px; height: 20px; border-radius: 50%; background: linear-gradient(135deg, #eee 0%, #aaa 100%); box-shadow: inset 0 2px 4px rgba(0,0,0,0.4), 0 1px 1px rgba(255,255,255,0.8); border: 1px solid #777; }
        .screw-br { position: absolute; bottom: 20px; right: 20px; width: 20px; height: 20px; border-radius: 50%; background: linear-gradient(135deg, #eee 0%, #aaa 100%); box-shadow: inset 0 2px 4px rgba(0,0,0,0.4), 0 1px 1px rgba(255,255,255,0.8); border: 1px solid #777; }

        /* Cross inside screws */
        .faceplate::before, .faceplate::after, .screw-bl, .screw-br {
            background-image: 
                linear-gradient(45deg, transparent 45%, #666 45%, #666 55%, transparent 55%),
                linear-gradient(-45deg, transparent 45%, #666 45%, #666 55%, transparent 55%),
                linear-gradient(135deg, #eee 0%, #aaa 100%);
        }

        /* Top Hardware Nav */
        nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 2rem;
            border-bottom: 2px solid #d0cece;
            box-shadow: 0 2px 0 rgba(255,255,255,0.6); /* Bevel under line */
            margin-bottom: 3rem;
            position: relative;
        }

        /* Speaker Grills at the top right */
        .grill {
            position: absolute; right: 100px; top: 10px;
            width: 120px; height: 30px;
            background: repeating-linear-gradient(
                90deg,
                transparent,
                transparent 6px,
                #222 6px,
                #222 10px
            );
            border-radius: 4px;
            opacity: 0.8;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.5), 0 1px 1px rgba(255,255,255,0.5);
        }

        /* Volume Knob (Decorative) */
        .knob {
            position: absolute; right: 240px; top: -5px;
            width: 45px; height: 45px;
            border-radius: 50%;
            background: radial-gradient(circle at 30% 30%, #fff, #bbb);
            box-shadow: 0 5px 10px rgba(0,0,0,0.3), inset 0 -2px 4px rgba(0,0,0,0.2);
            border: 1px solid #999;
        }
        .knob::after {
            content: ""; position: absolute; top: 5px; left: 20px; width: 4px; height: 15px;
            background: #444; border-radius: 2px; box-shadow: inset 0 1px 2px rgba(0,0,0,0.5);
        }

        .logo-group { display: flex; flex-direction: row; align-items: baseline; gap: 10px; }
        .logo { font-family: 'Inter', sans-serif; font-weight: 900; font-size: 1.8rem; color: #333; text-decoration: none; text-transform: uppercase; letter-spacing: -0.02em; text-shadow: 0 1px 1px rgba(255,255,255,0.8); }
        .tagline { font-family: 'Inter', sans-serif; font-size: 0.85rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }

        .nav-right { display: flex; align-items: center; gap: 1rem; position: relative; z-index: 10; }
        .nav-icon { 
            width: 40px; height: 40px; border: 1px solid #aaa; 
            display: flex; align-items: center; justify-content: center; cursor: pointer;
            background: linear-gradient(to bottom, #fff, #e0e0e0); border-radius: 50%; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.1), inset 0 2px 2px #fff;
            transition: all 0.1s; color: var(--text-main); font-size: 1.2rem;
        }
        .nav-icon:active { transform: translateY(2px); box-shadow: 0 1px 2px rgba(0,0,0,0.1), inset 0 2px 4px rgba(0,0,0,0.2); background: #d0d0d0; }

        /* Hardware "Screen" Area (Hero) */
        .hero { margin-bottom: 3rem; display: flex; align-items: center; justify-content: space-between; gap: 2rem; background: rgba(0,0,0,0.02); padding: 1.5rem; border-radius: 16px; border: 1px solid rgba(0,0,0,0.05); box-shadow: inset 0 2px 8px rgba(0,0,0,0.05); }
        .hero h1 { display: none; } /* Hide old title to match layout */

        .search-area { position: relative; flex: 1; }
        
        /* Heavily recessed slot for input */
        .search-container {
            background: #d8d8d8;
            border-radius: 12px;
            display: flex; align-items: center;
            padding: 8px 12px;
            box-shadow: inset 0 4px 8px rgba(0,0,0,0.4), inset 0 1px 2px rgba(0,0,0,0.6), 0 1px 1px rgba(255,255,255,0.9);
            border: 1px solid #999;
            gap: 10px;
        }
        
        .search-container input {
            flex: 1; border: 1px solid #aaa; padding: 1rem 1.5rem; font-size: 1.1rem; outline: none;
            font-family: 'Inter', sans-serif; background: #fafafa; color: #333;
            border-radius: 8px;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.1), 0 1px 0 rgba(255,255,255,0.8);
        }
        
        /* 3D Distill Button */
        .distill-container { display: flex; align-items: center; gap: 1rem; }
        
        /* Orange Indicator Light */
        .indicator { width: 12px; height: 12px; border-radius: 50%; background: radial-gradient(circle, #ffcc00, #ff6600); box-shadow: 0 0 10px #ff6600, inset 0 1px 2px rgba(255,255,255,0.8), inset 0 -1px 2px rgba(0,0,0,0.5); border: 1px solid #883300; }
        
        .distill-btn {
            background: linear-gradient(to bottom, var(--btn-orange-top), var(--btn-orange-bottom));
            color: #000; text-shadow: 0 1px 1px rgba(255,255,255,0.4);
            border: none; border-radius: 12px;
            padding: 1rem 2.5rem; font-family: 'Inter', sans-serif; font-weight: 900;
            text-transform: uppercase; font-size: 1.1rem; cursor: pointer; letter-spacing: 0.05em;
            box-shadow: 
                0 8px 0 var(--btn-orange-side), 
                0 12px 10px rgba(0,0,0,0.3), 
                inset 0 2px 2px rgba(255,255,255,0.5),
                inset 0 -2px 4px rgba(0,0,0,0.2);
            transition: all 0.1s;
            position: relative;
            top: -4px; /* Push up by default */
        }
        .distill-btn:active { 
            top: 4px; 
            box-shadow: 
                0 0px 0 var(--btn-orange-side), 
                0 2px 5px rgba(0,0,0,0.3), 
                inset 0 2px 4px rgba(0,0,0,0.4); 
            background: linear-gradient(to bottom, var(--btn-orange-bottom), #cc4400);
        }

        /* Controls Strip / Toggle Area */
        .controls-strip {
            display: flex; flex-direction: column; align-items: center; gap: 0.5rem;
            font-family: 'Inter', sans-serif; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
            color: var(--text-dark); text-shadow: 0 1px 0 rgba(255,255,255,0.8);
        }
        .toggle-unit { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; }
        
        /* 3D Hardware Toggle */
        .switch { position: relative; display: inline-block; width: 60px; height: 30px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: #cac8c2; border-radius: 20px; transition: .3s;
            box-shadow: inset 0 4px 8px rgba(0,0,0,0.4), inset 0 1px 2px rgba(0,0,0,0.5), 0 1px 1px rgba(255,255,255,0.9);
            border: 1px solid #888;
        }
        .slider:before {
            position: absolute; content: ""; height: 22px; width: 22px; left: 4px; bottom: 3px;
            background: linear-gradient(to bottom, #fff, #ccc); border-radius: 50%; transition: .3s;
            box-shadow: 0 4px 4px rgba(0,0,0,0.3), inset 0 2px 2px #fff;
            border: 1px solid #999;
        }
        input:checked + .slider { background-color: #a8a6a0; }
        input:checked + .slider:before { transform: translateX(30px); }

        /* Status Text */
        .status-text { font-family: 'Inter', sans-serif; font-size: 0.7rem; font-weight: 700; color: #555; text-transform: uppercase; margin-top: 5px; }

        /* Main Grid */
        .results-container-main { display: grid; grid-template-columns: 1fr 1fr; gap: 2.5rem; margin-top: 2rem; }

        /* 3D Mounded Cards */
        .glass-card {
            background: var(--plastic-base);
            border: 1px solid #fff;
            border-radius: 20px;
            padding: 2rem;
            position: relative;
            box-shadow: 
                0 10px 20px rgba(0,0,0,0.15), 
                inset 0 4px 6px rgba(255,255,255,1), 
                inset 0 -4px 6px rgba(0,0,0,0.05);
            margin-bottom: 2rem;
        }

        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; border-bottom: 2px solid #d0cece; padding-bottom: 1rem; box-shadow: 0 2px 0 rgba(255,255,255,0.6); }
        .card-header h2 { font-family: 'Inter', sans-serif; font-size: 1rem; font-weight: 800; text-transform: uppercase; color: var(--text-dark); text-shadow: 0 1px 0 rgba(255,255,255,0.8); }

        /* Collapsibles styled as inset panels */
        details { background: #fdfdfc; border: 1px solid #ccc; border-radius: 12px; margin-bottom: 1.5rem; overflow: hidden; box-shadow: inset 0 2px 4px rgba(0,0,0,0.05), 0 2px 0 rgba(255,255,255,0.8); }
        summary {
            padding: 1.25rem 1.5rem; cursor: pointer; list-style: none; outline: none;
            display: flex; justify-content: space-between; align-items: center;
            font-family: 'Inter', sans-serif; font-weight: 800; font-size: 1rem; color: var(--text-dark);
            background: linear-gradient(to bottom, #fff, #f0f0f0);
            border-bottom: 1px solid #ddd;
        }
        summary::after { content: "▼"; font-size: 0.8rem; color: var(--text-muted); }
        details[open] summary { background: #e8e8e8; box-shadow: inset 0 2px 4px rgba(0,0,0,0.1); }
        details[open] summary::after { content: "▲"; }
        .collapsible-content { padding: 1.5rem; background: #fafafa; }

        /* Key Insights */
        .insights-list { list-style: none; }
        .insight-item { 
            display: flex; gap: 1rem; margin-bottom: 1rem; padding: 1.25rem; 
            border: 1px solid #e0e0e0; background: #fff; border-radius: 12px;
            font-size: 0.95rem; line-height: 1.6; color: var(--text-dark);
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        .insight-number { 
            font-family: 'Space Mono', monospace; font-size: 0.75rem; font-weight: 700;
            color: #fff; background: var(--btn-orange-top); width: 28px; height: 28px;
            display: flex; align-items: center; justify-content: center; flex-shrink: 0; border-radius: 50%;
            box-shadow: inset 0 2px 2px rgba(255,255,255,0.4), 0 2px 2px rgba(0,0,0,0.1);
        }

        /* Recessed Screen Elements */
        #mindmap { background: var(--screen-bg); border-radius: 12px; border: 2px solid #000; box-shadow: inset 0 4px 10px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.8); color: var(--accent-cyan); overflow: hidden; }

        /* Tags */
        .timestamp-badge { background: var(--accent-cyan); color: #000; padding: 4px 8px; border-radius: 12px; font-weight: 800; font-size: 0.7rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section-label { font-weight: 800; color: var(--btn-orange-top); text-transform: uppercase; font-size: 0.8rem; }

        /* Pro Video Thumb - Screen look */
        #videoProfileThumb { border: 2px solid #000; border-radius: 12px; overflow: hidden; background: #000; position: relative; box-shadow: inset 0 4px 10px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.8); }
        #videoProfileThumb::after {
            content: "REC ●"; position: absolute; top: 12px; left: 12px; color: #FF0033; font-weight: 700; font-size: 0.75rem; font-family: 'Space Mono', monospace;
            background: rgba(0,0,0,0.8); padding: 4px 8px; border-radius: 4px; letter-spacing: 0.1em;
            box-shadow: 0 0 5px #ff0000;
        }

        /* Utilities */
        .hidden { display: none !important; }

        /* Export Menu Fix */
        .export-group { position: relative; }
        .export-menu {
            position: absolute; right: 0; top: 100%; margin-top: 0.5rem;
            background: #fff; border: 1px solid #ccc; border-radius: 12px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.1); padding: 0.5rem;
            display: none; flex-direction: column; gap: 4px; width: 200px; z-index: 100;
        }
        .export-menu.active { display: flex; }
        .export-item { 
            font-family: 'Inter', sans-serif; font-size: 0.85rem; font-weight: 600;
            padding: 10px 12px; border-radius: 8px; cursor: pointer; color: var(--text-dark);
        }
        .export-item:hover { background: #f0f0f0; color: var(--accent-blue); }

        footer { 
            margin-top: auto; padding: 2rem 0 0 0; border-top: 2px solid #d0cece;
            display: flex; justify-content: space-between; font-family: 'Inter', sans-serif; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; text-shadow: 0 1px 0 rgba(255,255,255,0.8); box-shadow: inset 0 2px 0 rgba(255,255,255,0.6);
        }
    </style>
"""

# Regex replacement for the style block
content = re.sub(r'<style>.*?</style>', new_css, content, flags=re.DOTALL)

# Adjust HTML layout to match the image:
html_adjust = """
    <div class="screw-bl"></div>
    <div class="screw-br"></div>
    <div class="grill"></div>
    <div class="knob"></div>
    <nav>
"""
if '<div class="screw-bl"></div>' not in content:
    content = content.replace('<nav>', html_adjust)

hero_old = """    <div class="hero">
        <h1>Intelligence Distillation Unit</h1>
        <div class="search-area">
            <div class="search-container">
                <input type="text" id="videoUrl" placeholder="PASTE YOUTUBE SOURCE URL [MM:SS]...">
                <button onclick="summarizeVideo()" id="summarizeBtn" class="distill-btn">Distill</button>
            </div>
            <div class="controls-strip">
                <div class="toggle-unit">
                    <label class="switch">
                        <input type="checkbox" id="includeScreenshots" checked>
                        <span class="slider"></span>
                    </label>
                    <span>Visual Capture [Shots]</span>
                </div>
                <div style="margin-left: auto; color: var(--accent-orange);">READY // AC_LINE: 220V</div>
            </div>
        </div>
        <p style="margin-top: 1rem; font-size: 0.8rem; color: var(--text-muted); text-align: center;">
            Don't want to spend credits? <a href="javascript:void(0)" onclick="loadDemo()" style="color: var(--accent-primary); text-decoration: none; font-weight: 600;">Try our Demo →</a>
        </p>
    </div>"""

# Ensure we remove the old hero correctly if it's there, but be robust using regex just in case
hero_new = """    <div class="hero">
        <div class="search-area">
            <div class="search-container">
                <input type="text" id="videoUrl" placeholder="Search YouTube URL, Video Title...">
                <div class="nav-icon" style="border-radius:4px; height: 36px; width: 36px; margin-right: 4px; box-shadow: none;">🔍</div>
            </div>
        </div>
        
        <div class="distill-container">
            <div class="indicator"></div>
            <button onclick="summarizeVideo()" id="summarizeBtn" class="distill-btn">Distill</button>
            <div class="indicator"></div>
        </div>

        <div class="controls-strip">
            <div class="toggle-unit">
                <label class="switch">
                    <input type="checkbox" id="includeScreenshots" checked>
                    <span class="slider"></span>
                </label>
            </div>
            <span class="status-text">AI Depth<br>Quick / Detailed</span>
        </div>
    </div>
    <div style="text-align: center; margin-bottom: 2rem; font-family: 'Inter', sans-serif; font-size: 0.8rem; font-weight: 700; color: #6b6b6b; text-transform: uppercase;">
        Don't want to spend credits? <a href="javascript:void(0)" onclick="loadDemo()" style="color: #ff4c29; text-decoration: none; font-weight: 900;">Try our Demo →</a>
    </div>"""

content = re.sub(r'<div class="hero">.*?</div>\s*<p.*?Try our Demo.*?</p>\s*</div>', hero_new, content, flags=re.DOTALL)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated index.html to extreme skeuomorphic style.")
