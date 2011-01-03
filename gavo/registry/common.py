"""
Common code and definitions for registry support.
"""

import re

from gavo import base
from gavo import utils
from gavo.utils import stanxml


SERVICELIST_ID = "__system__/services"


METADATA_PREFIXES = [
# (prefix, schema-location, namespace)
	("oai_dc", stanxml.schemaURL("OAI-PMH.xsd"),
		"http://www.openarchives.org/OAI/2.0/oai_dc/"),
	("ivo_vor", stanxml.schemaURL("VOResource-v1.0.xsd"),
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
class NoMetadataFormats(OAIError): pass
class NoSetHierarchy(OAIError): pass
class NoRecordsMatch(OAIError): pass


def getServicesRD():
	return base.caches.getRD(SERVICELIST_ID)


def getRegistryService():
	return getServicesRD().getById("registry")


def getResType(resob):
	resType = resob.getMeta("resType", None)
	if resType is None:
		resType = resob.resType
	return str(resType)


class DateUpdatedMixin(object):
	"""A mixin providing computers for dateUpdated and datetimeUpdated.

	The trouble is that we need this in various formats.  Classes
	mixing this in may give a dateUpdated attribute (a datetime.datetime) 
	that is used to compute both meta elements.

	If any of them is overridden manually, the other is computed from
	the one given.
	"""
	def __getDatetimeMeta(self, key, format):
		dt = getattr(self, "dateUpdated", None)
		if dt is None:
			raise base.NoMetaKey(key, carrier=self)
		return dt.strftime(format)
	
	def _meta_dateUpdated(self):
		if "datetimeUpdated" in self.meta_:
			return str(self.meta_["datetimeUpdated"])[:8]
		return self.__getDatetimeMeta("dateUpdated", "%Y-%m-%d")
	
	def _meta_datetimeUpdated(self):
		if "dateUpdated" in self.meta_:
			return str(self.meta_["dateUpdated"])+"T00:00:00Z"
		return self.__getDatetimeMeta("dateUpdated", utils.isoTimestampFmt)


__all__ = ["SERVICELIST_ID", "METADATA_PREFIXES",

"getResType", "getServicesRD", "getRegistryService",

"DateUpdatedMixin",

"OAIError", "BadArgument", "BadResumptionToken", "BadVerb",
"CannotDisseminateFormat", "IdDoesNotExist", 
"NoMetadataFormats", "NoSetHierarchy",
"NoRecordsMatch",
]
