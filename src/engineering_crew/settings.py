"""Configuration for the engineering crew.

The models are the interesting setting. The lead designs the system and is the
only agent whose mistakes cascade — a bad design wastes three downstream agents'
work — so it gets the strong model. The three implementers follow a design that
already exists and check their own work by running it, so a cheaper model is
enough. That split is most of the cost difference between a $3 run and a $0.40
one, and it is a decision worth being able to justify.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent

#: Where the agents write and run the code they produce. Wiped at the start of
#: every run, so a crew never inherits a previous run's half-finished files.
SANDBOX_DIR = Path(os.getenv("CREW_SANDBOX", PROJECT_ROOT / "sandbox")).resolve()

#: The Docker image the sandbox executes in. Pinned: agents write code against
#: whatever Python they are told is present, so drifting the runtime silently
#: changes what "the tests passed" means.
DOCKER_IMAGE = os.getenv("CREW_DOCKER_IMAGE", "ghcr.io/astral-sh/uv:python3.13-bookworm-slim")
SANDBOX_PYTHON = os.getenv("CREW_SANDBOX_PYTHON", "3.13")

#: A script that has not finished in this long is killed. The test engineer loops
#: until its tests pass, and an accidental infinite loop in generated code would
#: otherwise hold the whole crew.
EXECUTION_TIMEOUT_S = int(os.getenv("CREW_EXECUTION_TIMEOUT_S", "300"))

#: The remote MCP server the lead queries for current library APIs, so the design
#: is written against the real Gradio 6 signatures rather than the model's
#: recollection of Gradio 3.
CONTEXT7_MCP_URL = os.getenv("CONTEXT7_MCP_URL", "https://mcp.context7.com/mcp")
USE_CONTEXT7 = os.getenv("USE_CONTEXT7", "true").strip().lower() == "true"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
