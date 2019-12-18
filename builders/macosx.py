__all__ = ["macosx_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, Test, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileUpload
from buildbot.steps.master import MasterShellCommand
from buildbot.steps.slave import RemoveDirectory
from buildbot.config import BuilderConfig

import config
from .common import common_flags, buildtype_flag, whl_version_steps, whl_version, publish_rtdist_steps
from .common import MakeTorrent, SeedTorrent
from . import common


def get_dmg_filename(abi=None):
    "Determines the name of a .dmg file produced by makepanda."

    suffix = ""
    if abi and not abi.startswith('cp27-'):
        suffix = "-py%s.%s" % (abi[2], abi[3])

    return Interpolate("Panda3D-%(prop:version)s" + suffix + ".dmg")


@renderer
def dmg_version(props):
    if props["revision"].startswith("v"):
        return props["version"]
    else:
        return "%s-%s" % (props["version"], props["got_revision"][:7])


def get_dmg_upload_filename(abi=None):
    "Determines the upload location of an .dmg file on the master."

    suffix = ""
    if abi and not abi.startswith('cp27-'):
        suffix = "-py%s.%s" % (abi[2], abi[3])

    return Interpolate("%s/Panda3D-SDK-%s%s.dmg",
        common.upload_dir, dmg_version, suffix)


@renderer
def osxtarget(props):
    version = props["version"]
    if version.startswith("1.9.") or version.startswith("1.10."):
        return "10.6"
    else:
        return "10.9"


@renderer
def platform_prefix(props):
    osxver = osxtarget.getRenderingFor(props)
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


def get_build_command(abi):
    return [
        "/usr/local/bin/python%s.%s" % (abi[2], abi[3]),
        "makepanda/makepanda.py",
        "--everything",
        "--outputdir", outputdir,
        common_flags, "--universal",
        "--osxtarget", osxtarget,
        "--no-gles", "--no-gles2", "--no-egl",
        "--version", Property("version"),
    ]


def get_test_command(abi):
    return [
        "/usr/local/bin/python%s.%s" % (abi[2], abi[3]),
        "-B", "-m", "pytest", "tests",
    ]


def get_makewheel_command(abi, arch):
    return [
        "/usr/local/bin/python%s.%s" % (abi[2], abi[3]),
        "makepanda/makewheel.py",
        "--outputdir", outputdir,
        "--version", whl_version,
        "--platform", Interpolate("macosx-%s-%s", osxtarget, arch),
        "--verbose",
    ]


# The command used to create the .dmg installer.
package_cmd = [
    "python", "makepanda/makepackage.py",
    "--verbose",
    "--version", Property("version"),
    "--outputdir", outputdir,
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        "python", "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),
]

build_steps += whl_version_steps

for abi in ('cp37-cp37m', 'cp36-cp36m', 'cp27-cp27m', 'cp35-cp35m', 'cp34-cp34m'):
    whl_filename32 = get_whl_filename(abi, 'i386')
    whl_filename64 = get_whl_filename(abi, 'x86_64')

    build_steps += [
        # Run makepanda - give it enough timeout (1h)
        Compile(name='compile '+abi, command=get_build_command(abi), timeout=1*60*60,
                env={"MAKEPANDA_THIRDPARTY": "/Users/buildbot/thirdparty",
                     "MAKEPANDA_SDKS": "/Users/buildbot/sdks"}, haltOnFailure=True),

        # Run the test suite.
        Test(name='test '+abi, command=get_test_command(abi),
             env={"PYTHONPATH": outputdir}, haltOnFailure=True),

        # Build two wheels: one for 32-bit, the other for 64-bit.
        # makewheel is clever enough to use "lipo" to extract the right arch.
        ShellCommand(name="makewheel i386 "+abi,
                     command=get_makewheel_command(abi, 'i386'),
                     haltOnFailure=True),

        ShellCommand(name="makewheel x86_64 "+abi,
                     command=get_makewheel_command(abi, 'x86_64'),
                     haltOnFailure=True),

        FileUpload(name="upload i386 "+abi, slavesrc=whl_filename32,
                   masterdest=Interpolate("%s/%s", common.upload_dir, whl_filename32),
                   mode=0o664, haltOnFailure=True),
        FileUpload(name="upload x86_64 "+abi, slavesrc=whl_filename64,
                   masterdest=Interpolate("%s/%s", common.upload_dir, whl_filename64),
                   mode=0o664, haltOnFailure=True),

        # Now delete them.
        ShellCommand(name="rm "+abi, command=['rm', whl_filename32, whl_filename64], haltOnFailure=False),
    ]

# Build and upload the installer.
build_steps += [
    ShellCommand(name="package", command=package_cmd, haltOnFailure=True),

    FileUpload(name="upload dmg", slavesrc=get_dmg_filename(),
               masterdest=get_dmg_upload_filename(),
               mode=0o664, haltOnFailure=True),
]

sdk_factory = BuildFactory()
for step in build_steps:
    sdk_factory.addStep(step)


def macosx_builder():
    return BuilderConfig(name='macosx',
                         slavenames=config.macosx_slaves,
                         factory=sdk_factory,
                         properties={"buildtype": "sdk"})
