"""
Support for VO-Type Space-Time-Coordinates.

We're dealing with a huge data model here that probably can't be
fully implemented in any sense of the word.

So, our main data structure is an ElementTree DOM that stores
more or less raw STC/X data.  This can be fed using xmlstan,
from STC/X serialized data or from STC/S serialized data.

This DOM is passed to the various helper functions.

Note that this is slow as a dog.  I doubt we'll ever see performant STC
implementations.  This is really intended for one-shot transformations,
e.g. into functions or a query language.  Don't do any transformations
in serious loops.
"""

from gavo.stc.common import STCError, STCSParseError, STCLiteralError

from gavo.stc.stcsast import parseSTCS

from gavo.stc.stcx import STC

from gavo.stc.times import (parseISODT, 
	jYearToDateTime, dateTimeToJYear,
	bYearToDateTime, dateTimeToBYear,
	jdnToDateTime, dateTimeToJdn)

