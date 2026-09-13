# Architecture

## 1. A team, not a pipeline of prompts

Four agents, each with a role, a goal and a backstory, working a sequential
process with explicit context dependencies:

```
design_task      agent: engineering_lead     output_file: sandbox/design.md
    │                                        tools: Context7 MCP only
    │
    ├──► code_task        agent: backend_engineer    context: [design]
    │                     tools: sandbox
    │         │
    ├──► frontend_task    agent: frontend_engineer   context: [code, design]
    │                     tools: sandbox + Context7 MCP
    │
    └──► test_task        agent: test_engineer       context: [code, design]
                          tools: sandbox
                          output_file: sandbox/test_summary.md
```

`context` is the mechanism that makes this a team rather than four independent
prompts: CrewAI feeds the named tasks' outputs into the dependent task's context.
The frontend engineer sees the design *and* the backend code; the test engineer
sees both too, but deliberately not the original requirement — it works from what
was actually built.

They also share a filesystem. Every agent with sandbox tools reads and writes the
same directory, so the backend engineer's `backend.py` is literally the file the
test engineer imports. Context passing carries the intent; the sandbox carries
the artifact.

---

## 2. The sandbox is the whole security story

```python
subprocess.run([
    "docker", "run", "--rm",
    "-v", f"{SANDBOX_DIR}:/workspace",
    "-w", "/workspace",
    DOCKER_IMAGE,
    "uv", "run", filename,
], capture_output=True, text=True, timeout=EXECUTION_TIMEOUT_S)
```

Every property in that command is load-bearing:

* **`--rm`** — the container is destroyed after every single execution. State
  cannot accumulate; an agent cannot install something in run 3 and rely on it in
  run 7.
* **`-v SANDBOX_DIR:/workspace`** — the *only* mount. The rest of the host
  filesystem does not exist from inside.
* **a pinned image** — agents write code against whatever runtime they are told
  is present. Letting the image drift silently changes what "the tests passed"
  means.
* **`timeout=300`** — the test engineer loops until its tests pass, and an
  accidental `while True` in generated code would otherwise hold the whole crew
  forever.

The three file tools are scoped to `SANDBOX_DIR` by construction — they build
paths as `SANDBOX_DIR / filename`, so there is no path an agent can supply that
reaches outside.

### What this is not

It is not a hardened sandbox. There is no `--network none`, no `--read-only`, no
user namespace remapping, no memory or CPU limit. A determined adversarial
payload could reach the network from inside the container. This is isolation from
*the agents' mistakes*, which is the actual threat model here — an agent writing
`shutil.rmtree("/")` because it misread the design. Defending against an
adversarial code generator is a different and harder problem, and the honest
first steps are `--network none`, `--read-only` with a tmpfs, and `--memory`.

---

## 3. Why the lead has no sandbox

The design task says, in capitals, "Do not actually write any code. Function or
method signatures only." The lead is also the one agent constructed without
sandbox tools.

That is not belt-and-braces, it is the actual enforcement. An agent holding a
file-writing tool will write files, because tool use is trained behaviour and the
prompt is a suggestion competing with it. Removing the capability makes the
instruction unnecessary; the instruction remains only as an explanation of *why*.

The same principle appears in the tool assignment more broadly:

| Agent | Sandbox | Context7 | Why |
|---|---|---|---|
| Lead | ✗ | ✓ | Must not write code; must know current APIs |
| Backend | ✓ | ✗ | stdlib only, so a docs server is turns spent on nothing |
| Frontend | ✓ | ✓ | Writes Gradio, where the API actually moved |
| Test | ✓ | ✗ | stdlib `unittest` only |

Tool surface *is* prompt. Every tool an agent holds is an option it will consider
on every turn.

---

## 4. Documentation over recollection

Gradio 6 changed APIs that Gradio 3 and 4 established, and a model's recollection
of Gradio is mostly the older ones. An agent writing a UI from memory produces
code that looks right and does not run.

Two things address that, and the second is the interesting one:

1. The lead and the frontend engineer both hold the **Context7 MCP server**, a
   remote HTTPS MCP server that serves current library documentation.
2. The lead's goal instructs it to *"include explicit Gradio 6 API guidance for
   the frontend engineer (correct kwargs, method signatures, where things have
   changed from earlier versions), since they do not have access to Context7."*

That second line is context engineering expressed as team structure. One agent
does the lookup at design time and bakes the answer into the artifact everyone
downstream reads. It is cheaper than every agent querying, and it puts the
knowledge in front of the model *before* it starts writing rather than requiring
it to realise it needs to ask.

### The MCP patch

CrewAI 1.14.4 sanitises HTTPS MCP tool names on discovery — hyphens become
underscores — and then sends the **sanitised** name back to the server on
invocation. Any server tool with a hyphen in its name is therefore permanently
unreachable, which includes Context7's `resolve-library-id`.

`crewai_mcp_patch.py` replaces `MCPToolResolver._resolve_external` with a version
that keeps the original name on the wrapper (`_original_tool_name`) so `call_tool`
reaches the real tool. It is imported for its side effect, before any agent
resolves MCP tools.

A monkey-patch is a liability, so it is scoped to one method, its docstring names
the version and the exact symptom, and it says "re-verify on crewai upgrade".
That is the difference between a workaround and a landmine.

---

## 5. Tool caching, and why it is off

CrewAI caches tool results by default. For a lookup tool that is correct and
saves money. For these tools it is catastrophic:

```python
for _sandbox_tool in sandbox_tools:
    _sandbox_tool.cache_function = _never_cache
```

The sandbox mutates between calls. Files appear, change, and get executed. A
cached `run_sandbox_python("test_backend.py") -> "Exit code: 1 ... AssertionError"`
would be replayed to an agent that has since fixed the code — so the test
engineer patches, reruns, sees the identical stale failure, patches again, and
loops until it gives up or runs out of budget.

The general rule this is an instance of: **cache pure tools, never stateful
ones.** A tool whose output depends on side effects performed by earlier calls is
not cacheable, and an agent framework cannot know that for you.

---

## 6. Sequential, not hierarchical

CrewAI offers a hierarchical process where a manager agent delegates and decides
ordering. This crew is sequential.

The dependencies here are genuinely linear — you cannot test code that has not
been written, and you cannot write a UI for a backend that does not exist. A
manager would add a model call per step and a chance of getting the order wrong,
in exchange for flexibility this pipeline does not need.

Hierarchical earns its cost when the work is *decomposable in more than one way*
— when the manager has a real decision to make about who does what. Choosing
sequential here is choosing determinism where determinism is free.

---

## 7. The self-correcting loop

The test engineer is the only agent with an oracle it does not control:

```
write test_backend.py
    ↓
run_sandbox_python("test_backend.py")   → exit code + stdout + stderr
    ↓
read the traceback
    ↓
patch backend.py   (not the test — the task says to fix the code)
    ↓
rerun ────────────────┐
    ↑                 │
    └── until green ──┘
```

Two details make it work.

**Its task says "Fix any errors in the backend code so that the unit tests pass.
Keep working until all unit tests pass."** Without that, an agent writes tests,
sees a failure, and reports it. The instruction is what converts a test writer
into a repair loop.

**`run_sandbox_python`'s docstring explains that `unittest` writes failures to
stderr, not stdout.** That sentence is in the docstring because the docstring is
the tool's prompt — it is what the model reads when deciding how to interpret the
result. An agent that only reads stdout sees an empty string and concludes
everything passed.

The task also says "Avoid making any changes that might break the gradio app in
app.py", which is the crude version of a regression constraint. There is nothing
enforcing it.

---

## 8. Failure modes

Worth knowing, because they are what an interviewer will probe:

| Failure | Cause | Mitigation today |
|---|---|---|
| Frontend uses a stale Gradio API | knowledge cutoff | Context7 + design-time guidance; the `_validate.py` script catches construction errors |
| Test engineer fixes the *test* instead of the code | ambiguous instruction | the task says to fix the backend; nothing enforces it |
| Backend imports a third-party package | sandbox has only gradio | stated in the agent's goal; the run then fails loudly |
| A generated script hangs | infinite loop in generated code | 300s container timeout |
| `.launch()` in a validation script | blocks until timeout | explicitly forbidden in the task description |
| Design underspecifies an interface | hard problem | the strong model on the lead; no other mitigation |

The last one is the real limit. Everything downstream is recoverable because
someone runs the code; a bad design fails silently and expensively.

---

## 9. What I would change

* **Harden the container.** `--network none`, `--read-only` with a tmpfs, a
  memory cap and a non-root user. Currently the isolation defends against
  mistakes, not adversaries.
* **A structured handoff between design and implementation.** The design is
  markdown, so the backend engineer interprets prose. Emitting a Pydantic-typed
  interface spec would make "did you implement the design" checkable.
* **A budget.** There is no turn cap beyond CrewAI's defaults. The test
  engineer's loop is bounded only by its own judgement.
* **Keep the runs.** Each run wipes the sandbox, so there is no history and no
  way to compare a prompt change across runs. Archiving each run under a
  timestamp would make the crew's output measurable.
* **A second reviewer agent.** The only quality signal is "the tests pass",
  which the same crew wrote. A reviewer that never saw the implementation, given
  only the requirement and the code, would catch the class of bug where the tests
  and the code are wrong in the same direction.
