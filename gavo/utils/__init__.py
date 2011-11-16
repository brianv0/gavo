"""
Miscellaneous helper modules for GAVO's python modules.

This comprises helpers and wrappers that do not need gavo.base but for some
reason or another should be within the dc package.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

import os

from gavo.utils.algotricks import (
	chunk, identity, topoSort, commonPrefixLength)

from gavo.utils.autonode import AutoNode

from gavo.utils.codetricks import (silence, ensureExpression, compileFunction,
	loadPythonModule, memoized, identity, runInSandbox, document, 
	buildClassResolver, CachedGetter, intToFunnyWord, IdManagerMixin,
	addDefaults, iterDerivedClasses, iterDerivedObjects, iterConsecutivePairs,
	importModule, loadInternalObject, printFrames, memoizeOn, sandbox,
	in_dir, memoizedMethod, getTracebackAsString)

from gavo.utils.excs import *

# We reliably want the numpy version of pyfits.  Thus, always use
# from gavo.utils import pyfits rather than a direct import;  the
# "master import" is in fitstools, and we get pyfits from there.

from gavo.utils.fitstools import readPrimaryHeaderQuick, pyfits

from gavo.utils.mathtricks import *

from gavo.utils.misctricks import (Undefined, QuotedName, getfirst,
	logOldExc, sendUIEvent, pyparsingWhitechars, getWithCache)

from gavo.utils.ostricks import (safeclose, urlopenRemote, 
	fgetmtime, cat, ensureDir)

from gavo.utils.plainxml import StartEndHandler, iterparse

from gavo.utils.stanxml import ElementTree, xmlrender

from gavo.utils.texttricks import (formatSize, makeEllipsis, floatRE, 
	dateRE, datetimeRE, identifierPattern,
	datetimeToRFC2616, 
	isoTimestampFmt, isoTimestampFmtNoTZ, parseISODT, formatISODT,
	formatRFC2616Date, parseRFC2616Date,
	fixIndentation, parsePercentExpression, hmsToDeg, dmsToDeg,
	fracHoursToDeg, degToHms, degToDms, getRelativePath, parseAssignments, 
	NameMap, formatSimpleTable, replaceXMLEntityRefs,
	ensureOneSlash,)
