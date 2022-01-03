"""
This file builds .whl packages for Linux using the manylinux1 docker file.
"""

__all__ = ["manylinux_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, Test, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileDownload, FileUpload
from buildbot.config import BuilderConfig

import config
from .common import common_flags, whl_version_steps, whl_version, is_branch
from . import common


@renderer
def setarch(props):
    "Returns the appropriate setarch command if needed."

    if "arch" in props and props["arch"] not in ("amd64", "x86_64", "aarch64"):
        return ["setarch", props["arch"]]
    else:
        return []


def is_branch_and_manylinux1(branch):
    return lambda step: (step.getProperty("branch") == branch and \
                         step.getProperty("platform", "").startswith("manylinux1"))


def is_not_manylinux1():
    return lambda step: not step.getProperty("platform", "").startswith("manylinux1")


def get_clean_command():
    "Returns the command used to clean the build."

    return [
        "docker", "run", "--rm=true",
        #"-i", Interpolate("--name=%(prop:buildername)s"),
        "-v", Interpolate("%(prop:builddir)s/build/:/build/:rw"),
        "-w", "/build/",
        Property("platform"),

        "rm", "-rf", common.outputdir, ".pytest_cache",
    ]


def get_build_command(abi):
    "Returns the command used to compile Panda3D from source."

    return [
        "docker", "run", "--rm=true",
        #"-i", Interpolate("--name=%(prop:buildername)s"),
        "-v", Interpolate("%(prop:builddir)s/build/:/build/:rw"),
        "-w", "/build/",
        "-e", "CXXFLAGS=-Wno-int-in-bool-context",
        "-e", Interpolate("SOURCE_DATE_EPOCH=%(prop:commit-timestamp)s"),
        "-e", "PYTHONHASHSEED=0",
        Property("platform"),

        setarch,
        "/opt/python/%s/bin/python" % (abi),
         "makepanda/makepanda.py",
        "--everything", "--no-directscripts",
        "--no-gles", "--no-gles2",
        "--python-incdir=/opt/python/%s/include" % (abi),
        "--python-libdir=/opt/python/%s/lib" % (abi),
        common_flags,
        "--outputdir", common.outputdir,
        "--wheel", "--version", whl_version,
    ]


def get_test_command(abi, whl_filename):
    "Returns the command used to run the test suite in a virtualenv."

    return [
        "docker", "run", "--rm=true",
        #"-i", Interpolate("--name=%(prop:buildername)s"),
        "-v", Interpolate("%(prop:builddir)s/build/:/build/:rw"),
        "-w", "/build/",
        Property("platform"),

        setarch,
        "/opt/python/%s/bin/python" % (abi),
        "makepanda/test_wheel.py",
        "--verbose",
        whl_filename,
    ]


# The command to set up the Docker image.
setup_cmd = [
    "docker", "build", "-t",
    Property("platform"),
    "docker/"
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        "python3", "makepanda/getversion.py"],
        haltOnFailure=True),

    # Steps to figure out which .whl version to use.
    ] + whl_version_steps + [

    # Download and run the script to set up manylinux.
    FileDownload(mastersrc="build_scripts/prepare_manylinux.sh", workerdest="prepare_manylinux.sh", workdir="."),
    ShellCommand(name="prepare", command=["bash", "prepare_manylinux.sh", Property("platform")], workdir=".", haltOnFailure=True),

    # Download the Dockerfile for this distribution.
    FileDownload(mastersrc=Interpolate("dockerfiles/%(prop:platform)s"),
                 workerdest="docker/Dockerfile", workdir="manylinux"),

    # Build the Docker image.
    ShellCommand(name="setup", command=setup_cmd, workdir="manylinux", haltOnFailure=True),

    # Delete the built dir, if requested.  Requires running in Docker because the files are
    # owned by the root user (since the docker container runs as root)
    ShellCommand(name="clean", command=get_clean_command(),
                 haltOnFailure=False, doStepIf=lambda step:step.getProperty("clean", False)),
]

for abi in ('cp310-cp310', 'cp39-cp39', 'cp37-cp37m', 'cp38-cp38', 'cp36-cp36m', 'cp27-cp27mu', 'cp35-cp35m', 'cp34-cp34m'):
    whl_filename = common.get_whl_filename(abi)

    do_step = True
    if abi in ('cp27-cp27mu', 'cp34-cp34m', 'cp35-cp35m'):
        do_step = is_branch_and_manylinux1('release/1.10.x')
    elif abi.startswith('cp31'):
        do_step = is_not_manylinux1()

    build_steps += [
        # Invoke makepanda and makewheel.
        Compile(name="compile "+abi, command=get_build_command(abi),
                haltOnFailure=True, doStepIf=do_step),

        # Run the test suite in a virtualenv.
        Test(name="test "+abi, command=get_test_command(abi, whl_filename),
             haltOnFailure=True, doStepIf=do_step),

        # Upload the wheel file.
        FileUpload(name="upload "+abi, workersrc=whl_filename,
                   masterdest=Interpolate("%s/%s", common.upload_dir, whl_filename),
                   mode=0o664, haltOnFailure=True, doStepIf=do_step),

        # Now delete it.
        ShellCommand(name="rm "+abi, command=['rm', whl_filename],
                     haltOnFailure=False, doStepIf=do_step),
    ]

manylinux_factory = BuildFactory()
for step in build_steps:
    manylinux_factory.addStep(step)


def manylinux_builder(suite, arch):
    platform = "-".join((suite, arch))
    return BuilderConfig(name=platform,
                         workernames=config.linux_workers,
                         factory=manylinux_factory,
                         properties={"arch": arch, "platform": platform})
