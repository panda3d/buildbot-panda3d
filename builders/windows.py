__all__ = ["windows_builder"]

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
def exe_filename(props):
    "Determines the name of an .exe file for uploading."

    if props["arch"] == "amd64":
        suffix = "-x64"
    else:
        suffix = ""

    if "python-version" in props and props["python-version"] and props["python-version"] != "2.7":
        suffix = "-py" + props["python-version"] + suffix

    if "buildtype" in props and props["buildtype"] == "runtime":
        prefix = "Panda3D-Runtime"
    else:
        prefix = "Panda3D"

    return "%s-%s%s.exe" % (prefix, props["version"], suffix)

@renderer
def exe_upload_filename(props):
    "Determines the upload location of an .exe file on the master."

    if props["arch"] == "amd64":
        suffix = "-x64"
    else:
        suffix = ""

    if "python-version" in props and props["python-version"]:
        suffix = "-py" + props["python-version"] + suffix

    if "buildtype" in props and props["buildtype"] == "runtime":
        prefix = "Panda3D-Runtime"
    else:
        prefix = "Panda3D-SDK"

    if props["revision"].startswith("v"):
        basename = "%s-%s%s.exe" % (prefix, props["version"], suffix)
    #elif "commit-description" in props:
    #    basename = "%s-%s%s.exe" % (prefix, props["commit-description"][1:], suffix)
    else:
        basename = "%s-%spre-%s%s.exe" % (prefix, props["version"], props["got_revision"][:7], suffix)

    return '/'.join((config.downloads_dir, props["got_revision"], basename))

@renderer
def python_executable(props):
    "Determines the location of python.exe on the slave."

    if props["arch"] == "amd64":
        suffix = "-x64"
    else:
        suffix = ""

    if "buildtype" in props and props["buildtype"] == "rtdist":
        return 'C:\\Python27%s\\python.exe' % (suffix)
    elif "python-version" in props:
        return 'C:\\thirdparty\\win-python%s%s\\python.exe' % (props["python-version"], suffix)
    else:
        return 'C:\\thirdparty\\win-python%s\\python.exe' % (suffix)

@renderer
def dist_flags(props):
    if "buildtype" in props and props["buildtype"] == "rtdist":
        return []
    else:
        return ["--installer", "--lzma"]

@renderer
def outputdir(props):
    if "python-version" in props and props["python-version"] and props["python-version"] != '2.7':
        return ['built-py' + props["python-version"]]
    else:
        return ['built']

build_cmd = [
    python_executable,
    "makepanda\\makepanda.py",
    "--everything",
    "--outputdir=built",
    "--no-touchinput",
    common_flags, dist_flags,
    "--outputdir", outputdir,
    "--arch", Property("arch"),
    "--version", Property("version"),
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        python_executable, "makepanda\\getversion.py", buildtype_flag],
        haltOnFailure=True),

    # Run makepanda - give it enough timeout (6h) since some steps take ages
    Compile(command=build_cmd, timeout=6*60*60,
        env={"MAKEPANDA_THIRDPARTY": "C:\\thirdparty",
             "MAKEPANDA_SDKS": "C:\\sdks"}, haltOnFailure=True),
]

publish_exe_steps = [
    FileUpload(slavesrc=exe_filename, masterdest=exe_upload_filename,
               mode=0o664, haltOnFailure=True),

    MakeTorrent(exe_upload_filename),
    SeedTorrent(exe_upload_filename),
]

# Now make the factories.
exe_factory = BuildFactory()
for step in build_steps + publish_exe_steps:
    exe_factory.addStep(step)

rtdist_factory = BuildFactory()
rtdist_factory.addStep(RemoveDirectory(dir="built/slave"))
for step in build_steps + publish_rtdist_steps:
    rtdist_factory.addStep(step)


def windows_builder(buildtype, arch):
    factory = rtdist_factory if buildtype == "rtdist" else exe_factory
    return BuilderConfig(name='-'.join((buildtype, "windows", arch)),
                         slavenames=config.windows_slaves,
                         factory=factory,
                         properties={"buildtype": buildtype, "arch": arch})
