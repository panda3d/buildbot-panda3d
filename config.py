# This file collects various global configuration variables.

import json
from buildbot.buildslave import BuildSlave

# Will be passed to every build with --distributor argument to makepanda.
distributor = "cmu"

# URL where the source code is hosted.
git_url = "git://github.com/panda3d/panda3d.git"

# Link to the Panda3D project.
title_url = "https://www.panda3d.org/"

# Link to the buildbot status page.
buildbot_url = "https://buildbot.panda3d.org/"

# Link to webhook.
webhook_url = "https://www.panda3d.org/webhooks/buildbot.php"

# Location on the server where the builds are to be uploaded.
downloads_dir = "/srv/www/html/buildbot.panda3d.org/downloads"

# Location where the .deb archives are hosted in an apt repository.
archive_dir = "/srv/www/html/archive.panda3d.org"

# Where the rtdist builds are uploaded before being pmerged.
staging_dir = "/home/panda3d-bot/staging-tmp"

# Location on the server into which the rtdist packages should be merged.
runtime_dir = "/srv/www/html/runtime-dev.panda3d.org"

# Location of a copy of pmerge that can be run on the master.
pmerge_bin = "/srv/www/html/runtime.panda3d.org/pmerge.p3d"

# IRC settings
irc_host = "irc.freenode.net"
irc_nick = "p3dbuildbot"
irc_channels = ["#panda3d-devel"]

# Files that, when changed, should not trigger an automatic SDK rebuild.
# Paths starting with a forward slash are relative to the filesystem root.
sdk_excludes = [
    ".gitignore",
    "/.travis.yml",
    "/LICENSE",
    "README",
    "README.*",
    "BACKERS.*",
    "*.pl",
    "*.vcproj",
    "*.sln",
    "*.pdef",
    "*.xcf",
    "*.tau",
    "*.sh",
    "*.prebuilt",
    "*.bat",
    "PACKAGE-DESC",
    "/doc/ReleaseNotes",
    "/doc/InstallerNotes",
    "/doc/INSTALL",
    "/doc/INSTALLING-PLUGINS.TXT",
    "/direct/src/plugin/*",
    "/direct/src/plugin_activex/*",
    "/direct/src/plugin_installer/*",
    "/direct/src/plugin_npapi/*",
    "/direct/src/plugin_standalone/*",
    "/direct/src/doc/*",
    "/panda/src/cftalk/*",
    "/panda/src/doc/*",
    "/panda/src/android/*",
    "/panda/src/androiddisplay/*",
    "/panda/src/awesomium/*",
    "/panda/src/skel/*",
]

# List of slave names for each platform.
linux_slaves = ["build-lnx"]
windows_slaves = ["build-win3"]
macosx_10_6_slaves = ["build-osx"]
macosx_10_9_slaves = ["build-osx-2"]

# These files contain metadata (incl. passwords) of the slaves and users.
slaves_fn = "slaves.json"
users_fn = "users.json"

# Load the slaves from an external JSON file, since we don't want
# the slave passwords to become publicly visible.
slaves = []
for slave_spec in json.load(open(slaves_fn, 'r')):
    slaves.append(BuildSlave(**slave_spec))

# Do the same for the user accounts of the web interface.
users = []
for user_spec in json.load(open(users_fn, 'r')):
    users.append((str(user_spec[0]), str(user_spec[1])))


from fnmatch import fnmatchcase

def _matches(file, pattern):
    file = file.lstrip('/')
    if pattern.startswith('/'):
        return fnmatchcase(file, pattern[1:])

    # Relative pattern.  Recurse through the hierarchy to see if it matches.
    while file:
        if fnmatchcase(file, pattern):
            return True
        file = file.partition('/')[2]

    return False

def is_important(change):
    if '[ci skip]' in change.comments or '[skip ci]' in change.comments:
        return False

    for file in change.files:
        if not any(_matches(file, pattern) for pattern in sdk_excludes):
            return True

    return False
