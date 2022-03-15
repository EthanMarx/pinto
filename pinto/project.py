import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import toml

from pinto.env import Environment


@dataclass
class ProjectBase:
    path: str

    def __post_init__(self):
        self.path = Path(os.path.abspath(self.path))
        config_path = self.path / "pyproject.toml"
        try:
            with open(self.path / "pyproject.toml", "r") as f:
                self._config = toml.load(f)
        except FileNotFoundError:
            raise ValueError(
                "{} {} has no associated 'pyproject.toml' "
                "at location {}".format(
                    self.__class__.__name__, self.path, config_path
                )
            )

    @property
    def config(self):
        return self._config.copy()


@dataclass
class Project(ProjectBase):
    """
    Represents an individual project or library with
    an environment to be managed by some combination
    of Poetry and Conda and which may expose some set
    of command-line commands once installed
    """

    def __post_init__(self):
        super().__post_init__()
        self.name = self._config["tool"]["poetry"]["name"]
        self._venv = Environment(self)

    @property
    def pinto_config(self) -> dict:
        """
        Project Pinto settings as defined in the
        project's `pyproject.toml`
        """

        try:
            return self.config["tool"]["pinto"].copy()
        except KeyError:
            return {}

    @property
    def venv(self) -> Environment:
        """The virtual environment associated with this project"""
        return self._venv

    def install(self, force: bool = False) -> None:
        """
        Install this project into the virtual environment,
        creating the environment if necessary.

        Args:
            force:
                If `True`, update the environment even
                if the project is already installed. Otherwise,
                if the project is already installed in
                the environment, log that fact and move on.
        """

        if not self._venv.exists():
            self._venv.create()

        # ensure environment has this project
        # installed somewhere
        if not self._venv.contains(self):
            logging.info(
                "Installing project '{}' from '{}' into "
                "virtual environemnt '{}'".format(
                    self.name, self.path, self._venv.name
                )
            )
            self._venv.install()
        elif force:
            logging.info(
                "Updating project '{}' from '{}' in "
                "virtual environment '{}'".format(
                    self.name, self.path, self._venv.name
                )
            )
            # TODO: should we do a `poetry update` rather
            # than install in this case? What does that
            # command look like for the poetry env?
            self._venv.install()
        else:
            logging.info(
                "Project '{}' at '{}' already installed in "
                "virtual environment '{}'".format(
                    self.name, self.path, self._venv.name
                )
            )

    def run(self, *args: str) -> str:
        """Run a command in the project's virtual environment

        Run an individual command in the project's
        virtual environment, with each space-separated
        argument in the command given as a separate
        string argument to this method.

        If the project's virtual environment doesn't
        exist or doesn't have the project installed
        yet, `Project.install` will be called before
        executing the command.

        Args:
            *args:
                Command-line parameters to execute
                in the project's virtual environment.
                Each `arg` will be treated as a single
                command line parameter, even if there
                are spaces in it. So, for example, calling

                ```python
                project = Project(...)
                project.run("/bin/bash", "-c", "cd /home && echo $PWD")
                ```

                will execute `"cd /home && echo $PWD"` as the entire
                argument of `/bin/bash -c`.
        Returns:
            The standard output generated by executing the command
        """

        if not self._venv.exists() or not self._venv.contains(self):
            self.install()
        return self._venv.run(*args)


@dataclass
class Pipeline(ProjectBase):
    def __post_init__(self):
        super().__post_init__()

        config_path = self.path / "pyproject.toml"
        try:
            _ = self.steps
        except KeyError:
            raise ValueError(
                f"Config file {config_path} has no '[tool.pinto]' "
                "table or 'steps' key in it."
            )
        try:
            _ = self.typeo_config
        except KeyError:
            raise ValueError(
                f"Config file {config_path} has no '[tool.typeo]' "
                "table necessary to run projects."
            )

    @property
    def steps(self):
        return self.config["tool"]["pinto"]["steps"]

    @property
    def typeo_config(self):
        return self.config["tool"]["typeo"]

    def create_project(self, name):
        return Project(self.path / name)

    def run_step(
        self, project: Project, command: str, subcommand: Optional[str] = None
    ):
        typeo_arg = str(self.path)
        try:
            if command in self.typeo_config["scripts"]:
                typeo_arg += ":" + command
        except KeyError:
            if subcommand is not None:
                typeo_arg += "::" + subcommand
        else:
            if subcommand is not None:
                typeo_arg += ":" + subcommand

        project.run(command, "--typeo", typeo_arg)
