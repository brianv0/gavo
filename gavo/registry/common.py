"""
Common code and definitions for registry support.
"""

import re

from gavo import base


SERVICELIST_ID = "__system__/services"
STATICRSC_ID = "__system__/staticrsc"

METADATA_PREFIXES = [
# (prefix, schema-location, namespace)
	("oai_dc", "http://vo.ari.uni-heidelberg.de/docs/schemata/OAI-PMH.xsd",
		"http://www.openarchives.org/OAI/2.0/oai_dc/"),
	("ivo_vor", "http://www.ivoa.net/xml/RegistryInterface/v1.0",
		"http://www.ivoa.net/xml/RegistryInterface/v1.0"),
]


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


def getServicesRD():
	return base.caches.getRD(SERVICELIST_ID)


def getRegistryService():
	return getServicesRD().getById("registry")


def getResType(resob):
	resType = resob.getMeta("resType", None)
	if resType is None:
		resType = resob.resType
	return str(resType)


__all__ = ["SERVICELIST_ID", "STATICRSC_ID", "METADATA_PREFIXES",

"getResType", "getServicesRD", "getRegistryService",

"OAIError", "BadArgument", "BadResumptionToken", "BadVerb",
"CannotDisseminateFormat", "IdDoesNotExist", "NoRecordsMatch",
"NoMetadataFormats", "NoSetHierarchy",
]
