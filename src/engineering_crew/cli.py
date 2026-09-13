"""Entry point for the engineering crew.

    engineering-crew run                    build the default requirement
    engineering-crew run --requirement library
    engineering-crew run --file spec.txt    your own requirement, from a file
    engineering-crew doctor                 check Docker, uv and the API key
    engineering-crew show                   list the built-in requirements

The MCP patch is imported before the crew, because it monkey-patches CrewAI's
tool resolver and has to be in place before any agent resolves its MCP tools.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import warnings
from pathlib import Path

# pysbd (a CrewAI dependency) emits a SyntaxWarning on import under 3.12+.
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from engineering_crew import (  # noqa: E402
    crewai_mcp_patch,  # noqa: F401  imported for its side effect: applies the MCP patch
    settings,
)
from engineering_crew import requirements as requirement_catalogue  # noqa: E402
from engineering_crew.tools.sandbox import docker_available, reset_sandbox  # noqa: E402


def _doctor() -> int:
    """Check everything the crew needs before it starts spending money.

    Docker is the one that matters. Without it the agents write code perfectly
    happily and every attempt to run it fails, so the test engineer spends its
    whole budget "fixing" code that was never broken.
    """
    print("Engineering crew environment check\n")

    ok = bool(settings.OPENAI_API_KEY)
    print("  [ ok ] OPENAI_API_KEY" if ok else "  [FAIL] OPENAI_API_KEY is missing — nothing will run")

    uv = shutil.which("uv")
    print(f"  [ ok ] uv ({uv})" if uv else "  [FAIL] uv not found — the sandbox cannot be initialised")
    ok = ok and bool(uv)

    if docker_available():
        print("  [ ok ] docker (daemon responding)")
    else:
        ok = False
        print("  [FAIL] docker is not available — agents can write code but never run it")

    print(f"\n  sandbox    {settings.SANDBOX_DIR}")
    print(f"  image      {settings.DOCKER_IMAGE}")
    print(f"  timeout    {settings.EXECUTION_TIMEOUT_S}s per script")
    print(f"  docs MCP   {settings.CONTEXT7_MCP_URL if settings.USE_CONTEXT7 else 'disabled'}")
    print("\nReady." if ok else "\nNot ready: fix the FAIL lines above.")
    return 0 if ok else 1


def _show() -> int:
    print("Built-in requirements:\n")
    for name, text in requirement_catalogue.CATALOGUE.items():
        marker = "  (default)" if name == requirement_catalogue.DEFAULT else ""
        first_line = next(line for line in text.strip().splitlines() if line.strip())
        print(f"  {name:<12}{first_line}{marker}")
    print("\nRun one with: engineering-crew run --requirement <name>")
    print("Or supply your own with: engineering-crew run --file spec.txt")
    return 0


def _resolve_requirement(args: argparse.Namespace) -> str:
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            raise SystemExit(f"No such requirements file: {path}")
        return path.read_text(encoding="utf-8")
    return requirement_catalogue.CATALOGUE[args.requirement]


def _run(args: argparse.Namespace) -> int:
    requirement = _resolve_requirement(args)

    if not args.allow_no_docker and not docker_available():
        raise SystemExit(
            "Docker is not available, so the agents could write code but never run it.\n"
            "Start Docker Desktop, or pass --allow-no-docker to proceed anyway."
        )

    # The task YAML declares output_file paths relative to the working directory
    # (CrewAI resolves them against cwd), so anchor the run at the project root
    # and the design and test summary land in the sandbox wherever you invoked from.
    os.chdir(settings.PROJECT_ROOT)

    from engineering_crew.crew import EngineeringCrew

    print("Requirement:\n" + requirement.strip() + "\n")
    print(f"Resetting the sandbox at {settings.SANDBOX_DIR}\n")
    reset_sandbox()

    EngineeringCrew().crew().kickoff(inputs={"requirements": requirement})

    print(f"\nThe crew has finished. Everything it built is in {settings.SANDBOX_DIR}:")
    for path in sorted(settings.SANDBOX_DIR.iterdir()):
        print(f"  {path.name}")
    print(f"\nTry the app:  cd {settings.SANDBOX_DIR} && uv run app.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="engineering-crew", description="Four agents that design, build and test software."
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="check Docker, uv and the API key")
    sub.add_parser("show", help="list the built-in requirements")

    run = sub.add_parser("run", help="build software from a requirement")
    run.add_argument(
        "--requirement",
        choices=sorted(requirement_catalogue.CATALOGUE),
        default=requirement_catalogue.DEFAULT,
        help="a built-in requirement to build",
    )
    run.add_argument("--file", help="path to a file containing your own requirement")
    run.add_argument(
        "--allow-no-docker",
        action="store_true",
        help="run even though code execution will fail (not recommended)",
    )

    # So a bare `engineering-crew` behaves as `engineering-crew run`.
    parser.set_defaults(requirement=requirement_catalogue.DEFAULT, file=None, allow_no_docker=False)

    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "doctor":
        return _doctor()
    if command == "show":
        return _show()
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
