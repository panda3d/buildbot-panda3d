# The 'slaves' list defines the set of recognized buildslaves. Each element is
# a BuildSlave object, specifying a unique slave name and password.  The same
# slave name and password must be configured on the slave.
__all__ = ['slaves']

from buildbot.buildslave import BuildSlave
import json

def read_slaves(fn):
    """ Reads buildslave information from a JSON file. """
    slaves = []

    data = json.load(open(fn, 'r'))
    for slave_data in data:
        slaves.append(BuildSlave(**slave_data))

    return slaves

slaves = read_slaves("slaves.json")
