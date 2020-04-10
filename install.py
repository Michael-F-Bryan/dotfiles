#!/bin/env python3

"""
A script for setting up a Linux system just the way you want it.
"""

__author__ = "Michael-F-Bryan <michaelfbryan@gmail.com>"

from pathlib import Path
import argparse
import os
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
import logging
from typing import TextIO, Iterable, List, Callable, Tuple
import json
import subprocess
from subprocess import CompletedProcess

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s [%(name)s]: %(message)s",
)

logger = logging.getLogger(__name__)


def get_log_level(verbosity: int) -> int:
    levels = {
        0: logging.WARN,
        1: logging.INFO,
        2: logging.DEBUG,
    }

    return levels.get(verbosity, logging.DEBUG)


class Environment:
    """
    A helper for interacting with the outside environment.
    """

    def __init__(self, dry_run: bool, log_level: int, dotfiles_root: Path):
        self.dry_run = dry_run
        self.log_level = log_level
        self.dotfiles_root = dotfiles_root

    @property
    def quiet(self) -> bool:
        return self.log_level > logging.INFO

    def subcommand(
        self, cmd: List[str], sudo=False, stdout=None, stderr=None
    ) -> CompletedProcess:
        """
        Execute a shell command.
        """
        if sudo:
            cmd = ["sudo"] + cmd

        logger.debug("Running %s", cmd)

        if self.dry_run:
            return CompletedProcess(cmd, 0)
        else:
            return subprocess.run(cmd, stdout=stdout, stderr=stderr)

    def symlink(self, src: Path, dest: Path):
        if not os.path.exists(dest.parent):
            self.mkdir(dest.parent)

        logger.debug("Linking %s → %s", src, dest)

        if not self.dry_run:
            os.symlink(src, dest, target_is_directory=src.is_dir())

    def mkdir(self, dirname: Path):
        logger.debug("Creating %s", dirname)

        if not self.dry_run:
            os.makedirs(dirname, exist_ok=True)


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
        return f"use {program} to install {packages[0]}"
    elif package_count < 5:
        comma_separated = ", ".join(packages)
        return f"use {program} to install {comma_separated}"
    else:
        return f"Use {program} to install {package_count} packages"


class InstallPackages:
    """
    Installs system packages using a pacman-like package manager.
    """

    def __init__(self, packages: Iterable[str], program: str, needs_sudo: bool):
        self.packages: List[str] = list(packages)
        self.program = program
        self.needs_sudo = needs_sudo

        if len(self.packages) == 0:
            raise ValueError("No packages specified")

    def __call__(self, env: Environment):
        args = [self.program, "--sync", "--needed", "--noconfirm"]

        if env.quiet:
            args.append("--quiet")

        args.extend(self.packages)

        env.subcommand(
            args, sudo=self.needs_sudo,
        )

    def __str__(self) -> str:
        return _str_install_with(self.packages, self.program)


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
        return "ensure the `yay` AUR helper is installed"


class ApplySymlinks:
    def __init__(self, links: Iterable[Tuple[str, str]]):
        self.links = list(links)

    def __call__(self, env: Environment):
        for original, target in self.links:
            src = env.dotfiles_root.joinpath(original)
            dest = self.resolve(target)
            env.symlink(src, dest)

    def resolve(self, s: str) -> Path:
        transforms = [os.path.expanduser, os.path.expandvars]

        for transform in transforms:
            s = transform(s)

        return Path(s).resolve()

    def __str__(self) -> str:
        num_links = len(self.links)

        if num_links == 1:
            return "apply 1 symlink"
        else:
            return f"apply {len(self.links)} symlinks"


def compile_config(reader: TextIO) -> Iterable[Step]:
    """
    Reads the configuration file and compiles it into a "recipe" which can be
    executed to set up the system.
    """
    raw = json.load(reader)

    arch_packages = raw.get("arch-packages")
    if arch_packages:
        yield InstallPackages(arch_packages, "pacman", True)

    aur_packages = raw.get("aur-packages")
    if aur_packages:
        yield EnsureYayInstalled()
        yield InstallPackages(aur_packages, "yay", False)

    links = raw.get("symlinks")
    if links:
        yield ApplySymlinks(links.items())


def main(config: TextIO, env: Environment):
    steps = list(compile_config(config))
    logger.info("Found %d steps after parsing the config", len(steps))

    for step in steps:
        logger.info('Beginning "%s"', step)
        step(env)


def dotfiles_root() -> Path:
    return Path(__file__).resolve().parent


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--dry-run",
        default=False,
        action="store_true",
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
    parser.add_argument(
        "-d",
        "--dotfiles",
        default=dotfiles_root(),
        help="The dotfiles repository directory (default: %(default)s)",
    )
    args = parser.parse_args()

    log_level = get_log_level(args.verbose)
    logger.setLevel(log_level)
    logger.info("Starting installation")
    logger.debug("Args: %s", vars(args))

    env = Environment(args.dry_run, log_level, args.dotfiles)

    main(args.config, env)
