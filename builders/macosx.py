__all__ = ["macosx_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileUpload
from buildbot.steps.master import MasterShellCommand
from buildbot.steps.slave import RemoveDirectory
from buildbot.config import BuilderConfig

import config
from .common import common_flags, buildtype_flag, publish_rtdist_steps, MakeTorrent, SeedTorrent

@renderer
def dmg_filename(props):
    "Determines the name of an .dmg file for uploading."

    if "buildtype" in props and props["buildtype"] == "runtime":
        return "p3d-setup.dmg"

    return "Panda3D-%s.dmg" % (props["version"])

@renderer
def dmg_upload_filename(props):
    "Determines the upload location of an .dmg file on the master."

    if "buildtype" in props and props["buildtype"] == "runtime":
        prefix = "Panda3D-Runtime"
        suffix = ""
    else:
        prefix = "Panda3D-SDK"
        suffix = "-MacOSX" + props["osxtarget"]

    if props["revision"].startswith("v"):
        basename = "%s-%s%s.dmg" % (prefix, props["version"], suffix)
    else:
        basename = "%s-%s-%s%s.dmg" % (prefix, props["version"], props["got_revision"][:7], suffix)

    return '/'.join((config.downloads_dir, props["got_revision"], basename))

@renderer
def arch_flags(props):
    "Returns the appropriate arch flags to use depending on build type."

    if "buildtype" in props and props["buildtype"] == "runtime":
        return "--arch=i386"
    else:
        return "--universal"

@renderer
def dist_flags(props):
    if "buildtype" in props and props["buildtype"] == "rtdist":
        return []
    else:
        return ["--installer"]

@renderer
def python_path(props):
    if "buildtype" in props and props["buildtype"] == "rtdist":
        return "/Users/buildbot/thirdparty/darwin-libs-a/rocket/lib/python2.7"
    else:
        return ""

@renderer
def python_ver(props):
    if "python-version" in props and props["python-version"]:
        return "python" + props["python-version"]
    elif "buildtype" in props and props["buildtype"] == "rtdist":
        return "python2.7"
    elif "osxtarget" in props and props["osxtarget"] == "10.6":
        return "python2.6"
    else:
        return "python2.7"

build_cmd = [
    python_ver, "makepanda/makepanda.py",
    "--everything",
    "--outputdir", "built",
    common_flags, arch_flags, dist_flags,
    "--osxtarget", Property("osxtarget"),
    "--no-gles", "--no-gles2", "--no-egl",
    "--version", Property("version"),
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        "python", "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),

    # Run makepanda - give it enough timeout (1h)
    Compile(command=build_cmd, timeout=1*60*60,
        env={"MAKEPANDA_THIRDPARTY": "/Users/buildbot/thirdparty",
             "MAKEPANDA_SDKS": "/Users/buildbot/sdks",
             "PYTHONPATH": python_path}, haltOnFailure=True),
]

publish_dmg_steps = [
    FileUpload(slavesrc=dmg_filename, masterdest=dmg_upload_filename,
               mode=0o664, haltOnFailure=True),

    MakeTorrent(dmg_upload_filename),
    SeedTorrent(dmg_upload_filename),
]

# Now make the factories.
dmg_factory = BuildFactory()
for step in build_steps + publish_dmg_steps:
    dmg_factory.addStep(step)

rtdist_factory = BuildFactory()
rtdist_factory.addStep(RemoveDirectory(dir="built/slave"))
for step in build_steps + publish_rtdist_steps:
    rtdist_factory.addStep(step)


def macosx_builder(buildtype, osxver):
    if buildtype == "sdk":
        name = '-'.join((buildtype, "macosx" + osxver))
    else:
        name = '-'.join((buildtype, "macosx"))
    factory = rtdist_factory if buildtype == "rtdist" else dmg_factory
    return BuilderConfig(name=name,
                         slavenames=config.macosx_slaves,
                         factory=factory,
                         properties={"osxtarget": osxver, "buildtype": buildtype})
