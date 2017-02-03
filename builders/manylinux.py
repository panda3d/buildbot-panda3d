"""
This file builds .whl packages for Linux using the manylinux1 docker file.
"""

__all__ = ["manylinux_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileDownload, FileUpload
from buildbot.config import BuilderConfig

import config
from .common import common_flags, python_abi, whl_version_steps, whl_version, whl_filename, whl_upload_filename

@renderer
def python_incdir(props):
    "Returns the path to the Python include directory."

    abi = python_abi.getRenderingFor(props)
    return "/opt/python/%s/include" % (abi)

@renderer
def python_libdir(props):
    "Returns the path to the Python library directory."

    abi = python_abi.getRenderingFor(props)
    return "/opt/python/%s/lib" % (abi)

@renderer
def python_executable(props):
    "Returns the path to the Python executable."

    abi = python_abi.getRenderingFor(props)
    return "/opt/python/%s/bin/python" % (abi)

@renderer
def built_dir(props):
    "Returns the name of the build directory to use."

    abi = python_abi.getRenderingFor(props)
    return "built-" + abi

@renderer
def setarch(props):
    "Returns the appropriate setarch command if needed."

    if "arch" in props and props["arch"] not in ("amd64", "x86_64"):
        return ["setarch", props["arch"]]
    else:
        return []

# The command to set up the Docker image.
setup_cmd = [
    "docker", "build", "-t",
    Property("platform"),
    "."
]

# The command used to compile Panda3D from source.
build_cmd = [
    "docker", "run", "--rm=true",
    "-i", Interpolate("--name=%(prop:buildername)s"),
    "-v", Interpolate("%(prop:workdir)s/build/:/build/:rw"),
    "-w", "/build/",
    Property("platform"),

    setarch,
    python_executable, "makepanda/makepanda.py",
    "--everything", "--no-directscripts",
    "--no-gles", "--no-gles2", "--no-egl",
    "--python-incdir", python_incdir,
    "--python-libdir", python_libdir,
    common_flags,
    "--outputdir", built_dir,
    "--wheel", "--version", whl_version,
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        "python", "makepanda/getversion.py"],
        haltOnFailure=True),

    # Steps to figure out which .whl version to use.
    ] + whl_version_steps + [

    # Download the Dockerfile for this distribution.
    FileDownload(mastersrc=Interpolate("dockerfiles/manylinux1-%(prop:arch)s"),
                 slavedest="Dockerfile", workdir="context"),

    # And the build scripts.
    FileDownload(mastersrc="build_scripts/build.sh", slavedest="build_scripts/build.sh", workdir="context"),
    FileDownload(mastersrc="build_scripts/build_utils.sh", slavedest="build_scripts/build_utils.sh", workdir="context"),

    # Build the Docker image.
    ShellCommand(name="setup", command=setup_cmd, workdir="context", haltOnFailure=True),

    # Invoke makepanda and makewheel.
    Compile(command=build_cmd, haltOnFailure=True),

    # Upload the wheel file.
    FileUpload(slavesrc=whl_filename, masterdest=whl_upload_filename,
            mode=0o664, haltOnFailure=True),
]

manylinux_factory = BuildFactory()
for step in build_steps:
    manylinux_factory.addStep(step)


def manylinux_builder(suite, arch):
    platform = "-".join((suite, arch))
    return BuilderConfig(name=platform,
                         slavenames=config.linux_slaves,
                         factory=manylinux_factory,
                         properties={"arch": arch, "platform": platform})
