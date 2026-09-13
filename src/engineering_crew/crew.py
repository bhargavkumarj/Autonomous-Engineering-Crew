"""The crew: four role-based agents that design, build, present and test software.

The agents and tasks are declared in YAML (`config/agents.yaml`,
`config/tasks.yaml`) and wired here. That split is CrewAI's central idea and it
earns its keep: the roles, goals, backstories and task descriptions — the parts
that get edited constantly and read like specifications — live in a file a
non-engineer can review, and this module contains only the wiring.

The pipeline is sequential, and each task declares the earlier tasks whose output
it needs:

    design_task     (lead)      →  a written design, no code
      ├── code_task      (backend)   needs: design
      ├── frontend_task  (frontend)  needs: design, code
      └── test_task      (test)      needs: design, code
                                     writes tests, RUNS them, fixes the backend,
                                     reruns until green

Two agents get the Context7 MCP server. Two do not, on purpose — see below.
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from engineering_crew.settings import CONTEXT7_MCP_URL, USE_CONTEXT7
from engineering_crew.tools.sandbox import sandbox_tools

#: The lead and the frontend engineer query Context7 for current library APIs.
#: The backend and test engineers are stdlib-only by their goals, so a
#: documentation server would be turns spent on nothing.
_DOCS_MCP = [CONTEXT7_MCP_URL] if USE_CONTEXT7 else []


@CrewBase
class EngineeringCrew:
    """Four engineers who take a requirement and hand back working software."""

    agents: list[BaseAgent]
    tasks: list[Task]

    # ---------------------------------------------------------------- agents

    @agent
    def engineering_lead(self) -> Agent:
        """Designs the system and assigns the work. The only agent with no sandbox.

        Deliberately toolless apart from documentation: the design task's
        instructions say "function signatures only, do not write any code", and
        an agent with a file-writing tool will write code no matter what the
        prompt says. Withholding the capability is more reliable than asking.
        """
        return Agent(config=self.agents_config["engineering_lead"], verbose=True, mcps=_DOCS_MCP)

    @agent
    def backend_engineer(self) -> Agent:
        """Implements the design in the sandbox, stdlib only."""
        return Agent(config=self.agents_config["backend_engineer"], verbose=True, tools=sandbox_tools)

    @agent
    def frontend_engineer(self) -> Agent:
        """Builds a Gradio UI over the backend, and validates that it constructs."""
        return Agent(
            config=self.agents_config["frontend_engineer"],
            verbose=True,
            tools=sandbox_tools,
            mcps=_DOCS_MCP,
        )

    @agent
    def test_engineer(self) -> Agent:
        """Writes unit tests, runs them, fixes the backend, reruns until they pass.

        The one agent with a real oracle: it is not judging its own work, it is
        reading an exit code and a traceback from a process it does not control.
        """
        return Agent(config=self.agents_config["test_engineer"], verbose=True, tools=sandbox_tools)

    # ----------------------------------------------------------------- tasks

    @task
    def design_task(self) -> Task:
        return Task(config=self.tasks_config["design_task"])

    @task
    def code_task(self) -> Task:
        return Task(config=self.tasks_config["code_task"])

    @task
    def frontend_task(self) -> Task:
        return Task(config=self.tasks_config["frontend_task"])

    @task
    def test_task(self) -> Task:
        return Task(config=self.tasks_config["test_task"])

    # ------------------------------------------------------------------ crew

    @crew
    def crew(self) -> Crew:
        """A sequential crew.

        Sequential rather than hierarchical because the dependencies here are
        genuinely linear — you cannot test code that has not been written. A
        manager agent deciding the order would add a model call per step and a
        chance of getting it wrong, in exchange for flexibility this pipeline
        does not need.
        """
        return Crew(
            agents=self.agents,  # collected by the @agent decorators
            tasks=self.tasks,  # collected by the @task decorators, in declaration order
            process=Process.sequential,
            verbose=True,
            tracing=True,
        )
