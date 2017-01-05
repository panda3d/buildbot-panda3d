__all__ = ["windows_builder"]

from buildbot.process.properties import Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, SetPropertyFromCommand
from buildbot.steps.transfer import FileUpload
from buildbot.steps.slave import RemoveDirectory
from buildbot.config import BuilderConfig

import config
from .common import common_flags, buildtype_flag, whl_version_steps, whl_version, whl_filename, whl_upload_filename, publish_rtdist_steps
from .common import MakeTorrent, SeedTorrent

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
def pdb_filename(props):
    "Determines the name of an -pdb.zip file for uploading."

    if props["arch"] == "amd64":
        suffix = "-x64"
    else:
        suffix = ""

    if "python-version" in props and props["python-version"] and props["python-version"] != "2.7":
        suffix = "-py" + props["python-version"] + suffix

    return "Panda3D-%s%s-pdb.zip" % (props["version"], suffix)

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
def pdb_upload_filename(props):
    "Determines the upload location of a -pdb.zip file on the master."

    if props["arch"] == "amd64":
        suffix = "-x64"
    else:
        suffix = ""

    if "python-version" in props and props["python-version"]:
        suffix = "-py" + props["python-version"] + suffix

    if props["revision"].startswith("v"):
        basename = "Panda3D-SDK-%s%s-pdb.zip" % (props["version"], suffix)
    #elif "commit-description" in props:
    #    basename = "Panda3D-SDK-%s%s-pdb.zip" % (props["commit-description"][1:], suffix)
    else:
        basename = "Panda3D-SDK-%spre-%s%s-pdb.zip" % (props["version"], props["got_revision"][:7], suffix)

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
    elif "buildtype" in props and props["buildtype"] == "runtime":
        return ["--installer", "--lzma"]
    else:
        return ["--installer", "--lzma", "--wheel"]

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
    "--version", whl_version,
]

checkout_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        python_executable, "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),
]

whl_steps = [
    SetPropertyFromCommand("python-abi", command=[
        python_executable, "-c", "import makewheel;print(makewheel.get_abi_tag())"],
        workdir="build/makepanda", haltOnFailure=True),
] + whl_version_steps

build_steps = [
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

publish_sdk_steps = [
    # Upload the wheel.
    FileUpload(slavesrc=whl_filename, masterdest=whl_upload_filename,
               mode=0o664, haltOnFailure=True),

    # Upload the pdb zip file.
    FileUpload(slavesrc=pdb_filename, masterdest=pdb_upload_filename,
               mode=0o664, haltOnFailure=False),
] + publish_exe_steps

# Now make the factories.
sdk_factory = BuildFactory()
for step in checkout_steps + whl_steps + build_steps + publish_sdk_steps:
    sdk_factory.addStep(step)

runtime_factory = BuildFactory()
for step in checkout_steps + build_steps + publish_exe_steps:
    runtime_factory.addStep(step)

rtdist_factory = BuildFactory()
rtdist_factory.addStep(RemoveDirectory(dir="built/slave"))
for step in checkout_steps + build_steps + publish_rtdist_steps:
    rtdist_factory.addStep(step)


def windows_builder(buildtype, arch):
    if buildtype == "rtdist":
        factory = rtdist_factory
    elif buildtype == "runtime":
        factory = runtime_factory
    else:
        factory = sdk_factory

    if arch == "amd64":
        platform = "win_amd64"
    else:
        platform = "win32"

    return BuilderConfig(name='-'.join((buildtype, "windows", arch)),
                         slavenames=config.windows_slaves,
                         factory=factory,
                         properties={"buildtype": buildtype, "arch": arch, "platform": platform})
