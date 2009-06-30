"""
Modules external to the data center.

This comprises helpers and wrappers that do not need gavo.base but for some
reason or another should be within the dc package.
"""

import os

from gavo.utils.algotricks import identity, topoSort

from gavo.utils.codetricks import (silence, ensureExpression, compileFunction,
	loadPythonModule, memoized, identity, runInSandbox)

from gavo.utils.excs import *


# We reliably want the numarray version of pyfits.  Thus, always use
# from gavo.utils import pyfits rather than a direct import;  the
# "master import" is in fitstools, and we get pyfits from there.

from gavo.utils.fitstools import readPrimaryHeaderQuick, pyfits

from gavo.utils.mathtricks import *

from gavo.utils.ostricks import safeclose, urlopenRemote

from gavo.utils.stanxml import ElementTree

from gavo.utils.texttricks import (formatSize, makeEllipsis, floatRE, 
	fixIndentation, parsePercentExpression, hmsToDeg, dmsToDeg,
	fracHoursToDeg, degToHms, degToDms, getRelativePath, parseAssignments, 
	NameMap)
