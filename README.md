# Autonomous Engineering Crew

Hand it a software requirement in plain English. Four role-based agents design
the system, implement it, build a UI for it, and write and run unit tests —
fixing their own defects until the tests pass. Every line of code they write is
executed inside an ephemeral Docker container, so nothing they produce touches
your machine.

```
   "A lending library system. Members borrow books. Fines are 20c a day.
    Prevent borrowing more than 5 at once..."
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  ENGINEERING LEAD                          model: the strong one          │
│  writes a design: modules, classes, signatures — deliberately NO code     │
│  tools: Context7 MCP (live library docs)   NO sandbox, on purpose         │
└──────────┬────────────────────────────────────────────────────────────────┘
           │ design
     ┌─────┴──────────────────┬──────────────────────────┐
     ▼                        ▼                          ▼
┌─────────────┐        ┌──────────────┐          ┌────────────────┐
│  BACKEND    │        │  FRONTEND    │          │  TEST          │
│  stdlib     │───────►│  Gradio UI   │          │  writes tests  │
│  only       │  code  │  + Context7  │          │  RUNS them     │
│             │        │  + validates │          │  fixes backend │
│             │        │  it builds   │          │  reruns ↺      │
└──────┬──────┘        └──────┬───────┘          └───────┬────────┘
       │                      │                          │
       └──────────────────────┴──────────────────────────┘
                              │ every read / write / RUN
                              ▼
              ┌───────────────────────────────────────┐
              │  SANDBOX  ./sandbox (a uv project)    │
              │  execution: docker run --rm           │
              │    -v sandbox:/workspace              │
              │  ephemeral · no host access · 300s cap│
              └───────────────────────────────────────┘
                              │
                              ▼
      design.md · backend.py · app.py · test_backend.py · test_summary.md
```

---

## Why this project is interesting

**The agents run the code they write.** That is the line between "an LLM
produced some Python" and "an agent built working software" — and it is also a
security question. The answer here is a process boundary, not a promise: every
execution is `docker run --rm` with only the sandbox directory mounted. The
agents never get a shell on the host, and nothing survives the container.

**The test engineer has a real oracle.** It writes tests, runs them, reads the
exit code and the traceback, patches the *backend*, and reruns until green. That
is a self-correcting loop grounded in an actual verdict from a process the agent
does not control — categorically stronger than a model grading its own output.
`run_sandbox_python` even explains in its docstring that `unittest` writes
failures to **stderr**, because an agent that only reads stdout concludes
everything passed.

**Capability is scoped, not requested.** The lead's task says "function
signatures only, do not write any code" — and the lead is also the one agent with
no sandbox tools. An agent with a file-writing tool will write files whatever the
prompt says. Withholding the capability is the enforcement; the prompt is just
the explanation.

**It solves the knowledge-cutoff problem concretely.** The lead queries the
Context7 MCP server for current library APIs before designing, and its goal
instructs it to fold explicit Gradio 6 guidance into the design *for the frontend
engineer, who does not have Context7*. One agent does the lookup; the design
carries the answer downstream. That is context engineering as a team structure.

**It works around a real framework bug.** CrewAI 1.14.4 sanitises HTTPS MCP tool
names on discovery and then sends the sanitised name back to the server, so any
tool with a hyphen in its name — like Context7's `resolve-library-id` — is
unreachable. `crewai_mcp_patch.py` restores the original name on the wrapper.
It is documented, scoped, and flagged for re-verification on upgrade.

---

## Quick start

```bash
cp .env.example .env    # add your OPENAI_API_KEY
```

Start Docker Desktop, then:

```bash
uv sync && uv run engineering-crew doctor
```

```bash
uv run engineering-crew run
```

Watch four agents work. When it finishes, everything is in `sandbox/`:

```bash
cd sandbox && uv run app.py
```

### Other requirements

```bash
uv run engineering-crew show
uv run engineering-crew run --requirement library
uv run engineering-crew run --requirement scheduler
uv run engineering-crew run --file my_spec.txt
```

Three are built in — a trading account system, a lending library, and a task
scheduler with dependency cycles and critical-path analysis. They are deliberately
similar in shape: a self-contained domain with **hard, checkable rules**. That is
the property that makes a requirement work here. "Make it user-friendly" produces
a crew that argues with itself; "prevent borrowing more than 5 books" produces a
test that either passes or does not.

### Requirements

* Python 3.12–3.13
* **Docker**, running. Without it the agents write code perfectly happily and
  every attempt to run it fails, so the test engineer spends its whole budget
  fixing code that was never broken. `doctor` checks the daemon, and `run`
  refuses to start without it unless you pass `--allow-no-docker`.
* `uv`, to initialise the sandbox project
* `OPENAI_API_KEY`

The first run pulls the container image, so give it a minute.

---

## Layout

```
src/engineering_crew/
├── settings.py            models, sandbox path, image, timeouts
├── cli.py                 run / doctor / show
├── crew.py                the four agents and four tasks, wired
├── requirements.py        three built-in requirements
├── crewai_mcp_patch.py    documented workaround for a CrewAI 1.14.4 MCP bug
├── config/
│   ├── agents.yaml          roles, goals, backstories, per-agent models
│   └── tasks.yaml           descriptions, expected outputs, context dependencies
└── tools/
    └── sandbox.py         read / write / list / RUN-in-Docker
sandbox/                   wiped and recreated at the start of every run
```

The YAML split is CrewAI's central idea and it earns its keep: the parts that get
edited constantly and read like specifications live in a file a non-engineer can
review, and `crew.py` contains only wiring.

---

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required.** |
| `CREW_SANDBOX` | `./sandbox` | Where agents write and run code |
| `CREW_DOCKER_IMAGE` | `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` | The execution container. Pinned on purpose. |
| `CREW_EXECUTION_TIMEOUT_S` | `300` | A generated script that hangs is killed |
| `USE_CONTEXT7` | `true` | Live library docs for the lead and frontend engineer |

Models are set per agent in `config/agents.yaml`. The lead gets the strong model
because a bad design wastes three downstream agents' work; the implementers
follow a design that already exists and verify by running it, so a cheaper model
suffices. That split is most of the difference between a $3 run and a $0.40 one.

---

## Tests

```bash
uv run --extra dev pytest
```

25 tests, no API key, no Docker, a quarter of a second. They validate the
declarative configuration the way CrewAI will read it — every task names an agent
that exists, every `context` entry points at an earlier task, every `{placeholder}`
is supplied at kickoff, no `output_file` escapes the sandbox. Each of those fails
at *runtime* otherwise: minutes into a paid run, after several agents have already
worked.

---

## Cost and limits

A full run is four agents with substantial context, and the test engineer may
iterate several times. Budget a few dollars on the default models. There is no
turn cap beyond CrewAI's own defaults — the honest bound is the requirement:
scope creep in the input turns into iterations in the output.

Success is not guaranteed. This produces working software most of the time on
requirements of this size, and the failure modes are worth knowing: a design that
underspecifies an interface, a frontend engineer using a Gradio API that moved,
or a test engineer that fixes the tests instead of the code.

---

## Provenance

Built from the week 3 (CrewAI) capstone of Ed Donner's *Master AI Agentic
Engineering* course, restructured into a standalone application: a `src` layout
with a proper package, centralised settings for the sandbox and container, a CLI
with an environment doctor and a requirement catalogue, a pre-flight Docker check
so a missing daemon fails fast instead of silently, `cwd` anchoring so output
files land in the sandbox regardless of where you invoke from, and a test suite
over the YAML configuration. See `ARCHITECTURE.md`.
