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
from .common import common_flags, buildtype_flag, whl_version_steps, whl_version, publish_rtdist_steps
from .common import MakeTorrent, SeedTorrent

@renderer
def dmg_filename(props):
    "Determines the name of an .dmg file for uploading."

    if "buildtype" in props and props["buildtype"] == "runtime":
        return "p3d-setup.dmg"

    if "python-version" in props and props["python-version"] and not props["python-version"].startswith("2."):
        return "Panda3D-%s-py%s.dmg" % (props["version"], props["python-version"])
    else:
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
        basename = "%s-%s%s" % (prefix, props["version"], suffix)
    else:
        basename = "%s-%s-%s%s" % (prefix, props["version"], props["got_revision"][:7], suffix)

    if "python-version" in props and props["python-version"] and not props["python-version"].startswith("2."):
        basename += "-py%s" % (props["python-version"])

    basename += ".dmg"
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
    #elif "osxtarget" in props and props["osxtarget"] == "10.6":
    #    return "python2.6"
    else:
        return "python2.7"

@renderer
def python_executable(props):
    "Returns the path to the Python executable."

    # We always use the build from python.org at the moment.
    return '/usr/local/bin/' + python_ver.getRenderingFor(props)

@renderer
def whl_filename32(props):
    "Determines the name of a .whl file for uploading."

    pyver = python_ver.getRenderingFor(props)[6:].replace('.', '')
    abi = props["python-abi"]
    osxver = props["osxtarget"].replace('.', '_')
    version = whl_version.getRenderingFor(props)
    return "panda3d-{0}-cp{1}-{2}-macosx_{3}_i386.whl".format(version, pyver, abi, osxver)

@renderer
def whl_filename64(props):
    "Determines the name of a .whl file for uploading."

    pyver = python_ver.getRenderingFor(props)[6:].replace('.', '')
    abi = props["python-abi"]
    osxver = props["osxtarget"].replace('.', '_')
    version = whl_version.getRenderingFor(props)
    return "panda3d-{0}-cp{1}-{2}-macosx_{3}_x86_64.whl".format(version, pyver, abi, osxver)

@renderer
def whl_upload_filename32(props):
    "Determines the upload location of a .whl file on the master."

    return '/'.join((config.downloads_dir,
                     props["got_revision"],
                     whl_filename32.getRenderingFor(props)))

@renderer
def whl_upload_filename64(props):
    "Determines the upload location of a .whl file on the master."

    return '/'.join((config.downloads_dir,
                     props["got_revision"],
                     whl_filename64.getRenderingFor(props)))

@renderer
def outputdir(props):
    if "buildtype" not in props or props["buildtype"] != "runtime":
        pyver = python_ver.getRenderingFor(props)[6:]
        return ['built-py' + pyver]
    else:
        return ['built']

build_cmd = [
    python_executable, "makepanda/makepanda.py",
    "--everything",
    "--outputdir", outputdir,
    common_flags, arch_flags, dist_flags,
    "--osxtarget", Property("osxtarget"),
    "--no-gles", "--no-gles2", "--no-egl",
    "--version", Property("version"),
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        python_executable, "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),

    # Run makepanda - give it enough timeout (1h)
    Compile(command=build_cmd, timeout=1*60*60,
        env={"MAKEPANDA_THIRDPARTY": "/Users/buildbot/thirdparty",
             "MAKEPANDA_SDKS": "/Users/buildbot/sdks",
             "PYTHONPATH": python_path}, haltOnFailure=True),
]

build_publish_whl_steps = whl_version_steps + [
    SetPropertyFromCommand("python-abi", command=[
        python_executable, "-c", "import makewheel;print(makewheel.get_abi_tag())"],
        workdir="build/makepanda", haltOnFailure=True),

    # Build two wheels: one for 32-bit, the other for 64-bit.
    # makewheel is clever enough to use "lipo" to extract the right arch.
    ShellCommand(name="makewheel", command=[
        python_executable, "makepanda/makewheel.py",
        "--outputdir", outputdir,
        "--version", whl_version,
        "--platform", Interpolate("macosx-%(prop:osxtarget)s-i386"),
        "--verbose"], haltOnFailure=True),

    ShellCommand(name="makewheel", command=[
        python_executable, "makepanda/makewheel.py",
        "--outputdir", outputdir,
        "--version", whl_version,
        "--platform", Interpolate("macosx-%(prop:osxtarget)s-x86_64"),
        "--verbose"], haltOnFailure=True),

    FileUpload(slavesrc=whl_filename32, masterdest=whl_upload_filename32,
               mode=0o664, haltOnFailure=True),
    FileUpload(slavesrc=whl_filename64, masterdest=whl_upload_filename64,
               mode=0o664, haltOnFailure=True),
]

publish_dmg_steps = [
    FileUpload(slavesrc=dmg_filename, masterdest=dmg_upload_filename,
               mode=0o664, haltOnFailure=True),

    MakeTorrent(dmg_upload_filename),
    SeedTorrent(dmg_upload_filename),
]

# Now make the factories.
sdk_factory = BuildFactory()
for step in build_steps + build_publish_whl_steps + publish_dmg_steps:
    sdk_factory.addStep(step)

runtime_factory = BuildFactory()
for step in build_steps + publish_dmg_steps:
    runtime_factory.addStep(step)

rtdist_factory = BuildFactory()
#rtdist_factory.addStep(RemoveDirectory(dir="built/stage"))
for step in build_steps + publish_rtdist_steps:
    rtdist_factory.addStep(step)


def macosx_builder(buildtype, osxver):
    if buildtype == "sdk":
        name = '-'.join((buildtype, "macosx" + osxver))
    else:
        name = '-'.join((buildtype, "macosx"))

    if buildtype == "rtdist":
        factory = rtdist_factory
    elif buildtype == "runtime":
        factory = runtime_factory
    else:
        factory = sdk_factory

    return BuilderConfig(name=name,
                         slavenames=config.macosx_slaves,
                         factory=factory,
                         properties={"osxtarget": osxver, "buildtype": buildtype})
