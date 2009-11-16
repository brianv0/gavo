"""
Parsing identifiers, getting res tuples and resobs from them.
"""

import re

from gavo import base
from gavo.registry import staticresource
from gavo.registry import servicelist
from gavo.registry.common import *


def computeIdentifierFromRestup(restup):
	"""returns an identifier from a res tuple.
	"""
	if (restup["sourceRd"]=="<static resource>" or 
		restup["sourceRd"]==STATICRSC_ID):
		reskey = "static/%s"%restup["internalId"]
	else:
		reskey = "%s/%s"%(restup["sourceRd"], restup["internalId"])
	return "ivo://%s/%s"%(base.getConfig("ivoa", "authority"), reskey)


_idPattern = re.compile("ivo://(\w[^!;:@%$,/]+)/(.*)")

def parseIdentifier(identifier):
	"""returns a pair of authority, resource key for identifier.

	Identifier has to be an ivo URI.

	In the context of the gavo DC, the resource key either starts with
	static/ or consists of an RD id and a service ID.
	"""
	mat = _idPattern.match(identifier)
	if not mat:
		raise IdDoesNotExist(identifier)
	return mat.group(1), mat.group(2)


def getRestupFromIdentifier(identifier):
	"""returns the record for identifier in the services table.
	"""
	authority, resKey = parseIdentifier(identifier)
	if authority!=base.getConfig("ivoa", "authority"):
		raise IdDoesNotExist(identifier)
	if resKey.startswith("static/"):
		sourceRD = STATICRSC_ID
		internalId = resKey[len("static/"):]
	else:
		parts = resKey.split("/")
		sourceRD = "/".join(parts[:-1])
		internalId = parts[-1]
	matches = servicelist.queryServicesList(
		"sourceRd=%(sourceRD)s AND internalId=%(internalId)s",
		locals(), tableName="services")
	if len(matches)!=1:
		raise IdDoesNotExist(identifier)
	return matches[0]


def getResobFromRestup(restup):
	"""returns a resob for a res tuple.

	restup at least has to contain the sourceRD and internalId fields.

	The item that is being returned is either a service or a StaticResource
	object.  All of these have a getMeta method and should be able to
	return the standard DC metadata.  Everything else depends on the type
	of StaticResource.
	"""
	if restup["deleted"]:
		return staticresource.DeletedResource(
			computeIdentifierFromRestup(restup), restup)
	sourceRD, internalId = restup["sourceRd"], restup["internalId"]
	if sourceRD==STATICRSC_ID:
		return staticresource.loadStaticResource(internalId)
	else:
		try:
			return base.caches.getRD(sourceRD).serviceIndex[internalId]
		except KeyError:
			raise base.NotFoundError(internalId, what="service",
				within="RD %s"%sourceRD, hint="This usually happens when you"
				" forgot to run gavopublish %s"%sourceRD)


def getResobFromIdentifier(identifier):
	"""returns a resob for an identifier.
	"""
	return getResobFromRestup(getRestupFromIdentifier(identifier))
