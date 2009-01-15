"""
The base sub-package.  We export quite a few names through this package 
__init__, so most non-fancy clients can get by saying 

from gavo import base.

This module may not be imported by anything within base.
"""

from pyparsing import ParseException


from gavo.base import caches

from gavo.base.attrdef import *
from gavo.base.complexattrs import *
from gavo.base.excs import *

from gavo.base.codetricks import (compileFunction, runInSandbox, getBinaryName,
	silence, loadPythonModule)

from gavo.base.config import(
	get as getConfig, set as setConfig,
	setDBProfile, getDBProfile, getDBProfileByName,
	makeSitePath)

from gavo.base.coords import degToRad, Box

from gavo.base.literals import *

from gavo.base.meta import (
	MetaSyntaxError, MetaError, MetaCardError, NoMetaKey,
	InfoItem as MetaInfoItem,
	MetaMixin, ComputedMetaMixin,
	getMetaText, makeMetaValue)

from gavo.base.misctricks import NameMap
	
from gavo.base.parsecontext import (
	IdAttribute, OriginalAttribute, ReferenceAttribute, ParseContext,
	resolveId)

from gavo.base.sqlsupport import (DBError,
	getDBConnection, getDefaultDBConnection,
	SimpleQuerier)

from gavo.base.structure import (Structure, ParseableStructure, 
	RefAttribute, DataContent, makeStruct)

from gavo.base.texttricks import (fixIndentation,
	makeEllipsis, getRelativePath, parseAssignments,
	timeangleToDeg, dmsToDeg, fracHoursToDeg, degToTimeangle, degToDms)

from gavo.base.typesystems import *

from gavo.base.valuemappers import getMappedValues, ValueMapperFactoryRegistry

from gavo.base.vizierexprs import (getVexprFor, getSQLKey)

from gavo.base.unitconv import (
	computeConversionFactor, parseUnit, computeColumnConversions,
	IncompatibleUnits, BadUnit)

from gavo.base.xmlstruct import parseFromString, parseFromStream
