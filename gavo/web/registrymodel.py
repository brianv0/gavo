"""
Data model for the VO registry interface.
"""

from elementtree import ElementTree

import gavo
from gavo import utils
from gavo.parsing import meta


class Error(gavo.Error):
	pass

# We need that bugger on the top element since we allow xsi:type attributes.
XSINamespace = "http://www.w3.org/2001/XMLSchema-instance"

OAINamespace = "http://www.openarchives.org/OAI/2.0/"
RINamespace = "http://www.ivoa.net/xml/RegistryInterface/v0.1"
VOGNamespace = "http://www.ivoa.net/xml/VORegistry/v1.0"
VORNamespace = "http://www.ivoa.net/xml/VOResource/v1.0"
DCNamespace = "http://purl.org/dc/elements/1.1/"
VODNamespace ="http://www.ivoa.net/xml/VODataService/v0.5"
SCSNamespace = "http://www.ivoa.net/xml/ConeSearch/v0.3" 
SIANamespace="http://www.ivoa.net/xml/SIA/v0.7" 

# Since we usually have the crappy namespaced attribute values (yikes!),
# and ElementTree is (IMHO rightly) unaware of schemata, we need this 
# mapping badly.  Don't change it without making sure the namespaces 
# in question aren't referenced in attributes.
ElementTree._namespace_map[XSINamespace] = "xsi"
ElementTree._namespace_map[VORNamespace] = "vr"
ElementTree._namespace_map[VOGNamespace] = "vg"
ElementTree._namespace_map[OAINamespace] = "oai"
ElementTree._namespace_map[DCNamespace] = "dc"
ElementTree._namespace_map[RINamespace] = "ri"
ElementTree._namespace_map[VODNamespace] = "vod"
ElementTree._namespace_map[SCSNamespace] = "cs"
ElementTree._namespace_map[SIANamespace] = "sia"

encoding = "utf-8"
XML_HEADER = '<?xml version="1.0" encoding="%s"?>'%encoding


class _Autoconstructor(type):
	"""is a metaclass that constructs an instance of itself on getitem.

	We want this so we save a parentheses pair on Elements without
	attributes.
	"""
	def __getitem__(cls, items):
		return cls()[items]


class Element(object):
	"""is an element for serialization into XML.

	This is loosely modelled after nevow stan.

	Don't access the children attribute directly.  I may want to add
	data model checking later, and that would go into addChild.

	When deriving form Elements, you may need attribute names that are not
	python identifiers (e.g., with dashes in them).  In that case, define
	an attribute <att>_name and point it to any string you want as the
	attribute.

	When building an ElementTree out of this, empty elements (i.e. those
	having an empty text and having no non-empty children) are usually
	discarded.  If you need such an element (e.g., for attributes), set
	mayBeEmpty to True.

	Since insane XSD mandates that local elements must not be qualified when
	elementFormDefault is unqualified, you need to set local=True on
	such local elements to suppress the namespace prefix.  Attribute names
	are never qualified here.  If you need qualified attributes, you'll
	have to use attribute name translation.

	Local elements like this will only work properly if you give the parent 
	elements the appropriate xmlns attribute.
	"""
	__metaclass__ = _Autoconstructor

	name = None
	namespace = ""
	mayBeEmpty = False
	local = False

	a_xsi_type = None
	xsi_type_name = ElementTree.QName(XSINamespace, "type")

	def __init__(self, **kwargs):
		self.children = []
		if self.name is None:
			self.name = self.__class__.__name__.split(".")[-1]
		self(**kwargs)

	def addChild(self, child):
		"""adds child to the list of children.

		Child may be an Element, a string, or a list or tuple of Elements and
		strings.  Finally, child may be None, in which case nothing will be
		added.
		"""
		if child is None:
			pass
		elif isinstance(child, (basestring, Element)):
			self.children.append(child)
		elif isinstance(child, meta.MetaItem):
			self.children.append(str(child))
		elif isinstance(child, (list, tuple)):
			for c in child:
				self.addChild(c)
		else:
			raise Error("%s element %s cannot be added to %s node"%(
				type(child), repr(child), self.name))

	def __getitem__(self, children):
		self.addChild(children)
		return self

	def __call__(self, **kw):
		if not kw:
			return self

		for k, v in kw.iteritems():
			if k[-1] == '_':
				k = k[:-1]
			elif k[0] == '_':
				k = k[1:]
			attname = "a_"+k
			# Only allow setting attributes already present
			getattr(self, attname)
			setattr(self, attname, v)
		return self

	def __iter__(self):
		raise NotImplementedError, "Element instances are not iterable."

	def isEmpty(self):
		for c in self.children:
			if isinstance(c, basestring):
				if c.strip():
					return False
			elif not c.isEmpty():
				return False
		return True

	def _makeAttrDict(self):
		res = {}
		for name in dir(self):
			if name.startswith("a_") and getattr(self, name)!=None:
				res[getattr(self, name[2:]+"_name", name[2:])] = getattr(self, name)
		return res

	def asETree(self, parent=None):
		"""returns an ElementTree instance for this node.
		"""
		try:
			if not self.mayBeEmpty and self.isEmpty():
				return
			if self.local:
				elName = self.name
			else:
				elName = ElementTree.QName(self.namespace, self.name)
			attrs = self._makeAttrDict()
			if parent==None:
				node = ElementTree.Element(elName, attrs)
			else:
				node = ElementTree.SubElement(parent, elName, attrs)
			for child in self.children:
				if isinstance(child, basestring):
					node.text = child.encode(encoding)
				else:
					child.asETree(node)
			return node
		except Error:
			raise
		except Exception, msg:
			utils.raiseTb(Error, str(msg)+" while building %s node"
				" with children %s"%(self.name, self.children))


class OAI:
	"""is a container for classes modelling OAI elements.
	"""
	class OAIElement(Element):
		namespace = OAINamespace

	class PMH(OAIElement):
		name = "OAI-PMH"
	
	class responseDate(OAIElement): pass

	class request(OAIElement):
		a_verb = None
		a_metadataPrefix = None

	class metadata(OAIElement): pass

	class Identify(OAIElement): pass

	class ListIdentifiers(OAIElement): pass

	class ListRecords(OAIElement): pass

	class header(OAIElement): pass
	
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
		

class VOR:
	"""is a container for classes modelling elements from VO Resource.
	"""
	class VORElement(Element):
		namespace = VORNamespace
		local = True

	class Resource(VORElement):
		local = False
		a_created = None
		a_updated = None
		a_status = None
		a_xmlns = VORNamespace
		
		c_title = None
		c_curation = None
		c_identifier = None
		c_shortName = None
		c_title = None

	class Organisation(Resource):
		c_facility = []
		c_instrument = []
		

	class validationLevel(VORElement): pass
	
	class title(VORElement): pass
	
	class shortName(VORElement): pass

	class ResourceName(VORElement):
		a_ivo_id = None

	class identifier(VORElement): pass

	class curation(VORElement): pass
	
	class content(VORElement): pass

	class creator(VORElement): pass
	
	class contributor(VORElement): pass
	
	class date(VORElement):
		a_role = None
	
	class version(VORElement): pass
	
	class contact(VORElement): pass
	
	class publisher(VORElement): pass

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
		a_standardID = None
	
	class interface(VORElement):
		a_version = None
		a_role = None
		a_qtype = None

	class accessURL(VORElement):
		a_use = None
	
	class securityMethod(VORElement): pass
	

class VOG:
	"""is a container for classes modelling elements from VO Registry.
	"""
	class VOGElement(Element):
		namespace = VOGNamespace

	class Registry(VOGElement):
		pass
	
	class full(VOGElement):
		pass
	
	class managedAuthority(VOGElement):
		pass
	
	class RegCapRestriction(VOGElement):
		a_standardID = None
	
	class validationLevel(VOGElement):
		pass
	
	class description(VOGElement):
		pass
	
	class interface(VOGElement):
		pass
	
	class Harvest(RegCapRestriction):
		pass
	
	class Search(RegCapRestriction):
		pass

	class maxRecords(VOGElement):
		pass

	class extensionSearchSupport(VOGElement):
		pass
	
	class optionalProtocol(VOGElement):
		pass
	
	class OAIHTTP(VOGElement):
		pass
	
	class OAISOAP(VOGElement):
		pass
	
	class Authority(VOGElement):
		pass
	
	class managingOrg(VOGElement):
		pass

	
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


class RI:
	"""is a container for classes modelling elements from IVOA Registry Interface.
	"""
	class RIElement(Element):
		namespace = RINamespace
	
	class VOResources(RIElement): pass

# XXX TODO: Resource is almost certainly wrong.
	class Resource(VOR.VORElement): pass
	

class VOD:
	"""is a container for classes modelling elements from IVOA VO data services.
	"""
	class VODElement(Element):
		namespace = VODNamespace
		local = True
	
	class Resource(VODElement):
		local = False
		a_xmlns = VODNamespace
		
	class facility(VODElement): pass
	
	class instrument(VODElement): pass
	
	class coverage(VODElement): pass
	
	class format(VODElement): 
		a_isMIMEType = None
	
	class rights(VODElement): pass
	
	class accessURL(VODElement): pass
	
	class facility(VODElement): pass

	class interface(VODElement):
		a_qtype = None

	class ParamHTTP(interface):
		c_resultType = None
		c_param = []

	class resultType(VODElement): pass
	
	class param(VODElement): pass
	
	class name(VODElement): pass
	
	class description(VODElement): pass
	
	class dataType(VODElement):
		a_arraysize = None
	
	class unit(VODElement): pass
	
	class ucd(VODElement): pass

	class DataCollection(VOR.Resource):
		c_facility = []
		c_instrument = []
		c_coverage = []
		c_format = []
		c_rights = []
		c_accessURL = []

	class Service(VOR.Resource):
		c_interface = []
	
	class SkyService(Service):
		c_facility = []
		c_instrument = []
		c_coverage = []
	
	class TabularSkyService(SkyService):
		c_table = []
	
	class table(VODElement):
		a_role = None

		c_column = []
		c_description = None
		c_name = None

	class column(VODElement):
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
	
	class capability(SIAElement):
		a_xmlns = SIANamespace
		local = False
	
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
	
	class capability(SCSElement):
		a_xmlns = SCSNamespace
		local = False
	
	class maxSR(SCSElement): pass
	
	class maxRecords(SCSElement): pass
	
	class verbosity(SCSElement): pass

