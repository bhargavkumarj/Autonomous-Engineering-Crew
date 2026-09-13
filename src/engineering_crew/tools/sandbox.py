"""The sandbox: how agents write code, and how they run it without touching your machine.

Four tools. Three are trivial file operations. The fourth, ``run_sandbox_python``,
is the one that matters: it executes agent-authored code inside an ephemeral
Docker container with only the sandbox directory mounted. The agents never get a
shell on the host, and nothing they write survives the container.

That boundary is what makes the whole project defensible. An agent that writes
code is unremarkable; an agent that *runs* code is a security question, and the
answer here is a process boundary rather than a promise in a prompt.
"""

from __future__ import annotations

import shutil
import subprocess

from crewai.tools import tool

from engineering_crew.settings import DOCKER_IMAGE, EXECUTION_TIMEOUT_S, SANDBOX_DIR, SANDBOX_PYTHON

SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


def reset_sandbox() -> None:
    """Wipe the sandbox and re-initialise it as a fresh uv project with gradio.

    Called at the start of every run. Without it a crew inherits the previous
    run's files and the test engineer starts "fixing" code nobody asked for.
    """
    if SANDBOX_DIR.exists():
        shutil.rmtree(SANDBOX_DIR)
    SANDBOX_DIR.mkdir(parents=True)
    subprocess.run(["uv", "init", "--bare", "--python", SANDBOX_PYTHON], cwd=SANDBOX_DIR, check=True)
    subprocess.run(["uv", "add", "gradio"], cwd=SANDBOX_DIR, check=True)


def docker_available() -> bool:
    """Whether Docker is installed and its daemon is actually running."""
    if not shutil.which("docker"):
        return False
    probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    return probe.returncode == 0


@tool("List Sandbox Files")
def list_sandbox_files() -> str:
    """
    List the filenames currently in the sandbox directory.

    Returns:
        A newline-separated list of filenames, or a message if the
        sandbox is empty.
    """
    names = sorted(p.name for p in SANDBOX_DIR.iterdir())
    return "\n".join(names) if names else "The sandbox is empty."


@tool("Read Sandbox File")
def read_sandbox_file(filename: str) -> str:
    """
    Read and return the text contents of a file in the sandbox directory.

    Args:
        filename: The name of the file to read (e.g. "solution.py").
    Returns:
        The file's contents, or a message if the file does not exist.
    """
    path = SANDBOX_DIR / filename
    if not path.is_file():
        return f"No such file in the sandbox: {filename}"
    return path.read_text()


@tool("Write Sandbox File")
def write_sandbox_file(filename: str, content: str) -> str:
    """
    Write text to a file in the sandbox directory, replacing any existing
    file with the same name.

    Args:
        filename: The name of the file to write (e.g. "solution.py").
        content: The text content to write.
    Returns:
        A confirmation message.
    """
    path = SANDBOX_DIR / filename
    path.write_text(content)
    return f"Wrote {len(content)} characters to {filename}."


@tool("Run Sandbox Python File")
def run_sandbox_python(filename: str) -> str:
    """
    Execute a Python file from the sandbox directory inside an ephemeral
    Docker container, with the sandbox mounted as the working directory,
    using `uv run` to run the code in the uv project.

    Returns the exit code, stdout, and stderr, clearly labeled. Note that
    Python's unittest module prints test results — including failures and
    tracebacks — to stderr by default, not stdout, so stderr is just as
    important as stdout for understanding what happened.

    Args:
        filename: The name of the Python file to run (e.g. "solution.py").
    Returns:
        A labeled block containing the exit code, stdout, and stderr.
    """
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{SANDBOX_DIR}:/workspace",
                "-w", "/workspace",
                DOCKER_IMAGE,
                "uv", "run", filename,
            ],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_S,
        )
        return (
            f"Exit code: {result.returncode}\n\n"
            f"--- stdout ---\n{result.stdout or '(empty)'}\n\n"
            f"--- stderr ---\n{result.stderr or '(empty)'}"
        )
    except subprocess.TimeoutExpired as expired:
        stdout = _decode(expired.stdout)
        stderr = _decode(expired.stderr)
        return (
            f"The script timed out after {EXECUTION_TIMEOUT_S} seconds.\n\n"
            f"--- stdout so far ---\n{stdout or '(empty)'}\n\n"
            f"--- stderr so far ---\n{stderr or '(empty)'}"
        )


def _decode(stream: bytes | str | None) -> str:
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream or ""


sandbox_tools = [list_sandbox_files, read_sandbox_file, write_sandbox_file, run_sandbox_python]


def _never_cache(*_args, **_kwargs) -> bool:
    return False


# CrewAI caches tool results by default, which is right for a pure lookup and
# catastrophic here: the sandbox mutates between calls (files appear, change and
# get executed), so a cached "the tests failed" would be replayed to an agent
# that has since fixed the code, and the test engineer would loop forever fixing
# an error that no longer exists. Opt every sandbox tool out.
for _sandbox_tool in sandbox_tools:
    _sandbox_tool.cache_function = _never_cache
