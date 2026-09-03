# Copilot App Factory

**AI-powered static site generator using GitHub Copilot SDK**

**Live demo: [wirier.com](https://wirier.com)**

---

## What is it?

Copilot App Factory lets anyone create a custom static website just by describing what they want. Type a description, and the AI builds a complete, production-ready site in seconds.

```
"A portfolio site for a photographer with a dark theme and image gallery"
     ↓
[ GitHub Copilot SDK ]
     ↓
Complete website with HTML, CSS, and responsive design
```

## How It Works

The site builder uses a two-pass approach:

1. **Generate** - Creates the complete site from your description using modern 2026 design patterns
2. **Polish** - Reviews and enhances images, animations, and mobile responsiveness

```
┌─────────────────────────────────────────────────────────┐
│                    Build Pipeline                        │
│                                                          │
│   Description ──▶ Generate ──▶ Polish ──▶ Deploy        │
│                      │           │           │           │
│                      ▼           ▼           ▼           │
│                   index.html  Enhanced   Live URL        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## GitHub Copilot SDK Integration

The core of this project uses the **GitHub Copilot SDK** (`pip install github-copilot-sdk`) to generate code:

```python
# backend/site_builder.py - Core Copilot SDK integration

from copilot import CopilotClient
from copilot.generated.session_events import SessionEventType

# Initialize the SDK client
client = CopilotClient({
    "cli_path": COPILOT_CLI_PATH,
    "cwd": output_dir,
    "auto_start": True,
})
await client.start()

# Create session with model selection
session = await client.create_session({
    "model": "gpt-5-mini",  # Free tier, performant
    "on_permission_request": auto_approve,
})

# Handle events
def on_event(event):
    if event.type == SessionEventType.ASSISTANT_MESSAGE:
        # Parse and save code from output
        save_code_blocks(event.data.content, output_dir)

session.on(on_event)

# Send prompt
await session.send({
    "prompt": build_prompt(description),
    "allowTools": True,
})
```

## Design Philosophy

Sites are generated following 2026 design best practices:

- **Bold typography** - Distinctive Google Fonts pairings (not generic Inter/Roboto)
- **Real images** - Picsum for authentic photography (with seeded URLs for consistency)
- **Atmospheric backgrounds** - Gradients, textures, and depth
- **Meaningful motion** - Staggered entrance animations, smooth hover states
- **Mobile-first** - Responsive layouts, thumb-friendly interactions
- **Accessibility** - Proper heading hierarchy, contrast ratios, alt text

## Features

- **Natural language input** - Describe your site in plain English
- **Real-time progress** - Watch as your site is built
- **Production-ready output** - Valid HTML5, responsive CSS, SEO meta tags
- **Instant deploy** - Sites go live immediately at wirier.com/apps/[id]

## Tech Stack

- **Backend**: Python, FastAPI, GitHub Copilot SDK
- **Frontend**: React, Vite
- **AI**: GitHub Copilot SDK with GPT-5 mini (free tier)

## The Name

**Wirier** - more wiry, more intricate, more interconnected. Like the neural networks that power AI, or the complex web of code that builds your site.

## Competition Entry

This project was built for the **GitHub Copilot SDK Weekend Contest** (January 2026).

The goal: demonstrate the power of the Copilot SDK by building something that builds other things - an AI that creates websites from natural language descriptions.

## License

MIT

---

Powered by [GitHub Copilot SDK](https://github.com/github/copilot-sdk)
