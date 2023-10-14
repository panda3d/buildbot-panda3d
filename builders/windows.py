__all__ = ["windows_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, Test, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileUpload
from buildbot.steps.worker import RemoveDirectory
from buildbot.config import BuilderConfig

import config
from .common import common_flags, buildtype_flag, whl_version_steps, whl_version, get_whl_filename, publish_rtdist_steps, is_branch
from .common import MakeTorrent, SeedTorrent
from . import common


@renderer
def arch_suffix(props):
    if props["arch"] == "amd64":
        return "-x64"
    else:
        return ""


def get_exe_filename(abi=None):
    "Determines the name of an .exe file for uploading."

    suffix = ""
    if abi and not abi.startswith('cp27-'):
        suffix = "-py%s.%s" % (abi[2], abi[3:].split('-')[0])

    return Interpolate("Panda3D-%s%s%s.exe", Property("version"), suffix, arch_suffix)


def get_pdb_filename(abi=None):
    "Determines the name of an -pdb.zip file for uploading."

    suffix = ""
    if abi and not abi.startswith('cp27-'):
        suffix = "-py%s.%s" % (abi[2], abi[3:].split('-')[0])

    return Interpolate("Panda3D-%s%s%s-pdb.zip", Property("version"), suffix, arch_suffix)


@renderer
def exe_version(props):
    if props["revision"].startswith("v"):
        return props["version"]
    else:
        return "%spre-%s" % (props["version"], props["got_revision"][:7])


def get_exe_upload_filename(abi=None):
    "Determines the upload location of an .exe file on the master."

    suffix = ""
    if abi and not abi.startswith('cp27-'):
        suffix = "-py%s.%s" % (abi[2], abi[3:].split('-')[0])

    return Interpolate("%s/Panda3D-SDK-%s%s%s.exe",
        common.upload_dir, exe_version, suffix, arch_suffix)


def get_pdb_upload_filename(abi=None):
    "Determines the upload location of a -pdb.zip file on the master."

    suffix = ""
    if abi and not abi.startswith('cp27-'):
        suffix = "-py%s.%s" % (abi[2], abi[3:].split('-')[0])

    return Interpolate("%s/Panda3D-SDK-%s%s%s-pdb.zip",
        common.upload_dir, exe_version, suffix, arch_suffix)


def get_python_executable(abi):
    "Determines the location of python.exe."

    if abi == "cp27-cp27m":
        return Interpolate("C:\\thirdparty\\win-python%s\\python.exe", arch_suffix)
    else:
        return Interpolate("C:\\thirdparty\\win-python%s.%s%s\\python.exe", abi[2], abi[3:].split('-')[0], arch_suffix)


@renderer
def outputdir(props):
    version = props["version"].split('.')
    dir = 'built{0}.{1}'.format(*version)

    if props.getProperty("optimize", False):
        dir += '-opt'

    return [dir]


@renderer
def outputdir_cp34(props):
    version = props["version"].split('.')
    dir = 'built{0}.{1}-cp34'.format(*version)

    if props.getProperty("optimize", False):
        dir += '-opt'

    return [dir]


def get_build_command(abi, copy_python=False):
    command = [
        get_python_executable(abi),
        "makepanda\\makepanda.py",
        "--everything",
        "--outputdir", outputdir,
        "--no-touchinput",
        common_flags,
        "--arch", Property("arch"),
        "--version", whl_version,
        "--wheel",
    ]
    if abi == 'cp34-cp34m':
        command += ["--outputdir", outputdir_cp34]
    else:
        command += ["--outputdir", outputdir]

    if not copy_python:
        command += ["--no-copy-python"]
    return command


def get_test_command(abi, whl_filename):
    return [
        get_python_executable(abi),
        "makepanda\\test_wheel.py",
        "--verbose",
        whl_filename,
    ]


# The command used to create the .exe installer.
package_cmd = [
    # It doesn't matter what Python version we call this with.
    get_python_executable("cp37-cp37m"),
    "makepanda\\makepackage.py",
    "--verbose", "--lzma",
    "--version", Property("version"),
    "--outputdir", outputdir,
]

build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        get_python_executable("cp37-cp37m"),
        "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),

    # Delete the built dir, if requested.
    ShellCommand(name="clean",
                 command=["rmdir", "/S", "/Q", outputdir, outputdir_cp34],
                 haltOnFailure=False, flunkOnFailure=False, warnOnFailure=False,
                 flunkOnWarnings=False, warnOnWarnings=False,
                 doStepIf=lambda step:step.getProperty("clean", False)),
]

build_steps += whl_version_steps

for abi in ('cp312-cp312', 'cp311-cp311', 'cp310-cp310', 'cp39-cp39', 'cp38-cp38', 'cp37-cp37m', 'cp36-cp36m', 'cp27-cp27m', 'cp34-cp34m', 'cp35-cp35m'):
    whl_filename = get_whl_filename(abi)
    copy_python = (abi == 'cp37-cp37m')

    do_step = True
    if abi in ('cp27-cp27m', 'cp34-cp34m', 'cp35-cp35m', 'cp36-cp36m', 'cp37-cp37m'):
        do_step = is_branch('release/1.10.x')

    build_steps += [
        # Run makepanda. Give it enough timeout (6h) since some steps take ages
        Compile(name="compile "+abi, timeout=6*60*60,
                command=get_build_command(abi, copy_python=copy_python),
                env={"MAKEPANDA_THIRDPARTY": "C:\\thirdparty",
                     "MAKEPANDA_SDKS": "C:\\sdks",
                     "SOURCE_DATE_EPOCH": Property("commit-timestamp"),
                     "PYTHONHASHSEED": "0"},
                haltOnFailure=True, doStepIf=do_step),

        # Run the test suite, but in a virtualenv.
        Test(name="test "+abi,
             command=get_test_command(abi, whl_filename),
             haltOnFailure=True, doStepIf=do_step),

        # Upload the wheel.
        FileUpload(name="upload whl "+abi, workersrc=whl_filename,
                   masterdest=Interpolate("%s/%s", common.upload_dir, whl_filename),
                   mode=0o664, haltOnFailure=True, doStepIf=do_step),

        # Clean up the created files.
        ShellCommand(name="del "+abi,
                     command=["del", "/Q", whl_filename],
                     haltOnFailure=False, doStepIf=do_step),
    ]

# Build and upload the installer.
build_steps += [
    ShellCommand(name="package", command=package_cmd,
                 env={"MAKEPANDA_THIRDPARTY": "C:\\thirdparty",
                      "SOURCE_DATE_EPOCH": Property("commit-timestamp"),
                      "PYTHONHASHSEED": "0"},
                 haltOnFailure=True),

    FileUpload(name="upload exe", workersrc=get_exe_filename(),
               masterdest=get_exe_upload_filename(),
               mode=0o664, haltOnFailure=True),

    FileUpload(name="upload pdb", workersrc=get_pdb_filename(),
               masterdest=get_pdb_upload_filename(),
               mode=0o664, haltOnFailure=True),
]

# Now make the factories.
sdk_factory = BuildFactory()
for step in build_steps:
    sdk_factory.addStep(step)


def windows_builder(arch):
    if arch == "amd64":
        platform = "win_amd64"
    else:
        platform = "win32"

    return BuilderConfig(name='-'.join(("sdk", "windows", arch)),
                         workernames=config.windows_workers,
                         factory=sdk_factory,
                         properties={"buildtype": "sdk", "arch": arch, "platform": platform})
