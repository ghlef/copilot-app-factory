"""
Site Builder - AI-powered static site generation using GitHub Copilot SDK

Generates production-ready static websites from natural language descriptions.
Uses a two-pass approach: main generation + optional polish pass.
"""

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
from datetime import datetime, timezone

from copilot import CopilotClient
from copilot.generated.session_events import SessionEventType


# =============================================================================
# SDK Monkey-Patch: Enable full permissions for agentic file operations
# =============================================================================

def _patch_copilot_sdk():
    """Patch CopilotClient to include full permission flags for agentic operations."""
    import copilot.client as sdk_client_module

    _original_start_cli = sdk_client_module.CopilotClient._start_cli_server

    async def _patched_start_cli(self):
        """Patched _start_cli_server that adds permission flags to CLI args."""
        import subprocess
        original_popen = subprocess.Popen

        def patched_popen(args, *popen_args, **popen_kwargs):
            if args and isinstance(args, list) and "--server" in args:
                extra_flags = [
                    "--allow-all-tools",
                    "--allow-all-paths",
                    "--allow-all-urls",
                ]
                for flag in extra_flags:
                    if flag not in args:
                        args = list(args) + [flag]
            return original_popen(args, *popen_args, **popen_kwargs)

        subprocess.Popen = patched_popen
        try:
            result = await _original_start_cli(self)
        finally:
            subprocess.Popen = original_popen
        return result

    sdk_client_module.CopilotClient._start_cli_server = _patched_start_cli


_patch_copilot_sdk()


# Cloud persistence - optional
try:
    from cloud_persistence import save_job_to_cloud, load_job_from_cloud, is_cloud_enabled
    _cloud_enabled = is_cloud_enabled()
except ImportError:
    _cloud_enabled = False
    def save_job_to_cloud(job): return False
    def load_job_from_cloud(job_id): return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BuildStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BuildJob:
    job_id: str
    description: str
    status: BuildStatus = BuildStatus.PENDING
    progress: int = 0
    message: str = ""
    output_dir: Optional[Path] = None
    site_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    logs: list[str] = field(default_factory=list)

    def add_log(self, message: str):
        timestamp = utc_now().isoformat()
        self.logs.append(f"[{timestamp}] {message}")
        self.message = message
        self.updated_at = utc_now()


# Job storage
_jobs: dict[str, BuildJob] = {}


def get_job(job_id: str) -> Optional[BuildJob]:
    if job_id in _jobs:
        return _jobs[job_id]
    job = load_job_from_cloud(job_id)
    if job:
        _jobs[job_id] = job
    return job


def save_job(job: BuildJob):
    _jobs[job.job_id] = job
    save_job_to_cloud(job)


def create_job(job_id: str, description: str) -> BuildJob:
    job = BuildJob(job_id=job_id, description=description)
    job.add_log(f"Job {job_id} created, waiting for build to start...")
    save_job(job)
    return job


# =============================================================================
# GitHub Copilot SDK Integration
# =============================================================================

COPILOT_CLI_PATH = os.getenv("COPILOT_CLI_PATH", "copilot")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# Use GPT-5 mini - FREE (0x multiplier) and performant
# Free: gpt-5-mini (0x), raptor-mini (0x), gpt-4.1 (0x)
# Cheap: grok-code-fast-1 (0.25x), claude-haiku-4.5 (0.33x), gemini-3-flash (0.33x)
# Premium: claude-sonnet-4.5 (1x), claude-opus-4.5 (1x), claude-opus-4.1 (10x)
COPILOT_MODEL = os.getenv("COPILOT_MODEL", "gpt-5-mini")


async def create_copilot_client(cwd: str) -> CopilotClient:
    client = CopilotClient({
        "cli_path": COPILOT_CLI_PATH,
        "cwd": cwd,
        "auto_start": True,
        "auto_restart": True,
    })
    await client.start()
    return client


# =============================================================================
# Prompt Engineering - 2026 Design Standards
# =============================================================================

def build_main_prompt(description: str) -> str:
    """
    Build the main generation prompt.

    Based on 2026 design trends:
    - Bold typography with distinctive font choices
    - Strategic whitespace and clear hierarchy
    - Real images from Picsum (never emojis as placeholders)
    - Vibrant gradients and atmospheric backgrounds
    - Mobile-first, fast-loading
    - Clear single CTA, minimal navigation
    - Kinetic typography and meaningful micro-animations

    Avoids AI red flags:
    - No generic fonts (Inter, Roboto, Arial)
    - No purple-gradient-on-white cliches
    - No buzzword-heavy copy
    - No identical paragraph lengths
    - No emojis as image placeholders
    """
    return f"""Create a complete, production-ready HTML landing page for: {description}

Output the complete code in a fenced code block:

```html:index.html
[your complete HTML here]
```

## 2026 Design Requirements

**Typography** (pick ONE distinctive pairing from Google Fonts):
- Display: Playfair Display, Cormorant Garamond, Fraunces, Libre Baskerville, DM Serif Display, or Instrument Serif
- Body: Source Sans 3, Karla, Work Sans, Manrope, or Outfit
- Use large, bold headlines (clamp(2.5rem, 5vw, 4.5rem))
- Headlines should sound natural, not clever or marketing-speak

**Color & Theme** (commit to ONE aesthetic):
- Dark moody: Deep charcoal (#1a1a1a to #2d2d2d) with warm amber (#e8934c) or copper accents
- Light editorial: Off-white (#faf9f6) with deep navy (#1a2332) and gold details
- Warm organic: Cream (#f5f0e8) with terracotta (#c4673d) and forest (#2d4a3e)
- Bold modern: Near-black with electric accents (cyan #00d9ff, magenta #ff006e, or lime #b5ff00)
Pick one. Execute it fully. No timid, evenly-distributed palettes.

**Layout**:
- Hero section with ONE clear message and ONE call-to-action
- Strategic negative space (don't fill every pixel)
- Asymmetric grid or intentional overlap for visual interest
- Mobile-first: thumb-friendly buttons, readable on small screens

**Images** (CRITICAL - use REAL photos, never emojis):
- Use Picsum with seed for themed images: https://picsum.photos/seed/coffee/800/600 (change "coffee" to relevant keyword)
- For variety, increment the seed: seed/coffee1, seed/coffee2, seed/coffee3
- Example hero: https://picsum.photos/seed/hero/1200/800
- Example feature images: https://picsum.photos/seed/feature1/600/400, seed/feature2/600/400
- Every image needs descriptive alt text
- Use object-fit: cover for consistent sizing
- NEVER use source.unsplash.com (deprecated and broken!)

**Motion & Polish**:
- Page load: fade-in with staggered delays (animation-delay: 0.1s, 0.2s, etc.)
- Hover states: subtle transforms, color shifts, or underline reveals
- Keep it minimal and meaningful - one orchestrated entrance beats scattered effects

**Accessibility**:
- Proper heading hierarchy (h1 → h2 → h3)
- Color contrast ratio 4.5:1 minimum
- Focus states for keyboard navigation
- All images have alt text

**What to AVOID** (AI red flags):
- Generic fonts: Inter, Roboto, Arial, system-ui
- Purple gradient on white background
- Emojis as image/icon placeholders
- Buzzwords without specifics ("revolutionary", "cutting-edge", "seamless")
- Cookie-cutter layouts with no personality
- Walls of text with identical paragraph lengths

## Structure
Include in one HTML file with inline <style>:
- Navigation (minimal - logo + 2-3 links max)
- Hero section (headline, subhead, CTA button)
- 2-3 content sections showcasing value
- Footer with contact/social

Output the complete, working HTML file now."""


def build_polish_prompt(description: str) -> str:
    """Build a polish pass prompt to refine the generated site."""
    return f"""Review and enhance the index.html file for: {description}

Check and fix if needed:

1. **Images**: Ensure ALL images use Picsum URLs (NOT source.unsplash.com which is broken!)
   - Example: <img src="https://picsum.photos/seed/relevant/800/600" alt="descriptive text">
   - For variety use different seeds: seed/image1, seed/image2, seed/image3

2. **Typography**: Verify Google Fonts are loaded and applied correctly

3. **Mobile**: Test that layout works on small screens (use media queries if missing)

4. **Animations**: Add subtle entrance animations if missing:
   - @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
   - Apply with animation: fadeIn 0.6s ease-out forwards;

5. **Polish**: Smooth hover transitions (transition: all 0.3s ease)

Output the enhanced file:

```html:index.html
[complete enhanced HTML]
```

When done, output: <promise>COMPLETE</promise>"""


def parse_and_save_code_blocks(output: str, output_dir: Path) -> list[str]:
    """Parse fenced code blocks from model output and save to files."""
    import re

    saved_files = []

    # Pattern: ```language:filename\ncontent\n```
    pattern = r'```(\w+):([^\n`]+)\n(.*?)```'
    matches = re.findall(pattern, output, re.DOTALL)

    for _, filename, content in matches:
        filename = filename.strip()
        if '..' in filename or filename.startswith('/'):
            continue
        file_path = output_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content.strip())
        saved_files.append(filename)

    # Fallback: plain ```html blocks
    if "index.html" not in saved_files:
        html_pattern = r'```html\n(.*?)```'
        html_matches = re.findall(html_pattern, output, re.DOTALL)
        if html_matches:
            (output_dir / "index.html").write_text(html_matches[-1].strip())
            saved_files.append("index.html")

    return saved_files


async def run_copilot_session(
    prompt: str,
    output_dir: Path,
    job: BuildJob,
    timeout: int = 300
) -> tuple[bool, str]:
    """Run a single Copilot SDK session with the given prompt."""
    client = None
    try:
        client = await create_copilot_client(str(output_dir))

        def auto_approve(request, _context):
            kind = getattr(request, 'kind', None) or (request.get('kind') if isinstance(request, dict) else 'unknown')
            job.add_log(f"  Auto-approving: {kind}")
            return {"kind": "approved", "rules": []}

        session = await client.create_session({
            "model": COPILOT_MODEL,
            "available_tools": ["write", "edit", "shell", "view", "glob", "grep"],
            "on_permission_request": auto_approve,
        })

        output_messages = []
        completed = False
        error_message = None

        def on_event(event):
            nonlocal completed, error_message
            try:
                event_type = event.type
                # Log significant events only (skip verbose internal events)
                event_name = event_type.value if hasattr(event_type, 'value') else str(event_type)
                if event_name not in ('assistant_message', 'tool_execution_end'):
                    job.add_log(f"  {event_name}")

                if event_type == SessionEventType.ASSISTANT_MESSAGE:
                    content = event.data.content or ''
                    output_messages.append(content)
                    if '<promise>COMPLETE</promise>' in str(content):
                        completed = True
                elif event_type == SessionEventType.TOOL_EXECUTION_START:
                    tool_name = event.data.tool_name or 'unknown'
                    job.add_log(f"  Tool: {tool_name}")
                elif event_type == SessionEventType.SESSION_ERROR:
                    error_message = event.data.message or 'Unknown error'
                elif event_type in (SessionEventType.SESSION_IDLE, SessionEventType.ASSISTANT_TURN_END):
                    completed = True
            except Exception as e:
                job.add_log(f"Event error: {e}")

        session.on(on_event)
        await session.send({"prompt": prompt, "allowTools": True})

        start_time = asyncio.get_event_loop().time()
        while not completed and not error_message:
            await asyncio.sleep(0.5)
            if asyncio.get_event_loop().time() - start_time > timeout:
                error_message = "Timeout"
                break

        await session.destroy()
        await client.stop()

        output = '\n'.join(output_messages)
        saved_files = parse_and_save_code_blocks(output, output_dir)
        if saved_files:
            job.add_log(f"  Saved: {', '.join(saved_files)}")

        success = completed and not error_message
        return success, output

    except Exception as e:
        return False, str(e)
    finally:
        if client:
            try:
                await client.stop()
            except Exception:
                pass


# =============================================================================
# Main Build Function
# =============================================================================

async def build_site(
    job_id: str,
    description: str,
    deploy_func: Optional[Callable] = None,
    on_progress: Optional[Callable] = None,
    enable_polish_pass: bool = True
) -> BuildJob:
    """
    Build a static site from a description.

    Two-pass approach:
    1. Main generation - creates the complete site
    2. Polish pass (optional) - refines images, animations, mobile
    """
    job = get_job(job_id)
    if not job:
        job = BuildJob(job_id=job_id, description=description)
        _jobs[job_id] = job

    job.status = BuildStatus.RUNNING
    job.add_log(f"Starting build for job {job_id}")
    save_job(job)

    output_dir = Path(tempfile.mkdtemp(prefix=f"copilot-build-{job_id}-"))
    job.output_dir = output_dir
    job.add_log(f"Created output directory: {output_dir}")

    def update_progress(percent: int, message: str):
        job.progress = percent
        job.add_log(message)
        save_job(job)
        if on_progress:
            on_progress(percent, message)

    try:
        # Pass 1: Main generation
        update_progress(10, "Generating site...")
        main_prompt = build_main_prompt(description)

        # Save prompt for debugging
        (output_dir / ".prompt.md").write_text(main_prompt)

        success, output = await run_copilot_session(main_prompt, output_dir, job)

        if not success:
            job.add_log(f"Main generation failed: {output[:200]}")

        # Pass 2: Polish (optional)
        if enable_polish_pass and (output_dir / "index.html").exists():
            update_progress(60, "Polishing site...")
            polish_prompt = build_polish_prompt(description)
            await run_copilot_session(polish_prompt, output_dir, job, timeout=120)

        # Ensure we have index.html
        index_file = output_dir / "index.html"
        if not index_file.exists():
            update_progress(85, "Creating fallback...")
            index_file.write_text(generate_fallback_html(description, job_id))

        update_progress(90, "Deploying...")

        # Deploy
        if deploy_func:
            try:
                import inspect
                if inspect.iscoroutinefunction(deploy_func):
                    site_url = await deploy_func(output_dir, job_id)
                else:
                    site_url = await asyncio.to_thread(deploy_func, output_dir, job_id)
                job.site_url = site_url
                update_progress(100, f"Deployed to {site_url}")
            except Exception as e:
                job.add_log(f"Deploy failed: {e}")
                job.error = str(e)
        else:
            update_progress(100, "Build complete")

        job.status = BuildStatus.COMPLETED
        job.add_log("Build completed successfully")
        save_job(job)

    except Exception as e:
        job.status = BuildStatus.FAILED
        job.error = str(e)
        job.add_log(f"Build failed: {e}")
        save_job(job)

    finally:
        if os.getenv("CLEANUP_TEMP", "true").lower() == "true":
            try:
                if job.status == BuildStatus.FAILED:
                    shutil.rmtree(output_dir, ignore_errors=True)
            except Exception:
                pass

    return job


# =============================================================================
# Fallback Template
# =============================================================================

def generate_fallback_html(description: str, job_id: str) -> str:
    """Generate a fallback HTML file if generation fails."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Site {job_id}</title>
    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Source Sans 3', sans-serif;
            background: #1a1a1a;
            color: #f5f5f5;
            line-height: 1.6;
        }}
        .hero {{
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            padding: 2rem;
            background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        }}
        h1 {{
            font-family: 'DM Serif Display', serif;
            font-size: clamp(2.5rem, 5vw, 4rem);
            margin-bottom: 1rem;
            color: #e8934c;
        }}
        p {{
            max-width: 600px;
            margin-bottom: 2rem;
            opacity: 0.9;
        }}
        .cta {{
            display: inline-block;
            padding: 1rem 2.5rem;
            background: #e8934c;
            color: #1a1a1a;
            text-decoration: none;
            font-weight: 600;
            border-radius: 4px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .cta:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(232, 147, 76, 0.3);
        }}
    </style>
</head>
<body>
    <section class="hero">
        <h1>Welcome</h1>
        <p>{description}</p>
        <a href="#" class="cta">Get Started</a>
    </section>
</body>
</html>'''
