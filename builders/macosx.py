__all__ = ["macosx_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, Test, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileUpload
from buildbot.steps.master import MasterShellCommand
from buildbot.steps.worker import RemoveDirectory
from buildbot.config import BuilderConfig

import config
from .common import common_flags, buildtype_flag, whl_version_steps, whl_version, publish_rtdist_steps, is_branch
from .common import MakeTorrent, SeedTorrent
from . import common


def get_dmg_filename():
    "Determines the name of a .dmg file produced by makepanda."

    return Interpolate("Panda3D-%(prop:version)s.dmg")


@renderer
def dmg_version(props):
    version = props["version"]
    if not props["revision"].startswith("v"):
        version += "-" + props["got_revision"][:7]

    if version.startswith("1.9.") or version.startswith("1.10."):
        version += '-MacOSX' + props["osxtarget"]

    return version


def get_dmg_upload_filename():
    "Determines the upload location of an .dmg file on the master."

    return Interpolate("%s/Panda3D-SDK-%s.dmg",
        common.upload_dir, dmg_version)


@renderer
def universal_flag(props):
    if props["osxtarget"] == "10.6":
        return ["--universal"]
    else:
        return []


@renderer
def platform_prefix(props):
    osxver = props["osxtarget"]
    return "macosx_" + osxver.replace('.', '_')


def get_whl_filename(abi, arch):
    "Determines the name of a .whl file for uploading."

    return Interpolate("panda3d-%s-%s-%s_%s.whl", whl_version, abi, platform_prefix, arch)


@renderer
def outputdir(props):
    version = props["version"].split('.')
    dir = 'built{0}.{1}'.format(*version)

    if props.getProperty("optimize", False):
        dir += '-opt'

    return [dir]


def get_build_step(abi):
    command = [
        "/usr/local/bin/python%s.%s" % (abi[2], abi[3]),
        "makepanda/makepanda.py",
        "--everything",
        "--outputdir", outputdir,
        common_flags, universal_flag,
        "--osxtarget", Property("osxtarget"),
        "--no-gles", "--no-gles2", "--no-egl",
        "--version", Property("version"),
    ]

    do_step = True
    if abi in ('cp27-cp27m', 'cp34-cp34m', 'cp35-cp35m'):
        do_step = is_branch('release/1.10.x')

    # Run makepanda - give it enough timeout (1h)
    s = Compile(name='compile '+abi, command=command, timeout=1*60*60,
                env={"MAKEPANDA_THIRDPARTY": "/Users/buildbot/thirdparty",
                     "MAKEPANDA_SDKS": "/Users/buildbot/sdks"},
                haltOnFailure=True, doStepIf=do_step)
    return s


def get_test_step(abi):
    # Run the test suite.
    command = [
        "/usr/local/bin/python%s.%s" % (abi[2], abi[3]),
        "-B", "-m", "pytest", "tests",
    ]

    do_step = True
    if abi in ('cp27-cp27m', 'cp34-cp34m', 'cp35-cp35m'):
        do_step = is_branch('release/1.10.x')

    test = Test(name='test '+abi, command=command,
                env={"PYTHONPATH": outputdir},
                haltOnFailure=True, doStepIf=do_step)
    return test


def get_makewheel_step(abi, arch):
    command = [
        "/usr/local/bin/python%s.%s" % (abi[2], abi[3]),
        "makepanda/makewheel.py",
        "--outputdir", outputdir,
        "--version", whl_version,
        "--platform", Interpolate("macosx-%s-%s", Property("osxtarget"), arch),
        "--verbose",
    ]

    do_step = True
    if abi in ('cp27-cp27m', 'cp34-cp34m', 'cp35-cp35m'):
        do_step = is_branch('release/1.10.x')

    return ShellCommand(name="makewheel " + arch + " " + abi,
                        command=command,
                        haltOnFailure=True, doStepIf=do_step)


def get_upload_step(abi, arch, file):
    do_step = True
    if abi in ('cp27-cp27m', 'cp34-cp34m', 'cp35-cp35m'):
        do_step = is_branch('release/1.10.x')

    return FileUpload(
        name="upload " + arch + " " + abi, workersrc=file,
        masterdest=Interpolate("%s/%s", common.upload_dir, file),
        mode=0o664, haltOnFailure=True, doStepIf=do_step)


# The command used to create the .dmg installer.
package_cmd = [
    "python3", "makepanda/makepackage.py",
    "--verbose",
    "--version", Property("version"),
    "--outputdir", outputdir,
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        "python3", "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),

    # Delete the built dir, if requested.
    ShellCommand(name="clean",
                 command=["rm", "-rf", outputdir, ".pytest_cache", get_dmg_filename(), "dstroot"],
                 haltOnFailure=False, doStepIf=lambda step:step.getProperty("clean", False)),
]

build_steps += whl_version_steps
build_steps_10_6 = build_steps[:]
build_steps_10_9 = build_steps[:]

for abi in ('cp37-cp37m', 'cp36-cp36m', 'cp27-cp27m', 'cp35-cp35m', 'cp34-cp34m'):
    whl_filename32 = get_whl_filename(abi, 'i386')
    whl_filename64 = get_whl_filename(abi, 'x86_64')

    build_steps_10_6 += [
        get_build_step(abi),
        get_test_step(abi),

        # Build two wheels: one for 32-bit, the other for 64-bit.
        # makewheel is clever enough to use "lipo" to extract the right arch.
        get_makewheel_step(abi, 'i386'),
        get_makewheel_step(abi, 'x86_64'),
        get_upload_step(abi, 'i386', whl_filename32),
        get_upload_step(abi, 'x86_64', whl_filename64),

        # Now delete them.
        ShellCommand(name="rm "+abi, command=['rm', '-f', whl_filename32, whl_filename64], haltOnFailure=False),
    ]

for abi in ('cp38-cp38', 'cp37-cp37m', 'cp36-cp36m', 'cp27-cp27m', 'cp35-cp35m'):
    whl_filename64 = get_whl_filename(abi, 'x86_64')

    build_steps_10_9 += [
        get_build_step(abi),
        get_test_step(abi),
        get_makewheel_step(abi, 'x86_64'),
        get_upload_step(abi, 'x86_64', whl_filename64),
        ShellCommand(name="rm "+abi, command=['rm', '-f', whl_filename64], haltOnFailure=False),
    ]

# Build and upload the installer.
package_steps = [
    ShellCommand(name="package", command=package_cmd, haltOnFailure=True),

    FileUpload(name="upload dmg", workersrc=get_dmg_filename(),
               masterdest=get_dmg_upload_filename(),
               mode=0o664, haltOnFailure=True),
]
build_steps_10_6 += package_steps
build_steps_10_9 += package_steps


def macosx_builder(osxver):
    if osxver in ('10.6', '10.7', '10.8'):
        workernames = config.macosx_10_6_workers
        buildsteps = build_steps_10_6
    else:
        workernames = config.macosx_10_9_workers
        buildsteps = build_steps_10_9

    factory = BuildFactory()
    for step in buildsteps:
        factory.addStep(step)

    return BuilderConfig(name='macosx' + ('-' + osxver if osxver else ''),
                         workernames=workernames,
                         factory=factory,
                         properties={"osxtarget": osxver, "buildtype": "sdk"})
