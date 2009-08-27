"""
Data model for the VO registry interface.
"""

from gavo import base
from gavo.utils import ElementTree
from gavo.utils.stanxml import Element, XSINamespace


class Error(base.Error):
	pass


OAINamespace = "http://www.openarchives.org/OAI/2.0/"
OAIDCNamespace = "http://www.openarchives.org/OAI/2.0/oai_dc/"
RINamespace = "http://www.ivoa.net/xml/RegistryInterface/v1.0"
VOGNamespace = "http://www.ivoa.net/xml/VORegistry/v1.0"
VORNamespace = "http://www.ivoa.net/xml/VOResource/v1.0"
DCNamespace = "http://purl.org/dc/elements/1.1/"
VSNamespace ="http://www.ivoa.net/xml/VODataService/v1.0"
SCSNamespace = "http://www.ivoa.net/xml/ConeSearch/v1.0" 
SIANamespace="http://www.ivoa.net/xml/SIA/v1.0" 

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
ElementTree._namespace_map[SCSNamespace] = "cs"
ElementTree._namespace_map[SIANamespace] = "sia"

def _schemaURL(xsdName):
	return "http://vo.ari.uni-heidelberg.de/docs/schemata/"+xsdName

_schemaLocations = {
	OAINamespace: _schemaURL("OAI-PMH.xsd"),
	OAIDCNamespace: _schemaURL("oai_dc.xsd"),
	VORNamespace: _schemaURL("VOResource-v1.0.xsd"),
	VOGNamespace: _schemaURL("VORegistry-v1.0.xsd"),
	DCNamespace: _schemaURL("simpledc20021212.xsd"),
	RINamespace: _schemaURL("RegistryInterface-v1.0.xsd"),
	VSNamespace: _schemaURL("VODataService-v1.0.xsd"),
	SCSNamespace: _schemaURL("ConeSearch-v1.0.xsd"),
	SIANamespace: _schemaURL("SIA-v1.0.xsd"),
}

class OAI:
	"""is a container for classes modelling OAI elements.
	"""
	class OAIElement(Element):
		namespace = OAINamespace

	class PMH(OAIElement):
		name = "OAI-PMH"
		a_xsi_schemaLocation = " ".join(["%s %s"%(ns, xs) 
			for ns, xs in _schemaLocations.iteritems()])
		xsi_schemaLocation_name = "xsi:schemaLocation"
		a_xmlns_xsi = XSINamespace
		xmlns_xsi_name = "xmlns:xsi"
		a_xmlns_sia = SIANamespace
		xmlns_sia_name = "xmlns:sia"
		a_xmlns_cs = SCSNamespace
		xmlns_cs_name = "xmlns:cs"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"

	class responseDate(OAIElement): pass

	class request(OAIElement):
		mayBeEmpty = True
		a_verb = None
		a_metadataPrefix = None

	class metadata(OAIElement): pass

	class Identify(OAIElement): pass

	class ListIdentifiers(OAIElement): pass

	class ListRecords(OAIElement): pass

	class GetRecord(OAIElement): pass
	
	class ListMetadataFormats(OAIElement): pass

	class ListSets(OAIElement): pass

	class header(OAIElement): pass

	class error(OAIElement):
		mayBeEmpty = True
		a_code = None

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
		namespace = OAIDCNamespace
	
	class dc(OAIDCElement):
		pass


class VOR:
	"""is a container for classes modelling elements from VO Resource.
	"""
	class VORElement(Element):
		namespace = VORNamespace
		local = True

	class Resource(VORElement):
# This is "abstract" in that only derived elements may be present
# in an instance document (since VOR doesn't define any global elements).
# Typically, this will be ri:Resource elements with some funky xsi:type
		a_created = None
		a_updated = None
		a_status = None
		
		name = ElementTree.QName(RINamespace, "Resource")
		local = False

		c_title = None
		c_curation = None
		c_identifier = None
		c_shortName = None
		c_title = None

	class Organisation(Resource):
		a_xsi_type = "vr:Organisation"
		a_xmlns_vr = VORNamespace
		xmlns_vr_name = "xmlns:vr"
		c_facility = []
		c_instrument = []
		
	class Service(Resource): pass

	class validationLevel(VORElement):
		a_validatedBy = None
	
	class title(VORElement): pass
	
	class shortName(VORElement): pass

	class ResourceName(VORElement):
		a_ivo_id = None
		ivo_id_name = "ivo-id"

	class identifier(VORElement): pass

	class curation(VORElement): pass
	
	class content(VORElement): pass

	class creator(VORElement): pass
	
	class contributor(ResourceName): pass
	
	class date(VORElement):
		a_role = None
	
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
	
	class capability(VORElement): 
		name = "capability"
		a_standardID = None
	
	class interface(VORElement):
		name = "interface"
		a_version = None
		a_role = None
		a_qtype = None

	class WebBrowser(interface):
		a_xsi_type = "vr:WebBrowser"
		a_xmlns_vr = VORNamespace
		xmlns_vr_name = "xmlns:vr"
	
	class WebService(interface):
		a_xsi_type = "vr:WebService"
		a_xmlns_vr = VORNamespace
		xmlns_vr_name = "xmlns:vr"

	class wsdlURL(VORElement): pass

	class accessURL(VORElement):
		a_use = None
	
	class securityMethod(VORElement):
		def isEmpty(self):
			return self.a_standardId is None
		a_standardId = None
	

class RI:
	"""is a container for classes modelling elements from IVOA Registry Interface.
	"""
	class RIElement(Element):
		namespace = RINamespace
	
	class VOResources(RIElement): pass

	class Resource(VOR.Resource):
		name = ElementTree.QName(RINamespace, "Resource")


class VOG:
	"""is a container for classes modelling elements from VO Registry.
	"""
	class VOGElement(Element):
		namespace = VOGNamespace
		local = True

	class Resource(RI.Resource):
		a_xsi_type = "vg:Registry"
		a_xmlns_vg = VOGNamespace
		xmlns_vg_name = "xmlns:vg"

	class Authority(RI.Resource):
		a_xsi_type = "vg:Authority"
		a_xmlns_vg = VOGNamespace
		xmlns_vg_name = "xmlns:vg"

	class capability(VOR.capability):
		a_standardID = "ivo://ivoa.net/std/Registry"
	
	class Harvest(capability):
		a_xsi_type = "vg:Harvest"
		a_xmlns_vg = VOGNamespace
		xmlns_vg_name = "xmlns:vg"

	class Search(VOGElement):
		a_xsi_type = "vg:Search"
		a_xmlns_vg = VOGNamespace
		xmlns_vg_name = "xmlns:vg"

	class OAIHTTP(VOR.interface):
		a_xsi_type = "vg:OAIHTTP"
		# namespace declaration has happened in enclosing element

	class OAISOAP(VOR.interface):
		a_xsi_type = "vg:OAISOAP"
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
		namespace = DCNamespace

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


class VS:
	"""is a container for classes modelling elements from IVOA VO data services.
	"""
	class VSElement(Element):
		namespace = VSNamespace
		local = True
	
	class facility(VSElement): pass
	
	class instrument(VSElement): pass
	
	class coverage(VSElement): pass
	
	class format(VSElement): 
		a_isMIMEType = None
	
	class rights(VSElement): pass
	
	class accessURL(VSElement): pass
	
	class ParamHTTP(VOR.interface):
		a_xsi_type = "vs:ParamHTTP"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"

	class resultType(VSElement): pass
	
	class param(VSElement): pass
	
	class name(VSElement): pass
	
	class description(VSElement): pass
	
	class dataType(VSElement):
		a_arraysize = None

	class simpleDataType(VSElement):
		name = "dataType"  # dataType with vs:SimpleDataType sounds so stupid
			# that I must have misunderstood something.  Well, I just hack it and
			# do an ad-hoc type translation at tree building time.  Yikes.
		
		typeMap = {
			"char": "string",
			"short": "integer",
			"int": "integer",
			"long": "integer",
			"float": "real",
			"double": "real",
		}
		def asETree(self, parent):
			if self.isEmpty():
				return
			self.children = [self.typeMap.get(self.children[0], self.children[0])]
			return super(VS.simpleDataType, self).asETree(parent)

	
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
		a_xsi_type = "vs:DataService"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"
		c_table = []

	class TableService(Service):
		c_facility = []
		c_instrument = []
		c_table = []
		a_xsi_type = "vs:TableService"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"

	class CatalogService(Service):
		a_xsi_type = "vs:CatalogService"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"

	class ServiceReference(VSElement):
		a_ivo_id = None
		ivo_id_name = "ivo-id"

	class table(VSElement):
		a_role = None

		c_column = []
		c_description = None
		c_name = None

	class column(VSElement):
		c_dataType = None
		c_description = None
		c_name = None
		c_ucd = None
		c_unit = None


class SIA:
	"""is a container for classes modelling elements for describing simple
	image access services.
	"""
	class SIAElement(Element):
		namespace = SIANamespace
		local = True

	class interface(VOR.interface):
		namespace = SIANamespace
		a_role = "std"
		a_xsi_type = "vs:ParamHTTP"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"

	class capability(VOR.capability):
		a_standardID = 	"ivo://ivoa.net/std/SIA"
		a_xsi_type = "sia:SimpleImageAccess"
		a_xmlns_sia = SIANamespace
		xmlns_sia_name = "xmlns:sia"
	
	class imageServiceType(SIAElement): pass
	
	class maxQueryRegionSize(SIAElement): pass
	
	class maxImageExtent(SIAElement): pass
	
	class maxImageSize(SIAElement): pass

	class maxFileSize(SIAElement): pass

	class maxRecords(SIAElement): pass

	class long(SIAElement): pass
	
	class lat(SIAElement): pass

	
class SCS:
	"""is a container for elements describing Simple Cone Search services.
	"""
	class SCSElement(Element):
		namespace = SCSNamespace
		local = True

	class Resource(RI.Resource):
		a_xsi_type = "cs:ConeSearch"
		a_xmlns_cs = SCSNamespace
		xmlns_cs_name = "xmlns:cs"

	class interface(VOR.interface):
		namespace = SCSNamespace
		a_role = "std"
		a_xsi_type = "vs:ParamHTTP"
		a_xmlns_vs = VSNamespace
		xmlns_vs_name = "xmlns:vs"

	class capability(SCSElement):
		a_standardID = 	"ivo://ivoa.net/std/ConeSearch"
		a_xsi_type = "cs:ConeSearch"
		a_xmlns_sia = SCSNamespace
		xmlns_sia_name = "xmlns:cs"
	
	class maxSR(SCSElement): pass
	
	class maxRecords(SCSElement): pass
	
	class verbosity(SCSElement): pass

	class testQuery(SCSElement): pass
	class ra(SCSElement): pass
	class dec(SCSElement): pass
	class sr(SCSElement): pass
	class extras(SCSElement): pass
