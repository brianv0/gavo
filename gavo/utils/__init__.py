"""
Modules external to the data center.

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
	addDefaults, iterDerivedClasses)

from gavo.utils.excs import *

# We reliably want the numpy version of pyfits.  Thus, always use
# from gavo.utils import pyfits rather than a direct import;  the
# "master import" is in fitstools, and we get pyfits from there.

from gavo.utils.fitstools import readPrimaryHeaderQuick, pyfits

from gavo.utils.mathtricks import *

from gavo.utils.misctricks import Undefined, QuotedName, getfirst

from gavo.utils.ostricks import safeclose, urlopenRemote, fgetmtime, cat

from gavo.utils.plainxml import StartEndHandler

from gavo.utils.stanxml import FastElementTree, ElementTree, xmlrender

from gavo.utils.texttricks import (formatSize, makeEllipsis, floatRE, 
	dateRE, datetimeRE, identifierRE,
	datetimeToRFC2616, 
	isoTimestampFmt, parseISODT, formatISODT,
	formatRFC2616Date, parseRFC2616Date,
	fixIndentation, parsePercentExpression, hmsToDeg, dmsToDeg,
	fracHoursToDeg, degToHms, degToDms, getRelativePath, parseAssignments, 
	NameMap, formatSimpleTable, replaceXMLEntityRefs,
	ensureOneSlash,)
