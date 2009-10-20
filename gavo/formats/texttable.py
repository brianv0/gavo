"""
Renderers that convert the primary table of a data set as text.
"""

import cStringIO
import re

from gavo import base


def _makeString(val):
	if isinstance(val, basestring):
		return repr(unicode(val))[2:-1]
	return str(val)

def renderAsText(data, target):
	"""writes a text (TSV) rendering of data's primary table to the file target.
	"""
	sm = base.SerManager(data.getPrimaryTable())
	for row in sm.getMappedTuples():
		target.write("\t".join([_makeString(s) for s in row])+"\n")

def getAsText(data):
	target = cStringIO.StringIO()
	renderAsText(data, target)
	return target.getvalue()
