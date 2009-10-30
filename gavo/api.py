"""
This should evolve into a useful API to GAVO code for more-or-less external
clients.

For now, it just makes sure that standard RDs can be imported.
"""

from gavo import base
from gavo import rscdesc
from gavo import web
from gavo.protocols import basic

getRD = base.caches.getRD

from gavo.base import (getConfig, getDBConnection, getDefaultDBConnection,
	setDBProfile, SimpleQuerier)
from gavo.rsc import (TableForDef, DBTable, makeData, parseValidating,
	parseNonValidating)
from gavo.utils import (Error, StructureError, ValidationError,
	ReportableError, NotFoundError, RDNotFound)
