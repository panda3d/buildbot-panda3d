"""
This file controls the builders for Linux distributions, via Docker.
It is intended to replace the schroot-based approach in debian.py.

All Linux builders can run on a single slave via the use of docker,
which manages Linux containers for various Linux distributions.

To set up a distribution, it uses a special Dockerfile which describes
how to set it up.  It also contains the package installation commands.

Since the coreapi needs to be linked with static versions of OpenSSL and
ZLib that were compiled with -fpic, I've compiled those separately into
a special directory.
"""

__all__ = ["docker_builder"]

from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.process.factory import BuildFactory
from buildbot.steps.source.git import Git
from buildbot.steps.shell import Compile, Test, SetPropertyFromCommand, ShellCommand
from buildbot.steps.transfer import FileDownload, FileUpload
from buildbot.steps.master import MasterShellCommand
from buildbot.steps.slave import RemoveDirectory
from buildbot.config import BuilderConfig
from buildbot.locks import MasterLock

from datetime import date
import os.path

import config
from .common import common_flags, buildtype_flag, whl_version_steps, publish_rtdist_steps, MakeTorrent, SeedTorrent, is_branch

@renderer
def upstream_version(props):
    "Determine which version string a .deb package should have."

    if props["revision"] == "v" + props["version"]:
        # We requested building a particular version tag, so this must be a
        # release.
        return props["version"]

    version = tuple(map(int, props["version"].split('.')))

    # Was this commit branched off from the main branch?
    local = ""
    if props["merge-base"] != props["got_revision"] and not props["branch"].startswith("release/"):
        # Add a local tag indicating that this has unofficial changes.
        local += "+g" + props["got_revision"][:7]

    # Is this a post-release build?  Check using the output of "git describe",
    # which contains the last release tag plus the number of commits since it.
    if "commit-description" in props:
        desc = props["commit-description"].split('-')

        if desc[0] == "v{0}.{1}.{2}".format(*version):
            if len(desc) == 1:
                # This is exactly this release.
                return props["version"]
            else:
                # This is a post-release.
                return "{0}+post{1}{2}".format(props["version"], desc[1], local)

    # No, it's a pre-release.  Make a version tag based on the number of
    # commits since the last major release.
    return "{0}~dev{1}{2}".format(props["version"], props["commit-index"], local)

@renderer
def debian_version(props):
    "Determine which version string a .deb package should have."

    debver = upstream_version.getRenderingFor(props)
    return debver + "~" + props["suite"]

@renderer
def deb_filename(props):
    "Determines the name of a .deb file for uploading."

    debver = debian_version.getRenderingFor(props)

    if "buildtype" in props and props["buildtype"] == "runtime":
        pkg_name = "panda3d-runtime"
    else:
        major_version = '.'.join(props["version"].split('.', 2)[:2])
        pkg_name = "panda3d" + major_version

    return "%s_%s_%s.deb" % (pkg_name, debver, props["arch"])

@renderer
def deb_upload_filename(props):
    "Determines the upload location of a .deb file on the master."

    return '/'.join((config.downloads_dir,
                     props["got_revision"],
                     deb_filename.getRenderingFor(props)))

@renderer
def deb_archive_dir(props):
    "Returns the directory in which the deb files should be placed."

    return '/'.join((config.archive_dir, props["distro"]))

@renderer
def deb_archive_suite(props):
    "Returns the suite to which the deb files should be uploaded."

    return props['suite'] + '-dev'

@renderer
def dist_flags(props):
    # I don't like that we have to do this, but p3d_plugin.so must link
    # with static versions of OpenSSL and ZLib.
    if "buildtype" in props and props["buildtype"] == "rtdist":
        arch = props['arch']
        return [
            "--openssl-incdir=/home/buildbot/rtdist_ssl_%s/include" % arch,
            "--openssl-libdir=/home/buildbot/rtdist_ssl_%s/lib" % arch,
            "--rocket-incdir=/home/buildbot/rtdist_rocket/include",
            "--rocket-libdir=/home/buildbot/rtdist_rocket/lib_%s" % arch,
            "--fltk-incdir=/home/buildbot/rtdist_fltk/include",
            "--fltk-libdir=/home/buildbot/rtdist_fltk/lib_%s" % arch,
            "--zlib-incdir=/home/buildbot/rtdist_zlib/include",
            "--zlib-libdir=/home/buildbot/rtdist_zlib/lib_%s" % arch]
    else:
        # The other builds link against the regular system version.
        return ["--installer"]

@renderer
def python_path(props):
    # Temporary hack
    if "buildtype" in props and props["buildtype"] == "rtdist":
        arch = props['arch']
        return "/home/buildbot/rtdist_rocket/lib_%s/python2.7" % arch
    return ""

@renderer
def setarch(props):
    if "arch" in props and props["arch"] != "amd64":
        return ["/usr/bin/setarch", props["arch"]]
    else:
        return []

cloudimg_cmd = Interpolate("wget -N https://partner-images.canonical.com/core/%(prop:suite)s/current/ubuntu-%(prop:suite)s-core-cloudimg-%(prop:arch)s-root.tar.gz || wget -N https://partner-images.canonical.com/core/unsupported/%(prop:suite)s/current/ubuntu-%(prop:suite)s-core-cloudimg-%(prop:arch)s-root.tar.gz")

# The command to set up the Docker image.
setup_cmd = [
    "docker", "build", "-t",
    Interpolate("%(prop:suite)s-%(prop:arch)s"),
    "."
]

# The command used to compile Panda3D from source.
build_cmd = [
    "docker", "run", "--rm=true",
    "-i", Interpolate("--name=%(prop:buildername)s"),
    "-v", Interpolate("%(prop:workdir)s/build/:/build/:rw"),
    "-w", "/build/",
    Interpolate("%(prop:suite)s-%(prop:arch)s"),

    setarch,
    "/usr/bin/python", "makepanda/makepanda.py",
    "--everything",
    "--no-gles", "--no-gles2", "--no-egl",
    common_flags, dist_flags,
    "--debversion", debian_version,
    "--version", Property("version"),
    "--outputdir", "built",
]

# The command used to run the test suite.
test_cmd = [
    "docker", "run", "--rm=true",
    "-i", Interpolate("--name=%(prop:buildername)s"),
    "-v", Interpolate("%(prop:workdir)s/build/:/build/:rw"),
    "-w", "/build/",
    "-e", "PYTHONPATH=/build/built",
    "-e", "LD_LIBRARY_PATH=/build/built/lib",
    Interpolate("%(prop:suite)s-%(prop:arch)s"),

    setarch,
    "/usr/bin/python", "-m", "pytest", "tests",
]

# The command used to run the deploy-ng tests.
test_deployng_cmd = [
    "docker", "run", "--rm=true",
    "-i", Interpolate("--name=%(prop:buildername)s"),
    "-v", Interpolate("%(prop:workdir)s/build/:/build/:rw"),
    "-w", "/build/",
    "-e", "PYTHONPATH=/build/built",
    "-e", "LD_LIBRARY_PATH=/build/built/lib",
    "-e", "PATH=/build/built/bin",
    Interpolate("%(prop:suite)s-%(prop:arch)s"),

    setarch,
    "/usr/bin/python", "tests/build_samples.py"
]

changelog_msg = Interpolate("Automatic build %(prop:buildnumber)s by builder %(prop:buildername)s")

# Build steps shared by all builders.
build_steps = [
    Git(config.git_url, getDescription={'match': 'v*'}),

    # Decode the version number from the dtool/PandaVersion.pp file.
    SetPropertyFromCommand("version", command=[
        "python", "makepanda/getversion.py", buildtype_flag],
        haltOnFailure=True),

    # These steps fill in properties used to determine upstream_version.
    ] + whl_version_steps + [

    # Download the Dockerfile for this distribution.
    FileDownload(mastersrc=Interpolate("dockerfiles/%(prop:suite)s-%(prop:arch)s"), slavedest="Dockerfile", workdir="context"),

    # Make sure the base distribution is up-to-date.
    ShellCommand(command=cloudimg_cmd, workdir="context"),

    # Build the Docker image.
    ShellCommand(name="setup", command=setup_cmd, workdir="context", haltOnFailure=True),

    # Invoke makepanda.
    Compile(command=build_cmd, haltOnFailure=True, env={'PYTHONPATH': python_path}),

    # Run the test suite.
    Test(command=test_cmd, haltOnFailure=True),

    # And the test scripts for deploy-ng.
    Test(name="build_samples", command=test_deployng_cmd, doStepIf=is_branch("deploy-ng"), haltOnFailure=True),
]

# Define a global lock, since reprepro won't allow simultaneous access to the repo.
repo_lock = MasterLock('reprepro')

# Steps to publish the runtime and SDK.
publish_deb_steps = [
    # Upload the deb package.
    FileUpload(slavesrc=deb_filename, masterdest=deb_upload_filename,
               mode=0o664, haltOnFailure=True),

    # Create a torrent file and start seeding it.
    MakeTorrent(deb_upload_filename),
    SeedTorrent(deb_upload_filename),

    # Upload it to an apt repository.
    MasterShellCommand(name="reprepro", command=[
        "reprepro", "-b", deb_archive_dir, "includedeb", deb_archive_suite,
        deb_upload_filename], locks=[repo_lock.access('exclusive')]),
]

# Now make the factories.
deb_factory = BuildFactory()
for step in build_steps + publish_deb_steps:
    deb_factory.addStep(step)


def docker_builder(buildtype, distro, suite, arch):
    return BuilderConfig(name='-'.join((buildtype, suite, arch)),
                         slavenames=config.linux_slaves,
                         factory=deb_factory,
                         properties={"buildtype": buildtype, "distro": distro, "suite": suite, "arch": arch})
