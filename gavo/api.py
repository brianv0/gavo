"""
This should evolve into a useful API to GAVO code for more-or-less external
clients.

For now, it just makes sure that standard RDs can be imported.
"""

from gavo import base
from gavo import rscdesc
from gavo import votable
from gavo import web

getRD = base.caches.getRD
RD = rscdesc.RD

from gavo.base import (getConfig, getDBConnection, getDefaultDBConnection,
	setDBProfile, SimpleQuerier, NoMetaKey)

from gavo.formats.votablewrite import writeAsVOTable, getAsVOTable

from gavo.rsc import (TableForDef, DBTable, makeData, parseValidating,
	parseNonValidating, Data)

from gavo.utils import (Error, StructureError, ValidationError,
	ReportableError, NotFoundError, RDNotFound)

from gavo.votable import VOTableError, ADQLTAPJob
