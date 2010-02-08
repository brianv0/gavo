"""
Writing Table objects as text.
"""

import cStringIO
import re

from gavo import base
from gavo import rsc
from gavo.formats import common


def _makeString(val):
# this is a cheap trick to ensure everything non-ascii is escaped.
	if isinstance(val, basestring):
		return repr(unicode(val))[2:-1]
	return str(val)


def renderAsText(table, target):
	"""writes a text (TSV) rendering of table to the file target.
	"""
	if isinstance(table, rsc.Data):
		table = table.getPrimaryTable()
	sm = base.SerManager(table)
	for row in sm.getMappedTuples():
		target.write("\t".join([_makeString(s) for s in row])+"\n")


def getAsText(data):
	target = cStringIO.StringIO()
	renderAsText(data, target)
	return target.getvalue()


# NOTE: This will only serialize the primary table.
common.registerDataWriter("tsv", renderAsText)
