""" Contains renderers and build steps that are useful to more than one
build factory. """

__all__ = ["rtdist_lock", "sse2_flag", "threads_flag", "buildtype_flag",
           "common_flags", "MakeTorrent"]

from buildbot.steps.master import MasterShellCommand
from buildbot.steps.transfer import FileUpload, DirectoryUpload
from buildbot.process.properties import Interpolate, Property, renderer
from buildbot.locks import MasterLock

import config

# Define a lock so that only one builder can update the rtdist at a time.
rtdist_lock = MasterLock('rtdist')

@renderer
def sse2_flag(props):
    "Determines the SSE2 flag based on the requested architecture."

    if "macosx" in props["buildername"]:
        # All Intel Macs have SSE2, I think
        return ["--use-sse2"]

    if props["arch"] == "amd64":
        return ["--use-sse2"]
    else:
        # Let's not use Eigen in 32-bit builds.  It's of questionable value
        # when we don't use SSE2, and it makes the Windows build too slow.
        return ["--no-sse2", "--no-eigen"]

@renderer
def threads_flag(props):
    "Determines the --threads flag to use."

    if props.getProperty("threads", 0) > 1:
        return "--threads=%d" % (props["threads"])
    else:
        return ""

@renderer
def buildtype_flag(props):
    "Determines whether to use --runtime, --rtdist, or neither."

    if "buildtype" in props:
        if props["buildtype"] == "runtime":
            return "--runtime"
        elif props["buildtype"] == "rtdist":
            return "--rtdist"

    return ""

@renderer
def common_flags(props):
    "Returns makepanda flags common to all builders."

    flags = [
        "--verbose",
        "--nocolor",
        sse2_flag.getRenderingFor(props),
        "--distributor=" + config.distributor,
        "--git-commit=" + props["got_revision"],
    ]

    if props.getProperty("threads", 0) > 1:
        flags.append("--threads=%d" % (props["threads"]))

    if props.getProperty("clean"):
        flags.append("--clean")

    buildtype = "sdk"

    if "buildtype" in props:
        buildtype = props["buildtype"] or "sdk"

    if buildtype != "sdk":
        flags.append("--" + buildtype)

    if buildtype == "rtdist":
        flags.append("--host=https://runtime.panda3d.org/")

    elif buildtype == "sdk":
        # Only build the .p3d deployment tools on a branch that's already
        # had a release.  Bit of a hacky way to determine that.
        major_version = '.'.join(props["version"].split('.', 2)[:2])
        if props.getProperty("commit-description", "").startswith('v' + major_version + '.'):
            flags.append("--host=https://runtime.panda3d.org/")

    return flags

@renderer
def rtdist_staging_dir(props):
    "The directory to which the rtdist is uploaded."

    return '%s/%s-%d' % (config.staging_dir, props['buildername'], props['buildnumber'])

# Steps to publish the rtdist.
publish_rtdist_steps = [
    # Upload the stage directory.
    DirectoryUpload(slavesrc="built/stage", masterdest=rtdist_staging_dir,
                    haltOnFailure=True),

    # Run pmerge.
    MasterShellCommand(name="pmerge", command=[
        config.pmerge_bin, "-i", config.runtime_dir, rtdist_staging_dir])
]

def MakeTorrent(filename, **kwargs):
    "Pseudo-class.  This build step creates a torrent on the master."

    return MasterShellCommand(command=[
        "transmission-create",
        "-t", "udp://tracker.publicbt.com:80",
        "-t", "udp://tracker.opentrackr.org:1337/announce",
        "-t", "http://tracker.bittorrent.am/announce",
        "-t", "udp://tracker.sktorrent.net:6969",
        "-o", Interpolate("%s.torrent", filename),
        filename], **kwargs)

def SeedTorrent(filename, **kwargs):
    """Pseudo-class.  This build step adds a torrent on the master.
    Requires a .netrc file to be present on the master containing the
    transmission-remote authentication credentials.
    """

    return MasterShellCommand(command=[
        "transmission-remote",
        "-a", Interpolate("%s.torrent", filename),
        "--find", filename], **kwargs)
