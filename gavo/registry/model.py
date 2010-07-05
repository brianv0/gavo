"""
Data model for the VO registry interface.
"""

from gavo import base
from gavo.base import typesystems
from gavo.utils import ElementTree
from gavo.utils.stanxml import Element, XSITypeMixin, schemaURL, XSINamespace


class Error(base.Error):
	pass


OAINamespace = "http://www.openarchives.org/OAI/2.0/"
OAIDCNamespace = "http://www.openarchives.org/OAI/2.0/oai_dc/"
RINamespace = "http://www.ivoa.net/xml/RegistryInterface/v1.0"
VOGNamespace = "http://www.ivoa.net/xml/VORegistry/v1.0"
VORNamespace = "http://www.ivoa.net/xml/VOResource/v1.0"
DCNamespace = "http://purl.org/dc/elements/1.1/"
VSNamespace ="http://www.ivoa.net/xml/VODataService/v1.0"
VS1Namespace ="http://www.ivoa.net/xml/VODataService/v1.1"
SCSNamespace = "http://www.ivoa.net/xml/ConeSearch/v1.0" 
SIANamespace="http://www.ivoa.net/xml/SIA/v1.0" 
AVLNamespace = "http://www.ivoa.net/xml/VOSIAvailability/v1.0"
CAPNamespace = "http://www.ivoa.net/xml/VOSICapabilities/v1.0"

# Since we usually have the crappy namespaced attribute values (yikes!),
# and ElementTree is (IMHO rightly) unaware of schemata, we need this 
# mapping badly.  Don't change it without making sure the namespaces 
# in question aren't referenced in attributes.
ElementTree._namespace_map[VORNamespace] = "vr"
ElementTree._namespace_map[VOGNamespace] = "vg"
ElementTree._namespace_map[OAINamespace] = "oai"
ElementTree._namespace_map[OAIDCNamespace] = "oai_dc"
ElementTree._namespace_map[DCNamespace] = "dc"
ElementTree._namespace_map[RINamespace] = "ri"
ElementTree._namespace_map[VSNamespace] = "vs"
ElementTree._namespace_map[VS1Namespace] = "vs1"
ElementTree._namespace_map[SCSNamespace] = "cs"
ElementTree._namespace_map[SIANamespace] = "sia"
ElementTree._namespace_map[AVLNamespace] = "avl"
ElementTree._namespace_map[CAPNamespace] = "cap"


_schemaLocations = {
	OAINamespace: schemaURL("OAI-PMH.xsd"),
	OAIDCNamespace: schemaURL("oai_dc.xsd"),
	VORNamespace: schemaURL("VOResource-v1.0.xsd"),
	VOGNamespace: schemaURL("VORegistry-v1.0.xsd"),
	DCNamespace: schemaURL("simpledc20021212.xsd"),
	RINamespace: schemaURL("RegistryInterface-v1.0.xsd"),
	VSNamespace: schemaURL("VODataService-v1.0.xsd"),
	VS1Namespace: schemaURL("VODataService-v1.1.xsd"),
	SCSNamespace: schemaURL("ConeSearch-v1.0.xsd"),
	SIANamespace: schemaURL("SIA-v1.0.xsd"),
	AVLNamespace: schemaURL("VOSIAvailability-v1.0.xsd"),
	CAPNamespace: schemaURL("VOSICapabilities-v1.0.xsd"),
}



class SchemaLocationMixin(object):
	_a_xmlns_xsi = XSINamespace
	_name_a_xmlns_xsi = "xmlns:xsi"
	_a_xsi_schemaLocation = " ".join(["%s %s"%(ns, xs) 
		for ns, xs in _schemaLocations.iteritems()])
	_name_a_xsi_schemaLocation = "xsi:schemaLocation"


def addSchemaLocations(object):
	"""adds schema locations to for the common VO schemata to an xmlstan
	object.

	This is the equivalent of using the SchemaLocationMixin stanxml classes.
	"""
	object.addAttribute("xsi:schemaLocation", 
		SchemaLocationMixin._a_xsi_schemaLocation)
	object.addAttribute("xmlns:xsi", XSINamespace)


class OAI(object):
	"""is a container for classes modelling OAI elements.
	"""
	class OAIElement(Element):
		_namespace = OAINamespace

	class PMH(OAIElement, SchemaLocationMixin):
		_name = "OAI-PMH"
		_a_xmlns_sia = SIANamespace
		_name_a_xmlns_sia = "xmlns:sia"
		_a_xmlns_cs = SCSNamespace
		_name_a_xmlns_cs = "xmlns:cs"
		_a_xmlns_vs = VSNamespace
		_name_a_xmlns_vs = "xmlns:vs"
	
	class responseDate(OAIElement): pass

	class request(OAIElement):
		_mayBeEmpty = True
		_a_verb = None
		_a_metadataPrefix = None

	class metadata(OAIElement): pass

	class Identify(OAIElement): pass

	class ListIdentifiers(OAIElement): pass

	class ListRecords(OAIElement): pass

	class GetRecord(OAIElement): pass
	
	class ListMetadataFormats(OAIElement): pass

	class ListSets(OAIElement): pass

	class header(OAIElement):
		_a_status = None

	class error(OAIElement):
		_mayBeEmpty = True
		_a_code = None

	class record(OAIElement): pass

	class identifier(OAIElement): pass
	
	class datestamp(OAIElement): pass
	
	class setSpec(OAIElement): pass

	class repositoryName(OAIElement): pass
	
	class baseURL(OAIElement): pass
	
	class adminEmail(OAIElement): pass
	
	class earliestDatestamp(OAIElement): pass
	
	class deletedRecord(OAIElement): pass
	
	class granularity(OAIElement): pass

	class description(OAIElement): pass
	
	class protocolVersion(OAIElement): pass

	class metadataFormat(OAIElement): pass

	class metadataPrefix(OAIElement): pass
	
	class schema(OAIElement): pass

	class metadataNamespace(OAIElement): pass

	class set(OAIElement): pass
	
	class setSpec(OAIElement): pass
	
	class setName(OAIElement): pass


class OAIDC:
	"""is a container for OAI's Dublin Core metadata model.
	"""
	class OAIDCElement(Element):
		_namespace = OAIDCNamespace
	
	class dc(OAIDCElement):
		pass


class VOR:
	"""is a container for classes modelling elements from VO Resource.
	"""
	class VORElement(Element):
		_namespace = VORNamespace
		_local = True

	class Resource(VORElement, XSITypeMixin):
# This is "abstract" in that only derived elements may be present
# in an instance document (since VOR doesn't define any global elements).
# Typically, this will be ri:Resource elements with some funky xsi:type
		_a_created = None
		_a_updated = None
		_a_status = None
		_name = ElementTree.QName(RINamespace, "Resource")
		_local = False
		_a_xmlns_vr = VORNamespace
		_name_a_xmlns_vr = "xmlns:vr"
		c_title = None
		c_curation = None
		c_identifier = None
		c_shortName = None
		c_title = None

	class Organisation(Resource):
		_a_xsi_type = "vr:Organisation"
		c_facility = []
		c_instrument = []
		
	class Service(Resource):
		_a_xsi_type = "vr:Service"

	class validationLevel(VORElement):
		_a_validatedBy = None
	
	class title(VORElement): pass
	
	class shortName(VORElement): pass

	class ResourceName(VORElement):
		_a_ivo_id = None
		_name_a_ivo_id = "ivo-id"

	class identifier(VORElement): pass

	class curation(VORElement): pass
	
	class content(VORElement): pass

	class creator(VORElement): pass
	
	class contributor(ResourceName): pass
	
	class date(VORElement):
		_a_role = None
	
	class version(VORElement): pass
	
	class contact(VORElement): pass
	
	class publisher(ResourceName): pass

	class facility(VORElement): pass

	class instrument(VORElement): pass
	
	class relatedResource(VORElement): pass
	
	class name(VORElement): pass
	
	class address(VORElement): pass
	
	class email(VORElement): pass
	
	class telephone(VORElement): pass
	
	class logo(VORElement): pass
	
	class subject(VORElement): pass
	
	class description(VORElement): pass
	
	class source(VORElement): pass
	
	class referenceURL(VORElement): pass
	
	class type(VORElement): pass
	
	class contentLevel(VORElement): pass
	
	class relationship(VORElement): pass
	
	class rights(VORElement): pass
	
	class capability(VORElement, XSITypeMixin):
		_name = "capability"
		_a_standardID = None
	
	class interface(VORElement, XSITypeMixin):
		_name = "interface"
		_a_version = None
		_a_role = None
		_a_qtype = None

	class WebBrowser(interface):
		_a_xsi_type = "vr:WebBrowser"
	
	class WebService(interface):
		_a_xsi_type = "vr:WebService"

	class wsdlURL(VORElement): pass

	class accessURL(VORElement):
		_a_use = None
	
	class securityMethod(VORElement):
		def isEmpty(self):
			return self.standardId is None
		_a_standardId = None
	

class RI:
	"""is a container for classes modelling elements from IVOA Registry Interface.
	"""
	class RIElement(Element):
		_namespace = RINamespace
	
	class VOResources(RIElement): pass

	class Resource(VOR.Resource):
		_name = ElementTree.QName(RINamespace, "Resource")


class VOG:
	"""is a container for classes modelling elements from VO Registry.
	"""
	class VOGElement(Element):
		_namespace = VOGNamespace
		_local = True

	class Resource(RI.Resource):
		_a_xsi_type = "vg:Registry"
		_a_xmlns_vg = VOGNamespace
		_name_a_xmlns_vg = "xmlns:vg"

	class Authority(RI.Resource):
		_a_xsi_type = "vg:Authority"
		_a_xmlns_vg = VOGNamespace
		_name_a_xmlns_vg = "xmlns:vg"

	class capability(VOR.capability):
		_a_standardID = "ivo://ivoa.net/std/Registry"
	
	class Harvest(capability):
		_a_xsi_type = "vg:Harvest"
		_a_xmlns_vg = VOGNamespace
		_name_a_xmlns_vg = "xmlns:vg"

	class Search(VOGElement):
		_a_xsi_type = "vg:Search"
		_a_xmlns_vg = VOGNamespace
		_name_a_xmlns_vg = "xmlns:vg"

	class OAIHTTP(VOR.interface):
		_a_xsi_type = "vg:OAIHTTP"
		# namespace declaration has happened in enclosing element

	class OAISOAP(VOR.interface):
		_a_xsi_type = "vg:OAISOAP"
		# namespace declaration has happened in enclosing element

	class description(VOGElement): pass
		
	class full(VOGElement): pass
	
	class managedAuthority(VOGElement): pass
	
	class validationLevel(VOGElement): pass
	
	class description(VOGElement): pass
	
	class interface(VOGElement): pass
	
	class maxRecords(VOGElement): pass

	class extensionSearchSupport(VOGElement): pass
	
	class optionalProtocol(VOGElement): pass
	
	class managingOrg(VOGElement): pass

	
class DC:
	"""is a container for classes modelling elements from Dublin Core.
	"""
	class DCElement(Element):
		_namespace = DCNamespace

	class contributor(DCElement): pass

	class coverage(DCElement): pass

	class creator(DCElement): pass

	class date(DCElement): pass

	class description(DCElement): pass

	class format(DCElement): pass

	class identifier(DCElement): pass

	class language(DCElement): pass

	class publisher(DCElement): pass

	class relation(DCElement): pass

	class rights(DCElement): pass

	class source(DCElement): pass

	class subject(DCElement): pass

	class title(DCElement): pass

	class type(DCElement): pass


def addBasicVSElements(baseNS, VSElement):
	"""returns an element namespace containing common VODataService elements.
	"""
	class TNS(baseNS):
		class facility(VSElement): pass
		
		class instrument(VSElement): pass
		
		class coverage(VSElement): pass
		
		class format(VSElement): 
			_a_isMIMEType = None
		
		class rights(VSElement): pass
		
		class accessURL(VSElement): pass
		
		class ParamHTTP(VOR.interface):
			_a_xsi_type = "vs:ParamHTTP"
			_a_xmlns_vs = VSNamespace
			_name_a_xmlns_vs = "xmlns:vs"

		class resultType(VSElement): pass
		
		class queryType(VSElement): pass

		class param(VSElement): pass
		
		class name(VSElement): pass
		
		class description(VSElement): pass

		class unit(VSElement): pass
		
		class ucd(VSElement): pass

		class DataCollection(RI.Resource):
			c_facility = []
			c_instrument = []
			c_coverage = []
			c_format = []
			c_rights = []
			c_accessURL = []

		class Service(RI.Resource):
			c_interface = []

		class DataService(Service):
			_a_xsi_type = "vs:DataService"
			_a_xmlns_vs = VSNamespace
			_name_a_xmlns_vs = "xmlns:vs"
			c_table = []

		class TableService(Service):
			c_facility = []
			c_instrument = []
			c_table = []
			_a_xsi_type = "vs:TableService"
			_a_xmlns_vs = VSNamespace
			_name_a_xmlns_vs = "xmlns:vs"

		class CatalogService(Service):
			_a_xsi_type = "vs:CatalogService"
			_a_xmlns_vs = VSNamespace
			_name_a_xmlns_vs = "xmlns:vs"

		class ServiceReference(VSElement):
			_a_ivo_id = None
			_name_a_ivo_id = "ivo-id"

		class table(VSElement):
			_a_role = None

			c_column = []
			c_description = None
			c_name = None

		class column(VSElement):
			c_dataType = None
			c_description = None
			c_name = None
			c_ucd = None
			c_unit = None

	
		class dataType(VSElement, XSITypeMixin):
			# dataType is something of a mess with subtle changes from 1.0 to
			# 1.1.  There are various type systems, and all of this is
			# painful.  I don't try to untangle this here.
			_name = "dataType"
			_a_arraysize = None
			_a_delim = None
			_a_extendedSchema = None
			_a_extendedType = None

			def addChild(self, item):
				assert isinstance(item, basestring)
				self._defineType(item)

			def _defineType(self, item):
				self._text = item

		class simpleDataType(dataType):
			_name = "dataType"  # dataType with vs:SimpleDataType sounds so stupid
				# that I must have misunderstood something.
			
			typeMap = {
				"char": "string",
				"short": "integer",
				"int": "integer",
				"long": "integer",
				"float": "real",
				"double": "real",
			}

			def _defineType(self, type):
				self._text = self.typeMap.get(type, type)
		
		class voTableDataType(dataType):
			_a_xsi_type = "vs1:VOTableType"

			def _defineType(self, type):
				typeName, arrLen = typesystems.toVOTableConverter.convert(type)
				self._text = typeName
				self(arraysize=str(arrLen))


	return TNS

# Elements common to VODataService 1.0 and 1.1 are added by addBasicVSElements

class _VS1_0Stub(object):
	"""The stub for VODataService 1.0.
	"""
	class VSElement(Element):
		_namespace = VSNamespace
		_local = True

VS = addBasicVSElements(_VS1_0Stub, _VS1_0Stub.VSElement)

class _VS1_1Stub:
	"""The stub for VODataService 1.1.
	"""
	class VSElement(Element):
		_namespace = VS1Namespace
		_local = True

	class tableset(VSElement, XSITypeMixin):
		_mayBeEmpty = True
		_childSequence = ["schema"]
	
	class schema(VSElement):
		_childSequence = ["name", "title", "description", "utype",
			"table"]
	
	class title(VSElement): pass
	class utype(VSElement): pass
	
	class table(VSElement):
		_childSequence = ["name", "title", "description", "utype",
			"column", "foreignKey"]

	class foreignKey(VSElement):
		_childSequence = ["targetTable", "fkColumn", "description", "utype"]
	
	class targetTable(VSElement): pass
	
	class fkColumn(VSElement):
		_childSequence = ["fromColumn", "targetColumn"]

	class fromColumn(VSElement): pass
	class targetColumn(VSElement): pass

VS1 = addBasicVSElements(_VS1_1Stub, _VS1_1Stub.VSElement)


class SIA(object):
	"""is a container for classes modelling elements for describing simple
	image access services.
	"""
	class SIAElement(Element):
		_namespace = SIANamespace
		_local = True

	class interface(VOR.interface):
		_namespace = SIANamespace
		_a_role = "std"
		_a_xsi_type = "vs:ParamHTTP"
		_a_xmlns_vs = VSNamespace
		_name_a_xmlns_vs = "xmlns:vs"

	class capability(VOR.capability):
		_a_standardID = 	"ivo://ivoa.net/std/SIA"
		_a_xsi_type = "sia:SimpleImageAccess"
		_a_xmlns_sia = SIANamespace
		_name_a_xmlns_sia = "xmlns:sia"
	
	class imageServiceType(SIAElement): pass
	
	class maxQueryRegionSize(SIAElement): pass
	
	class maxImageExtent(SIAElement): pass
	
	class maxImageSize(SIAElement): pass

	class maxFileSize(SIAElement): pass

	class maxRecords(SIAElement): pass

	class long(SIAElement): pass
	
	class lat(SIAElement): pass

	class testQuery(SIAElement): pass
	
	class pos(SIAElement): pass
	
	class size(SIAElement): pass

	
class SCS(object):
	"""is a container for elements describing Simple Cone Search services.
	"""
	class SCSElement(Element):
		_namespace = SCSNamespace
		_local = True

	class Resource(RI.Resource):
		_a_xsi_type = "cs:ConeSearch"
		_a_xmlns_cs = SCSNamespace
		_name_a_xmlns_cs = "xmlns:cs"

	class interface(VOR.interface):
		_namespace = SCSNamespace
		_a_role = "std"
		_a_xsi_type = "vs:ParamHTTP"
		_a_xmlns_vs = VSNamespace
		_name_a_xmlns_vs = "xmlns:vs"

	class capability(VOR.capability):
		_a_standardID = 	"ivo://ivoa.net/std/ConeSearch"
		_a_xmlns_cs = SCSNamespace
		_name_a_xmlns_cs = "xmlns:cs"
		_a_xsi_type = "cs:ConeSearch"
	
	class maxSR(SCSElement): pass
	
	class maxRecords(SCSElement): pass
	
	class verbosity(SCSElement): pass

	class testQuery(SCSElement): pass
	class ra(SCSElement): pass
	class dec(SCSElement): pass
	class sr(SCSElement): pass
	class extras(SCSElement): pass


class TAP:
	"""is a container for elements describing TAP services.

	A schema for this doesn't exist as of 2010-07, so I'm basically defining
	an interface element with a couple of attributes as suggested by Ray
	Plante in http://www.ivoa.net/forum/dal/0910/1620.htm.
	"""
	class interface(VOR.interface):
		_a_role = "std"
		_a_xsi_type = "vs:ParamHTTP"
		_a_xmlns_vs = VSNamespace
		_name_a_xmlns_vs = "xmlns:vs"

	class capability(VOR.capability):
		_a_standardID = 	"ivo://ivoa.net/std/TAP"
