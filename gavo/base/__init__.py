"""
Basic code for defining objects in the data center: Structures, their 
attributes, fundamental VO conventions.
"""


# This doesn't belong here and it should go away again, but right now,
# astLib has an issue in the de_DE (and probably other) locales.
import locale, os
os.environ["LC_ALL"] = 'C'
locale.setlocale(locale.LC_ALL, 'C')

from pyparsing import ParseException

# This may not be the best place to put this, but I don't really have a
# better one at this point.  We need some configuration of pyparsing, and
# this is probably imported by all modules doing pyparsing.
from pyparsing import ParserElement
# Hack to get around behaviour swings of setParseAction; we use
# addParseAction throughout and retrofit it to pyparsings that don't have it.
if not hasattr(ParserElement, "addParseAction"):
	ParserElement.addParseAction = ParserElement.setParseAction
ParserElement.enablePackrat()
ParserElement.setDefaultWhitespaceChars(" \t")

from gavo.base import caches

from gavo.base.attrdef import *
from gavo.base.complexattrs import *

from gavo.base.config import(
	get as getConfig, set as setConfig,
	setDBProfile, getDBProfile, getDBProfileByName,
	makeSitePath, getBinaryName)

from gavo.base.coords import Box

from gavo.base.events import EventDispatcher

ui = EventDispatcher()
del EventDispatcher

from gavo.utils import Undefined
from gavo.utils.excs import *

from gavo.base.literals import *

from gavo.base.meta import (
	MetaSyntaxError, MetaError, MetaCardError, NoMetaKey,
	InfoItem as MetaInfoItem,
	MetaMixin, ComputedMetaMixin,
	getMetaText, makeMetaValue, makeMetaItem)

from gavo.base.metavalidation import MetaValidationError, validateStructure

from gavo.base.observer import ObserverBase, listensTo

from gavo.base.parsecontext import (
	IdAttribute, OriginalAttribute, ReferenceAttribute, ParseContext,
	resolveId)

from gavo.base.sqlsupport import (getDBConnection, getDefaultDBConnection,
	DBError, QueryCanceledError, IntegrityError,
	SimpleQuerier, encodeDBMsg)

from gavo.base.structure import (Structure, ParseableStructure, 
	DataContent, makeStruct, RestrictionMixin)

from gavo.base.typesystems import *

from gavo.base.valuemappers import SerManager, ValueMapperFactoryRegistry

from gavo.base.vizierexprs import (getVexprFor, getSQLKey, 
	joinOperatorExpr)

from gavo.base.unitconv import (
	computeConversionFactor, parseUnit, computeColumnConversions,
	IncompatibleUnits, BadUnit)

from gavo.base.xmlstruct import parseFromString, parseFromStream

DEBUG = False
