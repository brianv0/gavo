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

from gavo.base import (getConfig, setConfig,
	getDBConnection, getDefaultDBConnection, setDBProfile, #deprecated
	SimpleQuerier,  # deprecated
	AdhocQuerier, getTableConn, getAdminConn,
	getWritableAdminConn,
	NoMetaKey, Error, StructureError, ValidationError, LiteralParseError, 
	ReportableError, NotFoundError, RDNotFound, 
	parseFromString,
	ui)

from gavo.formats.votablewrite import (writeAsVOTable, getAsVOTable,
	VOTableContext)

from gavo.rsc import (TableForDef, DBTable, makeData, parseValidating,
	parseNonValidating, getParseOptions, Data)

from gavo.rscdef import TableDef

from gavo.votable import VOTableError, ADQLTAPJob
