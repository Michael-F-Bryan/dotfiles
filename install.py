#!/bin/env python3

"""
A script for setting up a Linux system just the way you want it.
"""

__author__ = "Michael-F-Bryan <michaelfbryan@gmail.com>"

from pathlib import Path
import argparse
import os
import shutil
from tempfile import TemporaryDirectory, NamedTemporaryFile
from argparse import ArgumentParser
import logging
from typing import TextIO, Iterable, List, Callable, Tuple, Optional, Set, Dict
import json
import subprocess
from subprocess import CompletedProcess
from urllib import request
import re

logger = logging.getLogger(__name__)

# The maximum number of items to be printed in __str__() methods
MAX_ITEMS_IN_DUNDER_STR = 5

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s [%(name)s]: %(message)s",
)


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

    def __init__(self, dry_run: bool, log_level: int, dotfiles_root: Path, force: bool):
        self.dry_run = dry_run
        self.log_level = log_level
        self.dotfiles_root = dotfiles_root
        self.force = force
        self.logger = logger

        self.logger.setLevel(log_level)

    def execute_step(self, step: Callable[["Environment"], None]):
        logger = self.logger

        try:
            self.logger = logging.getLogger(type(step).__qualname__)
            self.logger.setLevel(self.log_level)
            self.logger.info('Beginning "%s"', step)
            step(self)
        finally:
            self.logger = logger

    @property
    def quiet(self) -> bool:
        """
        Has the user asked for less detailed output?
        """
        return self.log_level > logging.INFO

    def subcommand(
        self, cmd: List[str], sudo=False, stdout=None, stderr=None
    ) -> CompletedProcess:
        """
        Execute a shell command.
        """
        if sudo:
            cmd = ["sudo"] + cmd

        self.logger.debug("Running %s", cmd)

        if self.dry_run:
            return CompletedProcess(cmd, 0)
        else:
            return subprocess.run(cmd, stdout=stdout, stderr=stderr, encoding="UTF-8")

    def is_okay_to_overwrite(self, target: Path) -> bool:
        """
        Is it okay to overwrite `target`?
        """
        return self.force

    def remove(self, target: Path):
        """
        Remove a file or directory.
        """
        self.logger.debug("Removing %s", target)

        if self.dry_run:
            return

        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            os.remove(target)

    def symlink(self, link: Path, target: Path):
        """
        Create a symbolic link from `link` to `target`.

        If the destination already exists, it will only be overwritten if
        `self.is_okay_to_overwrite()` says it's okay (e.g. the `--force`
        argument was provided at the command line).
        """
        if not os.path.exists(link.parent):
            self.mkdir(link.parent)

        if link.is_symlink() or link.exists():
            if self.is_okay_to_overwrite(link):
                self.remove(link)
            else:
                self.logger.warning(
                    "Not symlinking %s → %s because it already exists", link, target,
                )
                return

        self.logger.debug("Linking %s → %s", link, target)

        if not self.dry_run:
            os.symlink(target, link, target_is_directory=target.is_dir())

    def mkdir(self, dirname: Path):
        """
        Make sure a directory exists.
        """
        self.logger.debug("Creating %s", dirname)

        if not self.dry_run:
            os.makedirs(dirname, exist_ok=True)


def already_installed(package: str, env: Environment) -> bool:
    """
    Ask pacman if a package is already installed.
    """
    env.logger.debug("Checking if %s is already installed", package)

    output = env.subcommand(
        ["pacman", "--query", "--info", "--quiet"], stdout=subprocess.DEVNULL
    )

    return output.returncode == 0


Step = Callable[[Environment], None]


def _packages_install_str(packages: List[str], program: str) -> str:
    package_count = len(packages)

    if package_count == 1:
        return f"use {program} to install {packages[0]}"
    elif package_count < MAX_ITEMS_IN_DUNDER_STR:
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

        env.subcommand(args, sudo=self.needs_sudo,).check_returncode()

    def __str__(self) -> str:
        return _packages_install_str(self.packages, self.program)


class EnsureYayInstalled:
    def __init__(self, repo="https://github.com/Jguer/yay"):
        self.repo = repo

    def __call__(self, env: Environment):
        if already_installed("yay", env):
            env.logger.debug("yay is already installed, continuing...")
            return

        with TemporaryDirectory() as temp:
            dest = Path(temp).joinpath("yay")
            env.logger.debug("Cloning yay to %s", dest)

            env.subcommand(["git", "clone", self.repo, str(dest)]).check_returncode()

            pkgconfig = dest.joinpath("PKGBUILD")
            env.logger.debug("Installing %s", pkgconfig)
            env.subcommand(
                ["makepkg", "--syncdeps", "--install", "-p", str(pkgconfig)]
            ).check_returncode()

    def __str__(self):
        return "ensure the `yay` AUR helper is installed"


def resolve_path(s: str) -> Path:
    transforms = [os.path.expanduser, os.path.expandvars]

    for transform in transforms:
        s = transform(s)

    return Path(s)


class ApplySymlinks:
    """
    Create symbolic links from something in the dotfiles directory to files on
    disk.
    """

    def __init__(self, links: Dict[str, str]):
        self.links = links

    def __call__(self, env: Environment):
        for original, target in self.links.items():
            full_name = env.dotfiles_root.joinpath(original)
            link = resolve_path(target)
            env.symlink(link, full_name)

    def __str__(self) -> str:
        num_links = len(self.links)

        if num_links == 1:
            return "apply 1 symlink"
        else:
            return f"apply {len(self.links)} symlinks"


def which(program) -> Optional[Path]:
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = Path(path).joinpath(program)
            if is_exe(exe_file):
                return exe_file

    return None


class EnsureRustIsInstalled:
    def __init__(
        self, default_channel: Optional[str] = None, url="http://sh.rustup.rs/"
    ):
        self.default_channel = default_channel
        self.url = url

    def __call__(self, env: Environment):
        """
        Do the equivalent of `curl http://sh.rustup.rs/ | sh
        """
        if self.already_installed():
            env.logger.debug("Rust is already installed")
            return

        env.logger.debug("Downloading %s and executing", self.url)

        if env.dry_run:
            return

        with NamedTemporaryFile(suffix=".sh") as f, request.urlopen(
            self.url
        ) as response:
            if response.status != 200:
                raise Exception(
                    f"Response failed with {response.status} {response.reason}"
                )

            shutil.copyfileobj(response, f)
            f.flush()

            self.call_rustup_sh(f.name, env)

    def call_rustup_sh(self, filename: str, env: Environment):
        args = ["sh", str(filename), "-y", "--no-modify-path"]

        if env.quiet:
            args.append("--quiet")

        if self.default_channel:
            args.append("--default-toolchain")
            args.append(self.default_channel)

        env.subcommand(args).check_returncode()

    def already_installed(self) -> bool:
        return bool(which("rustup"))

    def __str__(self):
        return "ensure Rust is installed"


class CargoInstall:
    """
    Install Rust packages using cargo.
    """

    def __init__(self, packages: Iterable[str]):
        self.packages: Set[str] = set(packages)

    def __call__(self, env: Environment):
        args = ["cargo", "install"]

        if env.force:
            args.append("--force")
            args.extend(self.packages)
        else:
            already_installed = set(self.get_installed_packages(env))
            env.logger.debug("Cargo packages already installed: %s", already_installed)
            to_install = self.packages.difference(already_installed)

            if not to_install:
                env.logger.info("Everything is already installed")
                return

            args.extend(to_install)

        env.subcommand(args).check_returncode()

    def get_installed_packages(self, env: Environment) -> Iterable[str]:
        crates_toml = Path.home().joinpath(".cargo", ".crates.toml")

        if not crates_toml.exists():
            return

        # a quick'n'dirty TOML parser for the v1 format

        with open(crates_toml, "r") as f:
            for line in f:
                match = re.search(r'^"([\w\d_-]+)[^"]*"\s*=', line)
                if match:
                    yield match.group(1)

    def __str__(self) -> str:
        return _packages_install_str(list(self.packages), "cargo")


class CopySecretsToDisk:
    def __init__(self, secrets: Dict[str, Dict[str, str]], username: Optional[str]):
        self.secrets = secrets
        self.username = username

    def __call__(self, env: Environment):
        self._check_logged_in(env)

        for secret, files in self.secrets.items():
            attachments = self.attachments(env, secret, files.keys())
            env.logger.debug(
                '"%s" has the following attachments: %s', secret, attachments
            )

            for file, target in files.items():
                attachment_id = attachments[file]
                dest = resolve_path(target)

                self.write_attachment_to_disk(env, secret, attachment_id, file, dest)

    def write_attachment_to_disk(
        self,
        env: Environment,
        secret: str,
        attachment_id: str,
        attachment_name: str,
        dest: Path,
    ):
        env.logger.debug("Writing %s → %s", attachment_name, dest)

        if dest.exists() and not env.force:
            env.logger.warning(
                "Skipping %s because %s already exists", attachment_name, dest
            )
            return

        if env.dry_run:
            return

        with open(dest, "w") as f:
            contents = self._read_attachment(env, secret, attachment_id)
            f.write(contents)

    def _read_attachment(
        self, env: Environment, secret: str, attachment_id: str
    ) -> str:
        outcome = env.subcommand(["lpass", "show", "--attach=" + attachment_id, secret])
        outcome.check_returncode()

        return outcome.stdout

    def attachments(
        self, env: Environment, secret: str, files: Iterable[str]
    ) -> Dict[str, str]:
        """
        Check which files are attached to a secret, returning a mapping from
        filenames to attachment IDs.
        """

        if env.dry_run:
            # we need to return a dummy mapping
            return {file: "XXX" for file in files}

        else:
            output = env.subcommand(
                ["lpass", "show", "--sync=auto", secret], stdout=subprocess.PIPE
            )
            output.check_returncode()
            attachments = {}

            for line in output.stdout.splitlines():
                match = re.match(r"^att-([\d-]+):\s*(.*)$", line)
                if not match:
                    continue

                attachments[match.group(2).strip()] = match.group(1)

            return attachments

    def _check_logged_in(self, env: Environment):
        env.logger.debug("Checking if we're already logged into LastPass")
        outcome = env.subcommand(["lpass", "status"])

        if outcome.returncode != 0:
            env.logger.info("We need to login to lastpass")
            if not self.username:
                raise Exception("No username provided")

            env.subcommand(["lpass", "login", self.username]).check_returncode()

    def __str__(self) -> str:
        filenames = [
            filename for secret in self.secrets.values() for filename in secret.keys()
        ]
        if len(filenames) < MAX_ITEMS_IN_DUNDER_STR:
            names = ", ".join(filenames)
            return f"using LastPass to copy {names} to disk"
        else:
            return f"copying {len(filenames)} secrets to disk"


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
        yield ApplySymlinks(links)

    rust = raw.get("rust")
    if rust:
        yield EnsureRustIsInstalled(rust.get("default-channel"))
        install = rust.get("install")
        if install:
            yield CargoInstall(install)

    secrets = raw.get("secrets")
    if secrets:
        username = secrets.get("username")
        files = secrets.get("files")
        yield CopySecretsToDisk(files, username)


def main(config: TextIO, env: Environment):
    steps = list(compile_config(config))
    env.logger.info("Found %d steps after parsing the config", len(steps))

    for step in steps:
        env.execute_step(step)


def dotfiles_root() -> Path:
    return Path(__file__).resolve().parent


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c",
        "--config",
        default="config.json",
        type=argparse.FileType("r"),
        help="The configuration file to read from (default: %(default)s)",
    )
    parser.add_argument(
        "-d",
        "--dotfiles",
        default=dotfiles_root(),
        help="The dotfiles repository directory (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--force",
        default=False,
        action="store_true",
        help="Do things which may otherwise destroy data (e.g. overwriting files)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        default=False,
        action="store_true",
        help="Show all the commands which would be executed, but don't actually do anything.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        default=0,
        action="count",
        help="Generate detailed output, repeat for increased verbosity",
    )
    args = parser.parse_args()

    log_level = get_log_level(args.verbose)

    env = Environment(args.dry_run, log_level, args.dotfiles, args.force)

    env.logger.info("Starting installation")
    env.logger.debug("Args: %s", vars(args))

    main(args.config, env)
