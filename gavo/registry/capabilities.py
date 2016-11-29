""" 
VOResource capability/interface elements.

The basic mapping from our RD elements to VOResource elements is that
each renderer on a service translates to a capability with one interface.
Thus, in the module we mostly deal with publication objects.  If you
need the service object, use publication.parent.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.registry import tableset
from gavo.registry.model import (VOR, VOG, VS, SIA, SCS, SLAP, SSAP, TR)


###################### Helpers (TODO: Move to tableset, I guess)


def _getParamFromColumn(column, rootElement, typeFactory):
	"""helper for get[Table|Input]ParamFromColumn.
	"""
	return rootElement[
			VS.name[column.name],
			VS.description[column.description],
			VS.unit[column.unit],
			VS.ucd[column.ucd],
			typeFactory(column.type)]


def getInputParamFromColumn(column, rootElement=VS.param):
	"""returns a InputParam element for a rscdef.Column.
	"""
	return _getParamFromColumn(column, rootElement,
		tableset.simpleDataTypeFactory)(
			std=(column.std and "true") or "false")


def getInputParams(publication, service):
	"""returns a sequence of vs:param elements for the input of service.
	"""
	if hasattr(service, "getInputKeysFor"): # no params on published tables
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
				base.getMetaText(publication, "accessURL",
					macroPackage=publication.parent)],
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
		paramSrc = publication.parent
		if publication.service:
			paramSrc = publication.service

		return InterfaceMaker._makeInterface(self, publication)[
			VS.queryType[base.getMetaText(
				publication, "requestMethod", propagate=False)],
			VS.resultType[base.getMetaText(
				publication, "resultType", propagate=False)],
			getInputParams(publication, paramSrc)
		]


class SIAPInterface(InterfaceWithParams):
	renderer = "siap.xml"
	interfaceClass = SIA.interface

class SIAP2Interface(InterfaceWithParams):
	renderer = "siap2.xml"
	interfaceClass = SIA.interface

class SCSInterface(InterfaceWithParams):
	renderer = "scs.xml"
	interfaceClass = SCS.interface

class SSAPInterface(InterfaceWithParams):
	renderer = "ssap.xml"
	interfaceClass = SSAP.interface

class SLAPInterface(InterfaceWithParams):
	renderer = "slap.xml"
	interfaceClass = SLAP.interface

class SODASyncInterface(InterfaceMaker):
	# here, we must not inquire parameters, as the core can only
	# tell when it actually has an ID, which we don't have here.
	renderer = "dlget"
	class interfaceClass(VS.ParamHTTP):
		role = "std"

class SODAAsyncInterface(SODASyncInterface):
	# same deal as with SODASyncInterface
	renderer = "dlasync"


class TAPInterface(InterfaceMaker):
# for TAP, result type is tricky, and we don't have good metadata
# on the accepted input parameters (QUERY, etc).  We should really
# provide them when we have extensions...
	renderer = "tap"
	interfaceClass = TR.interface

class ExamplesInterface(InterfaceMaker):
	renderer = "examples"
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

class GetProductInterface(WebBrowserInterface):
	renderer = "get"


_getInterfaceMaker = utils.buildClassResolver(InterfaceMaker, 
	globals().values(), instances=True, 
	key=lambda obj: obj.renderer,
	default=InterfaceWithParams())


def getInterfaceElement(publication):
	"""returns the appropriate interface definition for service and renderer.
	"""
	return _getInterfaceMaker(publication.render)(publication)
	

####################### Capabilities


class CapabilityMaker(object):
	"""An encapsulation of capability construction.

	Each capability (currently) corresponds to a renderer.

	You will want to override (some of) the class variables at the top, plus the
	_makeCapability method (that you'll probably still want to upcall for the
	basic functionality).

	In particular, you will typically want to override capabilityClass
	with a stanxml element spitting out the right standardIds.  
		
	Additionally, if the capability should also appear in data collections 
	served by a service with the capability, also define auxiliaryId (that's
	an IVOID like ivo://ivoa.net/std/TAP#aux).  These are used in 
	getCapabilityElement.

	CapabilityMakers are used by calling them.
	"""
	renderer = None
	capabilityClass = VOR.capability
	auxiliaryId = None

	def _makeCapability(self, publication):
		return self.capabilityClass[
			VOR.description[base.getMetaText(publication, "description", 
				propagate=False, macroPackage=publication.parent)],
			getInterfaceElement(publication)]

	def __call__(self, publication):
		return self._makeCapability(publication)


class PlainCapabilityMaker(CapabilityMaker):
	"""A capability maker for gerneric VR.capabilities.

	These essentially just set standardId. in addition to what
	the plain capabilities do.
	"""
	standardId = None

	def _makeCapability(self, publication):
		return CapabilityMaker._makeCapability(self, publication)(
			standardID=self.standardId)


class APICapabilityMaker(CapabilityMaker):
	renderer = "api"


class SIACapabilityMaker(CapabilityMaker):
	renderer = "siap.xml"
	capabilityClass = SIA.capability
	auxiliaryId = "ivo://ivoa.net/std/SIA#aux"

	def _makeCapability(self, publication):
		service = publication.parent
		return CapabilityMaker._makeCapability(self, publication)[
			SIA.imageServiceType[service.getMeta("sia.type", raiseOnFail=True)],
			SIA.maxQueryRegionSize[
				SIA.long[service.getMeta("sia.maxQueryRegionSize.long", default=None)],
				SIA.lat[service.getMeta("sia.maxQueryRegionSize.lat", default=None)],
			],
			SIA.maxImageExtent[
				SIA.long[service.getMeta("sia.maxImageExtent.long", default=None)],
				SIA.lat[service.getMeta("sia.maxImageExtent.lat", default=None)],
			],
			SIA.maxImageSize[
				service.getMeta("sia.maxImageSize", default=None),
			],
			SIA.maxFileSize[
				service.getMeta("sia.maxFileSize", default=None),
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


class SIAV2CapabilityMaker(SIACapabilityMaker):
	renderer = "siap2.xml"
	capabilityClass = SIA.capability2
	auxiliaryId = "ivo://ivoa.net/std/SIA#query-aux-2.0"


class SCSCapabilityMaker(CapabilityMaker):
	renderer = "scs.xml"
	capabilityClass = SCS.capability

	def _makeCapability(self, publication):
		service = publication.parent
		return CapabilityMaker._makeCapability(self, publication)[
			SCS.maxSR[base.getMetaText(service, "maxSR", "180")],
			SCS.maxRecords[str(base.getConfig("ivoa", "dalDefaultLimit")*10)],
			SCS.verbosity["true"],
			SCS.testQuery[
				SCS.ra[service.getMeta("testQuery.ra", raiseOnFail=True)],
				SCS.dec[service.getMeta("testQuery.dec", raiseOnFail=True)],
				SCS.sr[service.getMeta("testQuery.sr", default="0.001")],
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
			SSAP.supportedFrame["ICRS"],
			SSAP.maxSearchRadius["180"],
			SSAP.maxRecords[str(base.getConfig("ivoa", "dalHardLimit"))],
			SSAP.defaultMaxRecords[str(base.getConfig("ivoa", "dalDefaultLimit"))],
			SSAP.maxAperture["180"],
			SSAP.testQuery[
				SSAP.queryDataCmd[base.getMetaText(service, "ssap.testQuery", 
					raiseOnFail=True)+"&REQUEST=queryData"]],
		]


class SLAPCapabilityMaker(CapabilityMaker):
	renderer = "slap.xml"
	capabilityClass = SLAP.capability

	def _makeCapability(self, publication):
		service = publication.parent
		return CapabilityMaker._makeCapability(self, publication)[
			SLAP.complianceLevel[
				service.getMeta("slap.complianceLevel", default="full")], 
			SSAP.dataSource[service.getMeta("slap.dataSource", raiseOnFail=True)],
			SSAP.testQuery[
				SSAP.queryDataCmd[base.getMetaText(service, "slap.testQuery", 
					raiseOnFail=True)]],
		]


_tapModelBuilder = meta.ModelBasedBuilder([
	('supportsModel', meta.stanFactory(TR.dataModel), (), 
		{"ivoId": "ivoId"})])

class TAPCapabilityMaker(CapabilityMaker):
	renderer = "tap"
	capabilityClass = TR.capability
	auxiliaryId = "ivo://ivoa.net/std/TAP#aux"

	def _makeCapability(self, publication):
		res = CapabilityMaker._makeCapability(self, publication)
	
		with base.getTableConn() as conn:
			from gavo.protocols import tap
			from gavo.adql import ufunctions

			res[[
				TR.dataModel(ivoId=dmivoid)[dmname]
					for dmname, dmivoid in conn.query(
						"select dmname, dmivorn from tap_schema.supportedmodels")]]

			res[
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


class RegistryCapabilityMaker(CapabilityMaker):
	renderer = "pubreg.xml"
	capabilityClass = VOG.Harvest
	def _makeCapability(self, publication):
		return CapabilityMaker._makeCapability(self, publication)[
			VOG.maxRecords[str(base.getConfig("ivoa", "oaipmhPageSize"))]]


class VOSICapabilityMaker(PlainCapabilityMaker):
	# A common parent for the VOSI cap. makers.  All of those are
	# parallel and only differ by standardID
	capabilityClass = VOG.capability


class VOSIAvCapabilityMaker(VOSICapabilityMaker):
	renderer = "availability"
	standardId = "ivo://ivoa.net/std/VOSI#availability"

class VOSICapCapabilityMaker(VOSICapabilityMaker):
	renderer = "capabilities"
	standardId = "ivo://ivoa.net/std/VOSI#capabilities"

class VOSITMCapabilityMaker(VOSICapabilityMaker):
	renderer = "tableMetadata"
	standardId = "ivo://ivoa.net/std/VOSI#tables"

class ExamplesCapabilityMaker(PlainCapabilityMaker):
	renderer = "examples"
	standardId = "ivo://ivoa.net/std/DALI#examples-1.0"

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

class ProductCapabilityMaker(CapabilityMaker):
	renderer = "get"


class DatalinkCapabilityMaker(CapabilityMaker):
	renderer = "dlmeta"

	class capabilityClass(VOR.capability):
		_a_standardID = "ivo://ivoa.net/std/DataLink#links-1.0"


class SODACapabilityMaker(CapabilityMaker):
	renderer = "dlget"

	class capabilityClass(VOR.capability):
		_a_standardID = "ivo://ivoa.net/std/SODA#sync-1.0"


class SODAAsyncCapabilityMaker(CapabilityMaker):
	renderer = "dlasync"

	class capabilityClass(VOR.capability):
		_a_standardID = "ivo://ivoa.net/std/SODA#async-1.0"



_getCapabilityMaker = utils.buildClassResolver(CapabilityMaker, 
	globals().values(), instances=True, 
	key=lambda obj: obj.renderer)


def getAuxiliaryCapability(publication):
	"""returns a VR.capability element for an auxiliary publication.

	That's a plain capability with essentially the interface and a
	standardId obtained from the auxiliaryId attribute of the
	capability's normal maker.

	If no auxiliaryId is defined, None is returned (which means no
	capability will be generated).
	"""
	capMaker = _getCapabilityMaker(publication.render)
	if capMaker.auxiliaryId:
		return CapabilityMaker()(publication)(standardID=capMaker.auxiliaryId)


def getCapabilityElement(publication):
	"""returns the appropriate capability definition for a publication object.
	"""
	if publication.auxiliary:
		return getAuxiliaryCapability(publication)
	else:
		try:
			maker = _getCapabilityMaker(publication.render)
		except KeyError:
			raise base.ui.logOldExc(base.ReportableError("Do not know how to"
				" produce a capability for the '%s' renderer"%publication.render))
		return maker  (publication)
