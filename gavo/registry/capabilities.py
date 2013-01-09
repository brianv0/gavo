""" 
VOResource capability/interface elements.

The basic mapping from our RD elements to VOResource elements is that
each renderer on a service translates to a capability with one interface.
Thus, in the module we mostly deal with publication objects.  If you
need the service object, use publication.parent.
"""

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.base import typesystems
from gavo.registry.common import *
from gavo.registry.model import (OAI, OAIDC, VOR, VOG, DC, RI, VS,
	SIA, SCS, SSAP, TR)


###################### Helpers (TODO: Move to tableset, I guess)

def _getParamFromColumn(column, rootElement, typeFactory):
	"""helper for get[Table|Input]ParamFromColumn.
	"""
	type, length = typesystems.sqltypeToVOTable(column.type)
	return rootElement[
			VS.name[column.name],
			VS.description[column.description],
			VS.unit[column.unit],
			VS.ucd[column.ucd],
			typeFactory(type, length)]


def getInputParamFromColumn(column, rootElement=VS.param):
	"""returns a InputParam element for a rscdef.Column.
	"""
	return _getParamFromColumn(column, rootElement,
		lambda type, length: VS.simpleDataType[type])(
			std=(column.std and "true") or "false")


def getInputParams(publication, service):
	"""returns a sequence of vs:param elements for the input of service.
	"""
	return [getInputParamFromColumn(f) 
		for f in service.getInputKeysFor(svcs.getRenderer(publication.render))]


####################### Interfaces

class InterfaceMaker(object):
	"""An encapsulation of interface construction.

	Each interface maker corresponds to a renderer and thus a publication on a
	service.  It knows enough about the characteristics of a renderer to create
	interface stan by just calling.

	This class is abstract.  To build concrete interface makers, at
	least fill out the class variables.  You will probably want
	to override the _makeInterface method for some renderers corresponding
	so specially defined interfaces; the default implementation corresponds
	to the VOResource definition.
	"""
	renderer = None
	interfaceClass = VOR.interface

	def _makeInterface(self, publication):
		return self.interfaceClass[
			VOR.accessURL(use=base.getMetaText(publication, "urlUse"))[
				base.getMetaText(publication, "accessURL")],
			VOR.securityMethod(
				standardId=base.getMetaText(publication, "securityId")),
		]

	def __call__(self, publication):
		return self._makeInterface(publication)



class VOSIInterface(InterfaceMaker):
	class interfaceClass(VS.ParamHTTP):
		role = "std"

class VOSIAvInterface(VOSIInterface):
	renderer = "availability"

class VOSICapInterface(VOSIInterface):
	renderer = "capabilities"

class VOSITMInterface(VOSIInterface):
	renderer = "tableMetadata"


class InterfaceWithParams(InterfaceMaker):
	"""An InterfaceMaker on a publication sporting input parameters.

	This corresponds to a ParamHTTP interface.
	"""
	interfaceClass = VS.ParamHTTP

	def _makeInterface(self, publication):
		return InterfaceMaker._makeInterface(self, publication)[
			VS.queryType[base.getMetaText(publication, "requestMethod")],
			VS.resultType[base.getMetaText(publication, "resultType")],
			getInputParams(publication, publication.parent),
		]


class JPEGInterface(InterfaceWithParams):
	renderer = "img.jpeg"


class SIAPInterface(InterfaceWithParams):
	renderer = "siap.xml"
	interfaceClass = SIA.interface


class SCSInterface(InterfaceWithParams):
	renderer = "scs.xml"
	interfaceClass = SCS.interface


class SSAPInterface(InterfaceWithParams):
	renderer = "ssap.xml"
	interfaceClass = SSAP.interface


class TAPInterface(InterfaceMaker):
# for TAP, result type is tricky, and we don't have good metadata
# on the accepted input parameters (QUERY, etc).  We should really
# provide them when we have extensions...
	renderer = "tap"
	interfaceClass = TR.interface

class TAPExamplesInterface(InterfaceMaker):
	renderer = "tapexamples"
	interfaceClass = VOR.WebBrowser


class SOAPInterface(InterfaceMaker):
	renderer = "soap"
	interfaceClass = VOR.WebService

	def _makeInterface(self, publication):
		return InterfaceMaker._makeInterface(self, publication)[
			VOR.wsdlURL[base.getMetaText(publication, "accessURL")+"?wsdl"],
		]


class OAIHTTPInterface(InterfaceMaker):
	renderer = "pubreg.xml"
	interfaceClass = VOG.OAIHTTP

	def _makeInterface(self, publication):
		return InterfaceMaker._makeInterface(self, publication)(role="std")


class WebBrowserInterface(InterfaceMaker):
	"""An InterfaceMaker on a publication to be consumed by a web browser.

	This is abstract since various renderers boil down to this.
	"""
	interfaceClass = VOR.WebBrowser


class FormInterface(WebBrowserInterface):
	renderer = "form"

class DocformInterface(WebBrowserInterface):
	renderer = "docform"



# Actually, statics, externals and customs could be anything, but if you
# register it, it's better be something a web browser can handle.

class FixedInterface(WebBrowserInterface):
	renderer = "fixed"

class StaticInterface(WebBrowserInterface):
	renderer = "static"

class CustomInterface(WebBrowserInterface):
	renderer = "custom"

class ExternalInterface(WebBrowserInterface):
	renderer = "external"



_getInterfaceMaker = utils.buildClassResolver(InterfaceMaker, 
	globals().values(), instances=True, 
	key=lambda obj: obj.renderer)


def getInterfaceElement(publication):
	"""returns the appropriate interface definition for service and renderer.
	"""
	return _getInterfaceMaker(publication.render)(publication)
	

####################### Capabilities


class CapabilityMaker(object):
	"""An encapsulation of capability construction.

	Each capability (currently) corresponds to a renderer.

	This class is abstract.  You will want to override (some of) the
	class variables at the top, plus the _makeCapability method.

	CapabilityMakers are used by calling them.
	"""
	renderer = None
	capabilityClass = VOR.capability

	def _makeCapability(self, publication):
		return self.capabilityClass[
			VOR.description[base.getMetaText(publication, "description", 
				propagate=False, macroPackage=publication.parent)],
			getInterfaceElement(publication)]

	def __call__(self, publication):
		return self._makeCapability(publication)


class SIACapabilityMaker(CapabilityMaker):
	renderer = "siap.xml"
	capabilityClass = SIA.capability

	def _makeCapability(self, publication):
		service = publication.parent
		return CapabilityMaker._makeCapability(self, publication)[
			SIA.imageServiceType[service.getMeta("sia.type", raiseOnFail=True)],
			SIA.maxQueryRegionSize[
				SIA.long[service.getMeta("sia.maxQueryRegionSize.long", default="180")],
				SIA.lat[service.getMeta("sia.maxQueryRegionSize.lat", default="180")],
			],
			SIA.maxImageExtent[
				SIA.long[service.getMeta("sia.maxImageExtent.long", default="180")],
				SIA.lat[service.getMeta("sia.maxImageExtent.lat", default="180")],
			],
			SIA.maxImageSize[
				SIA.long[service.getMeta("sia.maxImageSize.long", default="100000")],
				SIA.lat[service.getMeta("sia.maxImageSize.lat", default="1000000")],
			],
			SIA.maxFileSize[
				service.getMeta("sia.maxFileSize", default="2000000000"),
			],
			SIA.maxRecords[
				service.getMeta("sia.maxRecords", 
					default=str(base.getConfig("ivoa", "dalHardLimit"))),
			],
			SIA.testQuery[
				SIA.pos[
					SIA.long[service.getMeta("testQuery.pos.ra")],
					SIA.lat[service.getMeta("testQuery.pos.dec")],
				],
				SIA.size[
					SIA.long[service.getMeta("testQuery.size.ra")],
					SIA.lat[service.getMeta("testQuery.size.dec")],
				],
			],
		]


class SCSCapabilityMaker(CapabilityMaker):
	renderer = "scs.xml"
	capabilityClass = SCS.capability

	def _makeCapability(self, publication):
		service = publication.parent
		return CapabilityMaker._makeCapability(self, publication)[
			SCS.maxSR["180.0"],
			SCS.maxRecords[str(base.getConfig("ivoa", "dalDefaultLimit"))],
			SCS.verbosity["true"],
			SCS.testQuery[
				SCS.ra[service.getMeta("testQuery.ra", raiseOnFail=True)],
				SCS.dec[service.getMeta("testQuery.dec", raiseOnFail=True)],
				SCS.sr["0.001"],
			],
		]


class SSACapabilityMaker(CapabilityMaker):
	renderer = "ssap.xml"
	capabilityClass = SSAP.capability

	def _makeCapability(self, publication):
		service = publication.parent
		return CapabilityMaker._makeCapability(self, publication)[
			# XXX TODO: see what we need for "full"
			SSAP.complianceLevel[
				service.getMeta("ssap.complianceLevel", default="minimal")], 
			SSAP.dataSource[service.getMeta("ssap.dataSource", raiseOnFail=True)],
			SSAP.creationType[service.getMeta("ssap.creationType", 
				default="archival")],
			SSAP.maxSearchRadius["180"],
			SSAP.maxRecords[str(base.getConfig("ivoa", "dalHardLimit"))],
			SSAP.defaultMaxRecords[str(base.getConfig("ivoa", "dalDefaultLimit"))],
			SSAP.maxAperture["180"],
			SSAP.testQuery[
				SSAP.queryDataCmd[base.getMetaText(service, "ssap.testQuery", 
					raiseOnFail=True)+"&REQUEST=queryData"]],
		]


_tapModelBuilder = meta.ModelBasedBuilder([
	('supportsModel', meta.stanFactory(TR.dataModel), (), 
		{"ivoId": "ivoId"})])

class TAPCapabilityMaker(CapabilityMaker):
	renderer = "tap"
	capabilityClass = TR.capability

	def _makeCapability(self, publication):
		res = CapabilityMaker._makeCapability(self, publication)
		
		with base.getTableConn() as conn:
			service = publication.parent
			from gavo.protocols import tap
			from gavo.adql import ufunctions
			res[[
					TR.dataModel(ivoId=dmivorn)[dmname]
					for dmname, dmivorn in conn.query(
						"select dmname, dmivorn from tap_schema.supportedmodels")],
				# Once we support more than one language, we'll have to
				# revisit this -- the optional features must then become
				# a property of the language.
				[TR.language[
						TR.name[langName],
						TR.version(ivoId=ivoId)[version],
						TR.description[description],
						TR.languageFeatures(
							type="ivo://ivoa.net/std/TAPRegExt#features-udf")[
							[TR.feature[
								TR.form[udf.adqlUDF_signature],
								TR.description[udf.adqlUDF_doc]]
							for udf in ufunctions.UFUNC_REGISTRY.values()]],
						TR.languageFeatures(
								type="ivo://ivoa.net/std/TAPRegExt#features-adqlgeo")[
							[TR.feature[
								TR.form[funcName]]
							# take this from adql.grammar somehow?
							for funcName in ("BOX", "POINT", "CIRCLE", "POLYGON",
									"REGION", "CENTROID", "COORD1", "COORD2",
									"DISTANCE", "CONTAINS", "INTERSECTS", "AREA")]]]
					for langName, version, description, ivoId
						in tap.getSupportedLanguages()],
				[TR.outputFormat(ivoId=ivoId)[
						TR.mime[mime], 
							[TR.alias[alias] for alias in aliases]]
					for mime, aliases, description, ivoId 
						in tap.getSupportedOutputFormats()],
				[TR.uploadMethod(ivoId="ivo://ivoa.net/std/TAPRegExt#%s"%proto)
					for proto in tap.UPLOAD_METHODS],
				TR.retentionPeriod[
					TR.default[str(base.getConfig("async", "defaultLifetime"))]],
				TR.executionDuration[
					TR.default[str(base.getConfig("async", "defaultExecTime"))]],
				TR.outputLimit[
					TR.default(unit="row")[
						str(base.getConfig("async", "defaultMAXREC"))],
					TR.hard(unit="row")[
						str(base.getConfig("async", "hardMAXREC"))]],
				TR.uploadLimit[
					TR.hard(unit="byte")[
						str(base.getConfig("web", "maxUploadSize"))]]]
		
		return res


class TAPExCapabilityMaker(CapabilityMaker):
	renderer = "tapexamples"
	capabilityClass = VOG.capability
	def _makeCapability(self, publication):
		return CapabilityMaker._makeCapability(self, publication)(
			standardID="ivo://org.gavo.dc/misc/tapexamples")
			

class RegistryCapabilityMaker(CapabilityMaker):
	renderer = "pubreg.xml"
	capabilityClass = VOG.Harvest
	def _makeCapability(self, publication):
		return CapabilityMaker._makeCapability(self, publication)[
			VOG.maxRecords[str(base.getConfig("ivoa", "oaipmhPageSize"))]]


class VOSICapabilityMaker(CapabilityMaker):
	# A common parent for the VOSI cap. makers.  All of those are
	# parallel and only differ by standardID
	capabilityClass = VOG.capability

	def _makeCapability(self, publication):
		return CapabilityMaker._makeCapability(self, publication)(
			standardID=self.standardID)


class VOSIAvCapabilityMaker(VOSICapabilityMaker):
	renderer = "availability"
	standardID = "ivo://ivoa.net/std/VOSI#availability"

class VOSICapCapabilityMaker(VOSICapabilityMaker):
	renderer = "capabilities"
	standardID = "ivo://ivoa.net/std/VOSI#capabilities"

class VOSITMCapabilityMaker(VOSICapabilityMaker):
	renderer = "tableMetadata"
	standardID = "ivo://ivoa.net/std/VOSI#tables"

class SOAPCapabilityMaker(CapabilityMaker):
	renderer = "soap"

class FormCapabilityMaker(CapabilityMaker):
	renderer = "form"

class ExternalCapabilityMaker(CapabilityMaker):
	renderer = "external"

class StaticCapabilityMaker(CapabilityMaker):
	renderer = "static"

class CustomCapabilityMaker(CapabilityMaker):
	renderer = "custom"

class JPEGCapabilityMaker(CapabilityMaker):
	renderer = "img.jpeg"

class FixedCapabilityMaker(CapabilityMaker):
	renderer = "fixed"

class DocformCapabilityMaker(CapabilityMaker):
	renderer = "docform"


_getCapabilityMaker = utils.buildClassResolver(CapabilityMaker, 
	globals().values(), instances=True, 
	key=lambda obj: obj.renderer)


def getCapabilityElement(publication):
	"""returns the appropriate capability definition for a publication object.
	"""
	res = _getCapabilityMaker(publication.render)(publication)
	return res
