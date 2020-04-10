#!/bin/env python3

"""
A script for setting up a Linux system just the way you want it.
"""

__author__ = "Michael-F-Bryan <michaelfbryan@gmail.com>"

from pathlib import Path
import argparse
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
import logging
from typing import TextIO, Iterable, List, Callable
import json
import subprocess
from subprocess import CompletedProcess

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s [%(name)s]: %(message)s",
)

logger = logging.getLogger(__name__)


def _set_log_level(verbosity: int):
    levels = {
        0: logging.WARN,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    logger.setLevel(levels.get(verbosity, logging.DEBUG))


class Environment:
    """
    A helper for interacting with the outside environment.
    """

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run

    def subcommand(self, cmd: List[str], sudo=False, stdout=None) -> CompletedProcess:
        """
        Execute a shell command.
        """
        if sudo:
            cmd = ["sudo"] + cmd

        logger.debug("Running %s", cmd)

        if self.dry_run:
            return CompletedProcess(cmd, 0)
        else:
            return subprocess.run(cmd, stdout=stdout)


def already_installed(package: str, env: Environment) -> bool:
    """
    Ask pacman if a package is already installed.
    """
    logger.debug("Checking if %s is already installed", package)

    output = env.subcommand(
        ["pacman", "--query", "--info", "--quiet"], stdout=subprocess.DEVNULL
    )

    return output.returncode == 0


Step = Callable[[Environment], None]


def _str_install_with(packages: List[str], program: str) -> str:
    package_count = len(packages)

    if package_count == 1:
        return f"install {packages[0]} with {program}"
    elif package_count < 5:
        comma_separated = ", ".join(packages)
        return f"install {comma_separated } with {program}"
    else:
        return f"Install {package_count} packages with {program}"


class PacmanInstall:
    """
    Installs system packages using the official package manager.
    """

    def __init__(self, packages: Iterable[str]):
        self.packages: List[str] = list(packages)

        if len(self.packages) == 0:
            raise ValueError("No packages specified")

    def __call__(self, env: Environment):
        env.subcommand(["pacman", "--sync", "--needed"] + self.packages, sudo=True)

    def __str__(self) -> str:
        return _str_install_with(self.packages, "pacman")


class EnsureYayInstalled:
    def __init__(self, repo="https://github.com/Jguer/yay"):
        self.repo = repo

    def __call__(self, env: Environment):
        if already_installed("yay", env):
            logger.debug("yay is already installed, continuing...")
            return

        with TemporaryDirectory() as temp:
            dest = Path(temp).joinpath("yay")
            logger.debug("Cloning yay to %s", dest)

            env.subcommand(["git", "clone", self.repo, str(dest)])

            pkgconfig = dest.joinpath("PKGBUILD")
            logger.debug("Installing %s", pkgconfig)
            env.subcommand(["makepkg", "--syncdeps", "--install", "-p", str(pkgconfig)])

    def __str__(self):
        return "Ensure the `yay` AUR helper is installed"


class YayInstall:
    def __init__(self, packages: Iterable[str]):
        self.packages: List[str] = list(packages)

    def __call__(self, env: Environment):
        env.subcommand(["yay", "--sync", "--needed"] + self.packages)

    def __str__(self) -> str:
        return _str_install_with(self.packages, "yay")


def compile_config(reader: TextIO) -> Iterable[Step]:
    """
    Reads the configuration file and compiles it into a "recipe" which can be
    executed to set up the system.
    """
    raw = json.load(reader)

    arch_packages = raw.get("arch-packages")
    if arch_packages:
        yield PacmanInstall(arch_packages)

    aur_packages = raw.get("aur-packages")
    if aur_packages:
        yield EnsureYayInstalled()
        yield YayInstall(aur_packages)


def main(config: TextIO, dry_run: bool):
    env = Environment(dry_run)

    for step in compile_config(config):
        logger.info("Beginning %s", step)
        step(env)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--dry-run",
        default=False,
        help="Show all the commands which would be executed, but don't actually do anything.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.json",
        type=argparse.FileType("r"),
        help="The configuration file to read from (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        default=0,
        action="count",
        help="Generate detailed output, repeat for increased verbosity",
    )
    args = parser.parse_args()

    _set_log_level(args.verbose)
    logger.info("Starting installation")
    logger.debug("Args: %s", vars(args))

    main(args.config, args.dry_run)
