"""
Common code and definitions for registry support.
"""

import re

from gavo import base


SERVICELIST_ID = "__system__/services"


class OAIError(base.Error):
	"""is one of the standard OAI errors.
	"""

class BadArgument(OAIError): pass
class BadResumptionToken(OAIError): pass
class BadVerb(OAIError): pass
class CannotDisseminateFormat(OAIError): pass
class IdDoesNotExist(OAIError): pass
class NoRecordsMatch(OAIError): pass
class NoMetadataFormats(OAIError): pass
class NoSetHierarchy(OAIError): pass


def computeIdentifier(resource):
	"""returns an identifier for resource.

	resource can either be a StaticResource instance, a Service instance
	or a dictionary containing a record from the service table.
	"""
	if isinstance(resource, dict):
		if (resource["sourceRd"]=="<static resource>" or 
				resource["sourceRd"]==SERVICELIST_ID):
			reskey = "static/%s"%resource["internalId"]
		else:
			reskey = "%s/%s"%(resource["sourceRd"], resource["internalId"])
	else:
		reskey = resource.getIDKey()
	return "ivo://%s/%s"%(base.getConfig("ivoa", "authority"), reskey)


def parseIdentifier(identifier):
	"""returns a pair of authority, resource key for identifier.

	Identifier has to be an ivo URI.

	In the context of the gavo DC, the resource key either starts with
	static/ or consists of an RD id and a service ID.
	"""
	mat = re.match("ivo://(\w[^!;:@%$,/]+)/(.*)", identifier)
	if not mat:
		raise IdDoesNotExist(identifier)
	return mat.group(1), mat.group(2)



__all__ = ["SERVICELIST_ID", 

"OAIError", "BadArgument", "BadResumptionToken", "BadVerb",
"CannotDisseminateFormat", "IdDoesNotExist", "NoRecordsMatch",
"NoMetadataFormats", "NoSetHierarchy",

"computeIdentifier", "parseIdentifier",
]
