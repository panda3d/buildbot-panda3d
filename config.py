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
buildbot_url = "http://buildbot.panda3d.org/"

# Location on the server where the builds are to be uploaded.
downloads_dir = "/var/www/html/buildbot.panda3d.org/downloads"

# Location where the .deb archives are hosted in an apt repository.
archive_dir = "/var/www/html/archive.panda3d.org"

# Where the rtdist builds are uploaded before being pmerged.
staging_dir = "/home/panda3d-bot/staging-tmp"

# Location on the server into which the rtdist packages should be merged.
runtime_dir = "/var/www/html/runtime-dev.panda3d.org"

# Location of a copy of pmerge that can be run on the master.
pmerge_bin = "/var/www/html/runtime.panda3d.org/pmerge.p3d"

# List of slave names for each platform.
linux_slaves = ["build-lnx"]
windows_slaves = ["build-win"]
macosx_slaves = ["build-osx"]

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
