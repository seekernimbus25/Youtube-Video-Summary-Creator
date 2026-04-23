import re

with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# 1. Replace Fonts
old_fonts = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Lexend:wght@400;500;600;700&display=swap" rel="stylesheet">'
new_fonts = '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
html = html.replace(old_fonts, new_fonts)

# 2. Replace Main Style Block
new_css = """    <style>
        :root {
            --bg-base: #e0e5ec;
            --bg-card: #e0e5ec;
            --bg-recessed: #d1d9e6;
            --text-main: #2d3748;
            --text-muted: #718096;
            --accent-primary: #ff5722;
            --accent-secondary: #00bcd4;
            --accent-success: #10b981;
            --accent-warning: #f59e0b;
            --accent-error: #ef4444;
            --shadow-light: #ffffff;
            --shadow-dark: #a3b1c6;
            --border-radius: 16px;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Manrope', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            line-height: 1.6;
            overflow-x: hidden;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* Nav */
        nav {
            height: 70px;
            padding: 0 4rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 1000;
            background: var(--bg-base);
            box-shadow: 0 4px 10px rgba(163, 177, 198, 0.3);
        }

        .logo-group { display: flex; flex-direction: column; line-height: 1.1; }
        .logo { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.4rem; color: var(--text-main); text-decoration: none; letter-spacing: -0.02em; }
        .tagline { font-size: 0.65rem; color: var(--accent-primary); font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; }

        .nav-right { display: flex; align-items: center; gap: 1.5rem; }
        .nav-icon { color: var(--text-muted); font-size: 1.2rem; cursor: pointer; transition: color 0.2s; }
        .nav-icon:hover { color: var(--accent-primary); }

        /* Hero */
        .hero { padding: 4rem 1rem 3rem; text-align: center; max-width: 1200px; margin: 0 auto; }
        .hero h1 {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 3.5rem;
            margin-bottom: 2rem;
            color: var(--text-main);
            font-weight: 700;
            letter-spacing: -0.03em;
            text-shadow: 2px 2px 4px var(--shadow-light), -2px -2px 4px var(--shadow-dark);
        }

        /* Search */
        .search-container {
            max-width: 700px;
            margin: 0 auto;
            background: var(--bg-recessed);
            border-radius: 50px;
            padding: 0.5rem;
            display: flex;
            align-items: center;
            gap: 1rem;
            box-shadow: inset 6px 6px 12px var(--shadow-dark), inset -6px -6px 12px var(--shadow-light);
        }

        .search-container input {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-main);
            padding: 0.75rem 1.5rem;
            outline: none;
            font-size: 1.1rem;
            font-family: 'Manrope', sans-serif;
        }

        /* Switch */
        .toggle-group { display: flex; align-items: center; gap: 0.75rem; color: var(--text-muted); font-size: 0.75rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; }
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: var(--bg-recessed);
            box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
            transition: .4s; border-radius: 24px;
        }
        .slider:before {
            position: absolute; content: ""; height: 16px; width: 16px; left: 4px; bottom: 4px;
            background-color: var(--text-muted);
            box-shadow: 2px 2px 4px rgba(0,0,0,0.2);
            transition: .4s; border-radius: 50%;
        }
        input:checked + .slider:before { transform: translateX(20px); background-color: var(--accent-primary); }

        /* Btn Summarize */
        .btn-summarize {
            background: var(--bg-base);
            color: var(--accent-primary);
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 40px;
            font-weight: 800;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1rem;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            box-shadow: 6px 6px 12px var(--shadow-dark), -6px -6px 12px var(--shadow-light);
            transition: all 0.2s ease;
        }
        .btn-summarize:active {
            box-shadow: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light);
            transform: scale(0.98);
        }

        /* Main Layout */
        .results-container-main { max-width: 1400px; margin: 0 auto; padding: 2rem; display: flex; flex-direction: column; gap: 2rem; }
        .top-row { display: grid; grid-template-columns: 1fr 400px; gap: 2rem; align-items: stretch; }

        /* Skeuomorphic Cards */
        .glass-card {
            background: var(--bg-card);
            border-radius: var(--border-radius);
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            box-shadow: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light);
            transition: transform 0.3s ease;
        }
        
        .card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
        .card-header h2 { font-family: 'Space Grotesk', sans-serif; font-size: 1.2rem; font-weight: 700; color: var(--text-main); }

        /* Collapsibles */
        details {
            background: var(--bg-card);
            border-radius: var(--border-radius);
            margin-bottom: 1.5rem;
            box-shadow: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light);
            overflow: hidden;
            transition: all 0.3s;
        }
        summary {
            list-style: none; padding: 1.5rem 2rem; cursor: pointer;
            font-family: 'Space Grotesk', sans-serif; font-size: 1.25rem; font-weight: 700;
            display: flex; align-items: center; justify-content: space-between;
            color: var(--text-main); outline: none; user-select: none;
        }
        summary::-webkit-details-marker { display: none; }
        summary::after {
            content: "+"; font-size: 1.5rem; color: var(--accent-primary);
            width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
            border-radius: 50%; box-shadow: 3px 3px 6px var(--shadow-dark), -3px -3px 6px var(--shadow-light);
            transition: transform 0.3s, box-shadow 0.2s;
        }
        details[open] summary::after { content: "−"; transform: rotate(90deg); box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light); }
        .collapsible-content { padding: 0 2rem 2rem; border-top: 1px solid rgba(0,0,0,0.05); }

        /* Insights */
        .insights-list { list-style: none; display: flex; flex-direction: column; gap: 1.25rem; }
        .insight-item { display: flex; gap: 1rem; font-size: 0.95rem; color: var(--text-main); line-height: 1.5; }
        .insight-number {
            color: var(--accent-secondary); font-weight: 800; font-family: 'Space Grotesk', sans-serif; font-size: 0.9rem;
            width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
            border-radius: 50%; background: var(--bg-base);
            box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light);
            flex-shrink: 0;
        }

        /* Concept Cards */
        .concept-card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; margin-top: 1rem; }
        .concept-premium-card {
            background: var(--bg-card);
            border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem;
            box-shadow: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light);
            border: 2px solid transparent;
            transition: all 0.3s;
        }
        .concept-premium-card:hover { border-color: var(--accent-secondary); }
        .concept-title { font-family: 'Space Grotesk', sans-serif; font-weight: 700; color: var(--text-main); font-size: 1.1rem; display: flex; align-items: center; gap: 0.75rem; }
        .concept-title::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--accent-primary); box-shadow: 0 0 8px var(--accent-primary); }
        .concept-label { color: var(--text-muted); font-weight: 800; text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.05em; margin-bottom: 0.4rem; display: block; }
        .concept-text { color: var(--text-main); line-height: 1.5; }

        /* Legacy Grid */
        .results-grid { max-width: 1400px; margin: 0 auto; padding: 2rem; display: grid; grid-template-columns: 1fr 450px; gap: 2rem; }
        .left-col, .right-col { display: flex; flex-direction: column; gap: 2rem; }

        .pill-tag {
            background: var(--bg-base); color: var(--accent-primary);
            padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em;
            box-shadow: 2px 2px 5px var(--shadow-dark), -2px -2px 5px var(--shadow-light);
        }

        .interactive-tag { background: var(--accent-secondary); color: #fff; font-size: 0.6rem; padding: 3px 8px; border-radius: 4px; font-weight: 800; text-transform: uppercase; box-shadow: 2px 2px 4px var(--shadow-dark); }

        /* Concepts Dots */
        .concepts-container { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 1rem; }
        .concept-dot-tag {
            display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem;
            background: var(--bg-base); border-radius: 30px; font-size: 0.85rem; color: var(--text-main); font-weight: 600;
            box-shadow: 3px 3px 6px var(--shadow-dark), -3px -3px 6px var(--shadow-light);
            cursor: pointer; transition: 0.2s;
        }
        .concept-dot-tag:active { box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light); }
        .dot { width: 10px; height: 10px; border-radius: 50%; box-shadow: inset 1px 1px 2px rgba(0,0,0,0.3); }

        /* Summary Sidebar */
        .summary-card {
            padding: 1.5rem; margin-bottom: 1.5rem;
            background: var(--bg-recessed); border-radius: 12px;
            box-shadow: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light);
            border-left: 4px solid var(--accent-primary);
        }
        .timestamp-badge {
            background: var(--bg-base); padding: 3px 8px; border-radius: 6px; font-family: 'Space Grotesk', monospace; font-size: 0.75rem; color: var(--accent-primary); font-weight: 700;
            box-shadow: 2px 2px 4px var(--shadow-dark), -2px -2px 4px var(--shadow-light);
        }
        .summary-card h3 { font-size: 1.2rem; margin-bottom: 0.75rem; color: var(--text-main); font-family: 'Space Grotesk', sans-serif; }
        .summary-card p { font-size: 0.95rem; color: var(--text-main); margin-bottom: 1rem; }
        .section-label { font-size: 0.65rem; font-weight: 800; color: var(--text-muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.5rem; display: block; }
        
        .step-list { list-style: none; margin: 1rem 0; }
        .step-list li { display: flex; align-items: flex-start; gap: 0.75rem; font-size: 0.9rem; margin-bottom: 0.6rem; color: var(--text-main); }
        .check-circle {
            width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            background: var(--bg-base); color: var(--accent-success); font-size: 0.6rem; font-weight: 900;
            box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light);
            flex-shrink: 0; margin-top: 2px;
        }

        .tradeoff {
            font-size: 0.85rem; color: var(--accent-error); display: flex; align-items: center; gap: 0.5rem; margin-top: 1.25rem; padding: 0.75rem;
            background: var(--bg-base); border-radius: 8px; font-weight: 600;
            box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
        }

        /* Comparisons */
        .comparisons-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; max-width: 1400px; margin: 0 auto 2rem; padding: 0 2rem; }
        .comparison-card { padding: 2rem; text-align: left; }
        .icon-box {
            width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 1.5rem; font-size: 1.4rem;
            background: var(--bg-base); box-shadow: 4px 4px 8px var(--shadow-dark), -4px -4px 8px var(--shadow-light);
        }

        /* Recommendations */
        .recom-container { display: grid; grid-template-columns: 1fr 500px; gap: 2rem; max-width: 1400px; margin: 2rem auto 4rem; padding: 0 2rem; }
        .recom-list { display: flex; flex-direction: column; gap: 1rem; }
        .recom-item { display: flex; align-items: center; gap: 1.5rem; padding: 1.5rem; }
        .icon-circle {
            width: 50px; height: 50px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
            background: var(--bg-base); box-shadow: 4px 4px 8px var(--shadow-dark), -4px -4px 8px var(--shadow-light); color: var(--accent-secondary); font-size: 1.2rem;
        }

        .synthesis-card { background: var(--bg-base); border: 2px solid var(--accent-primary); }

        /* Progress Shimmer */
        .shimmer {
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.8), transparent);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
        }
        @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }

        /* Animation */
        .hidden { display: none !important; }
        
        .scroll-reveal { opacity: 0; transform: translateY(30px); transition: opacity 0.8s cubic-bezier(0.16, 1, 0.3, 1), transform 0.8s cubic-bezier(0.16, 1, 0.3, 1); }
        .scroll-reveal.in-view { opacity: 1; transform: translateY(0); }
        
        /* Instead of triggering on load, keep reveal for non-scroll items */
        .reveal { animation: reveal 0.8s cubic-bezier(0.16, 1, 0.3, 1) both; }
        @keyframes reveal { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

        footer { margin-top: auto; padding: 1rem 4rem; border-top: 1px solid var(--shadow-light); display: flex; justify-content: space-between; align-items: center; background: var(--bg-base); }
        .footer-links { display: flex; gap: 2rem; font-size: 0.85rem; font-weight: 700; }
        .footer-links a { color: var(--text-muted); text-decoration: none; transition: color 0.2s; }
        .footer-links a:hover { color: var(--accent-primary); }

        .screenshot-box-mini { margin: 1.5rem 0; border-radius: 12px; overflow: hidden; box-shadow: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light); border: 4px solid var(--bg-base); }
        .screenshot-box-mini img { width: 100%; display: block; }
        .screenshot-caption-mini { padding: 0.75rem; background: var(--bg-recessed); font-size: 0.75rem; color: var(--text-main); font-weight: 700; text-align: center; }

        #mindmap svg { overflow: visible; }
        .mindmap-controls { position: absolute; bottom: 1rem; right: 1rem; display: flex; gap: 0.75rem; z-index: 10; }
        .map-btn {
            width: 40px; height: 40px; background: var(--bg-base); border-radius: 8px; color: var(--accent-primary); display: flex; align-items: center; justify-content: center; cursor: pointer; border: none; font-weight: bold;
            box-shadow: 4px 4px 8px var(--shadow-dark), -4px -4px 8px var(--shadow-light); transition: 0.1s; font-size: 1.2rem;
        }
        .map-btn:active { box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light); transform: scale(0.95); }
        #mindmap:fullscreen { background: var(--bg-base); padding: 2rem; display: flex; align-items: center; justify-content: center; }

        .export-group { position: relative; display: inline-block; }
        .export-menu {
            position: absolute; bottom: 100%; right: 0; background: var(--bg-base); border-radius: 12px; padding: 0.5rem; display: none; flex-direction: column; gap: 0.25rem; width: 160px;
            box-shadow: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light); margin-bottom: 1rem; z-index: 2000; border: none;
        }
        .export-menu.active { display: flex; }
        .export-menu.top { bottom: auto; top: 100%; margin-bottom: 0; margin-top: 1rem; }
        .export-item { padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 700; transition: 0.2s; color: var(--text-main); }
        .export-item:hover { background: var(--bg-recessed); color: var(--accent-primary); box-shadow: inset 2px 2px 4px var(--shadow-dark), inset -2px -2px 4px var(--shadow-light); }

        #videoProfileThumb { border: 4px solid var(--bg-base); box-shadow: 6px 6px 12px var(--shadow-dark), -6px -6px 12px var(--shadow-light); border-radius: 16px; overflow: hidden; }
        #progressCard { background: var(--bg-card); border-radius: 16px; box-shadow: inset 6px 6px 12px var(--shadow-dark), inset -6px -6px 12px var(--shadow-light); }
        
        .section-breakdown-item { margin-bottom: 1.5rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--shadow-dark); }
        .section-breakdown-item:last-child { border-bottom: none; }

        @media print {
            :root { color-scheme: light !important; }
            html, body { background: #fff !important; color: #000 !important; padding: 0 !important; font-size: 10pt; box-shadow: none !important; }
            * { 
                background-color: transparent !important; 
                background-image: none !important; 
                color: #000 !important; 
                text-shadow: none !important; 
                box-shadow: none !important; 
                backdrop-filter: none !important; 
                border-color: #eee !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            .reveal, .scroll-reveal { opacity: 1 !important; transform: none !important; visibility: visible !important; }
            .nav-icon, .hero, .search-container, .mindmap-controls, footer, .map-btn, .interactive-tag, nav, .progress-card, .btn-summarize, #mindmap, .card-header a, .export-group, .export-menu, #mindmap-card { display: none !important; }
            
            #resultsContainer, .results-container-main, .top-row, .glass-card, #videoProfileCard { 
                display: block !important; border: none !important; padding: 0 !important; margin: 0 !important; width: 100% !important;
            }
            
            #videoProfileThumb { float: left; width: 140px !important; margin-right: 1rem !important; margin-bottom: 0.5rem !important; }
            #videoProfileTitle { font-size: 1.4rem !important; font-weight: bold; margin-bottom: 0.2rem !important;}
            #videoProfileMeta { font-size: 0.85rem; margin-bottom: 0.5rem !important; }
            #videoProfilePitch { font-size: 0.95rem !important; margin-bottom: 1rem !important;}
            
            .card-header h2 { font-size: 1.2rem !important; border-bottom: 1px solid #000 !important; margin: 0.5rem 0 0.2rem 0 !important; clear: both; width: 100%; padding-bottom: 0.2rem !important;}
            .insight-item { margin-bottom: 0.1rem !important; padding-bottom: 0 !important; line-height: 1.2 !important; }
            .insight-number { font-weight: bold; margin-right: 0.3rem !important; }
            
            details { margin-bottom: 0.5rem !important; padding: 0 !important; }
            summary { font-size: 1.1rem !important; font-weight: bold; border-bottom: 1px solid #ddd !important; margin-bottom: 0.2rem !important; padding-bottom: 0.2rem !important; }
            
            .insights-list { margin: 0 !important; padding: 0 !important; list-style: none !important; }
            .section-breakdown-item { page-break-inside: avoid; border: none !important; border-top: 1px solid #eee !important; padding: 0.3rem 0 !important; margin: 0.3rem 0 !important; }
            
            table { border: 1px solid #000; border-collapse: collapse; width: 100%; margin-bottom: 0.5rem !important;}
            th, td { border: 1px solid #000; padding: 2px 4px !important; }
            
            h1, h2, h3, h4 { color: #000 !important; margin: 0.2rem 0 !important; }
            p, span, li, td, th { color: #000 !important; margin: 0.1rem 0 !important; }
            .step-list { margin: 0 !important; padding: 0 0 0 1rem !important; }
            .step-list li { margin: 0 !important; padding: 0 !important; list-style: circle !important; }
        }
    </style>"""

html = re.sub(r'<style>.*?</style>', new_css, html, flags=re.DOTALL, count=1)

# 3. Inject scroll observer logic before </body> (safely using rsplit)
observer_script = """
    <script>
        // Intersection Observer for scroll animations
        document.addEventListener('DOMContentLoaded', () => {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('in-view');
                    }
                });
            }, { threshold: 0.05, rootMargin: '0px 0px -30px 0px' });

            const observeElements = () => {
                document.querySelectorAll('.glass-card, details, .comparison-card, .recom-item').forEach(el => {
                    if (!el.classList.contains('scroll-reveal')) {
                        el.classList.add('scroll-reveal');
                        observer.observe(el);
                    }
                });
            };
            
            observeElements();
            
            const mutationObserver = new MutationObserver((mutations) => {
                let shouldObserve = false;
                mutations.forEach(mutation => {
                    if (mutation.addedNodes.length > 0) shouldObserve = true;
                });
                if (shouldObserve) observeElements();
            });
            
            const resultsContainer = document.getElementById('resultsContainer');
            if (resultsContainer) {
                mutationObserver.observe(resultsContainer, { childList: true, subtree: true });
            }
        });
    </script>
</body>"""

if 'IntersectionObserver' not in html:
    # Use rsplit to only replace the LAST </body> tag (the real one)
    parts = html.rsplit('</body>', 1)
    if len(parts) == 2:
        html = observer_script.join(parts)

# 4. Surgical replacements for colors/borders
html = html.replace('linear-gradient(90deg, #7c3aed, #a855f7)', 'var(--accent-primary)')
html = html.replace('background: rgba(5, 6, 15, 0.8);', 'background: var(--bg-base);')
html = html.replace('border: 1px solid var(--glass-border);', 'border: none;')

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Updated successfully.")
