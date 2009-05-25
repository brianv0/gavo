"""
Support for VO-Type Space-Time-Coordinates.

We're dealing with a huge data model here that probably can't be
fully implemented in any sense of the word.

So, we have a stripped down data model in the form of an abstract syntax
tree here (defined in the dm submodule).  This can be built directly or
from various input formats (XXXast submodules).  From the AST, you can
also build various output formats (XXXgen submodules).

All other operations should be performed on the AST.

Note that this is slow as a dog.  I doubt we'll ever see performant STC
implementations.  This is really intended for one-shot transformations,
e.g. into functions or a query language.  Don't do any transformations
in serious loops.
"""

from gavo.stc.common import (STCError, STCSParseError, STCLiteralError,
	STCValueError, STCNotImplementedError,
	STCNamespace)

from gavo.stc.conform import conformSpherical

from gavo.stc.stcsast import parseSTCS

from gavo.stc.stcsgen import getSTCS

from gavo.stc.stcx import STC

from gavo.stc.stcxast import parseSTCX

from gavo.stc.stcxgen import astToStan, getSTCXProfile

from gavo.stc.times import (parseISODT, 
	jYearToDateTime, dateTimeToJYear,
	bYearToDateTime, dateTimeToBYear,
	jdnToDateTime, dateTimeToJdn)

