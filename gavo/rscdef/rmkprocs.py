"""
A namespace and registry for predefined rowmaker procs.

These are defined in __system__/procs and are pulled in using getRD
when importing rscdesc.
"""


import re

from gavo import base


_procRegistry = {}


def registerProcedure(name, procOb):
	_procRegistry[name] = procOb
	

def getProcedure(name):
	try:
		return _procRegistry[name]
	except KeyError:
		raise base.LiteralParseError("No such predefined procedure: %s"%
			name, "predefined", name)

