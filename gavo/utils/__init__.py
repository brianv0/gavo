"""
Modules external to the data center.

This comprises helpers and wrappers that do not need gavo.base but for some
reason or another should be within the dc package.
"""


from gavo.utils.algotricks import identity, topoSort

from gavo.utils.codetricks import (silence, ensureExpression, compileFunction,
	loadPythonModule)

from gavo.utils.excs import *

from gavo.utils.fitstools import readPrimaryHeaderQuick

from gavo.utils.mathtricks import *

from gavo.utils.ostricks import safeclose

from gavo.utils.stanxml import ElementTree

from gavo.utils.texttricks import (formatSize, makeEllipsis, floatRE, 
	fixIndentation, parsePercentExpression, hmsToDeg, dmsToDeg,
	fracHoursToDeg, degToHms, degToDms, getRelativePath, parseAssignments, 
	NameMap)

