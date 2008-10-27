"""
Code to expose our services via SOAP and WSDL.
"""

import cStringIO
import datetime
import sys

from elementtree import ElementTree

import ZSI
from ZSI import TC

import gavo
from gavo import sqlsupport
from gavo import typesystems
from gavo import valuemappers
from gavo.stanxml import Element, XSINamespace
from gavo.web import registry


SOAPNamespace = 'http://schemas.xmlsoap.org/wsdl/soap/'
HTTPNamespace = 'http://schemas.xmlsoap.org/wsdl/http/'
MIMENamespace = 'http://schemas.xmlsoap.org/wsdl/mime/'
WSDLNamespace = 'http://schemas.xmlsoap.org/wsdl/'
XSDNamespace = "http://www.w3.org/2001/XMLSchema"

ElementTree._namespace_map[SOAPNamespace] = "soap"
ElementTree._namespace_map[HTTPNamespace] = "http"
ElementTree._namespace_map[MIMENamespace] = "mime"
ElementTree._namespace_map[WSDLNamespace] = "wsdl"
ElementTree._namespace_map[XSDNamespace] = "xsd"


def _schemaURL(xsdName):
	return "http://vo.ari.uni-heidelberg.de/docs/schemata/"+xsdName

_schemaLocations = {
	SOAPNamespace: _schemaURL("wsdlsoap-1.1.xsd"),
	WSDLNamespace: _schemaURL("wsdl-1.1.xsd"),
	XSDNamespace: _schemaURL("XMLSchema.xsd"),
}


class WSDL(object):
	"""is a container for elements from the wsdl 1.1 schema.
	"""
	class WSDLElement(Element):
		namespace = WSDLNamespace

	class _tParam(WSDLElement):
		a_message = None
		a_name = None

	class binding(WSDLElement):
		a_name = None
		a_type = None

	class definitions(WSDLElement):
		a_name = None
		a_targetNamespace = None
		a_xmlns_tns = None
		xmlns_tns_name = "xmlns:tns"
		a_xmlns_xsd = XSDNamespace
		xmlns_xsd_name = "xmlns:xsd"
#		a_xsi_schemaLocation =  " ".join(["%s %s"%(ns, xs) 
#			for ns, xs in _schemaLocations.iteritems()])
#		xsi_schemaLocation_name = "xsi:schemaLocation"
		a_xmlns_xsi = XSINamespace
		xmlns_xsi_name = "xmlns:xsi"
	
	class documentation(WSDLElement): pass
	
	class fault(WSDLElement):
		a_name = None
	
	class import_(WSDLElement):
		name = "import"
		a_location = None
		a_namespace = None

	class input(_tParam): 
		mayBeEmpty = True

	class message(WSDLElement):
		a_name = None
	
	class operation(WSDLElement):
		a_name = None
		a_parameterOrder = None

	class output(_tParam):
		mayBeEmpty = True
		a_name = None
		a_message = None

	class part(WSDLElement):
		mayBeEmpty = True
		a_name = None
		a_type = None

	class port(WSDLElement):
		mayBeEmpty = True
		a_binding = None
		a_name = None

	class portType(WSDLElement):
		a_name = None

	class service(WSDLElement):
		a_name = None
	
	class types(WSDLElement): pass
	

class SOAP(object):
	class SOAPElement(Element):
		namespace = SOAPNamespace

	class binding(SOAPElement):
		mayBeEmpty = True
		a_style = "rpc"
		a_transport = "http://schemas.xmlsoap.org/soap/http"

	class body(SOAPElement):
		mayBeEmpty = True
		a_use = "encoded"
		a_namespace = None
		a_encodingStyle = "http://schemas.xmlsoap.org/soap/encoding"
	
	class operation(SOAPElement):
		a_name = None
		a_soapAction = None
		a_style = "rpc"
	
	class address(SOAPElement):
		mayBeEmpty = True
		a_location = None


class XSD(object):
	"""is a container for elements from XML schema.
	"""
	class XSDElement(Element):
		namespace = XSDNamespace
		local = True

	class schema(XSDElement):
		a_xmlns = XSDNamespace
		a_targetNamespace = None

	class element(XSDElement):
		mayBeEmpty = True
		a_name = None
		a_type = None
	
	class complexType(XSDElement):
		a_name = None
	
	class all(XSDElement): pass

	class list(XSDElement):
		mayBeEmpty = True
		a_itemType = None
	
	class simpleType(XSDElement):
		a_name = None
	

def makeTypesForService(service, queryMeta):
	"""returns xmlstan definitions for the (SOAP) type of service.

	Only "atomic" input parameters are supported so far, so we can
	skip those.  The output type is always called outList and contains
	of outRec elements.
	"""
	return WSDL.types[
		XSD.schema(targetNamespace=registry.computeIdentifier(service))[
			XSD.element(name="outRec")[
				XSD.complexType[
					XSD.all[[
						XSD.element(name=f.get_dest(), type=typesystems.sqltypeToXSD(
							f.get_dbtype()))[
								WSDL.documentation[f.get_description()],
								WSDL.documentation[f.get_unit()]]
							for f in service.getCurOutputFields(queryMeta)]]]],
			XSD.element(name="outList")[
				XSD.simpleType[
					XSD.list(itemType="outRec")]]]]


def makeMessagesForService(service):
	"""returns xmlstan definitions for the SOAP messages exchanged when
	using the service.

	Basically, the input message (called srvInput) consists of some 
	combination of the service's input fields, the output message
	(called srvOutput) is just an outArr.
	"""
	return [
		WSDL.message(name="srvInput")[[
			WSDL.part(name=f.get_dest(), type="xsd:"+typesystems.sqltypeToXSD(
				f.get_dbtype()))[
					WSDL.documentation[f.get_description()],
					WSDL.documentation[f.get_unit()]]
				for f in service.getInputFields()]],
		WSDL.message(name="srvOutput")[
			WSDL.part(name="srvOutput", type="tns:outList")]]


def makePortTypeForService(service):
	"""returns xmlstan for a port type named serviceSOAP.
	"""
	parameterOrder = " ".join([f.get_dest() for f in service.getInputFields()])
	return WSDL.portType(name="serviceSOAP")[
		WSDL.operation(name="useService", parameterOrder=parameterOrder) [
			WSDL.input(name="inPars", message="tns:srvInput"),
			WSDL.output(name="outPars", message="tns:srvOutput"),
# XXX TODO: Define fault
		]]


def makeSOAPBindingForService(service):
	"""returns xmlstan for a SOAP binding of service.
	"""
	tns = registry.computeIdentifier(service)
	return WSDL.binding(name="soapBinding", type="tns:serviceSOAP")[
		SOAP.binding,
		WSDL.operation(name="useService")[
			SOAP.operation(soapAction="", name="useService"),
			WSDL.input(name="inPars")[
				SOAP.body(use="encoded", namespace=tns)],
			WSDL.output(name="inPars")[
				SOAP.body(use="encoded", namespace=tns)],
		]
	]
			

def makeSOAPServiceForService(service):
	"""returns xmlstan for a WSDL service definition of the SOAP interface
	to service.
	"""
	shortName = str(service.getMeta("shortName"))
	return WSDL.service(name=shortName)[
		WSDL.port(name="soap_%s"%shortName, binding="tns:soapBinding")[
			SOAP.address(location=service.getURL("soap", method="POST")+"/go"),
		]
	]


def makeSOAPWSDLForService(service, queryMeta):
	"""returns an xmlstan definitions element describing service.

	The definitions element also introduces a namespace named after the
	ivoa id of the service, accessible through the tns prefix.
	"""
	serviceId = registry.computeIdentifier(service)
	return WSDL.definitions(targetNamespace=serviceId,
			xmlns_tns=serviceId,
			name="%s_wsdl"%str(service.getMeta("shortName")).replace(" ", "_"))[
		WSDL.import_,
		makeTypesForService(service, queryMeta),
		makeMessagesForService(service),
		makePortTypeForService(service),
		makeSOAPBindingForService(service),
		makeSOAPServiceForService(service),
	]


class ToTcConverter(typesystems.FromSQLConverter):
	"""is a quick and partial converter from SQL types to ZSI's type codes.
	"""
	typeSystem = "ZSITypeCodes"
	simpleMap = {
		"smallint": TC.Integer,
		"integer": TC.Integer,
		"int": TC.Integer,
		"bigint": TC.Integer,
		"real": TC.FPfloat,
		"float": TC.FPfloat,
		"boolean": ("boolean", "1"),
		"double precision": TC.FPdouble,
		"double":  TC.FPdouble,
		"text": TC.String,
		"char": TC.String,
		"date": TC.gDate,
		"timestamp": TC.gDateTime,
		"time": TC.gTime,
		"raw": TC.String,
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return TC.String

sqltypeToTC = ToTcConverter().convert


# rather than fooling around with ZSI.SoapWriter's serialization, I use
# the machinery used for VOTables and HTML to serialize weird values.
# It's in place anyway.

_wsdlMFRegistry = valuemappers.ValueMapperFactoryRegistry()
_registerMF = _wsdlMFRegistry.registerFactory

try:
	from mx import DateTime

	def mxDatetimeMapperFactory(colProps):
		"""returns mapper for mxDateTime objects to python time tuples.
		"""
		if isinstance(colProps["sample"], DateTime.DateTimeType):
			return lambda val: val.tuple()
		if isinstance(colProps["sample"], DateTime.DateTimeDeltaType):
			return lambda val: (0,0,0,)+val.tuple()[:3]+(-1,-1,-1)
	_registerMF(mxDatetimeMapperFactory)
except ImportError:
	pass


def datetimeMapperFactory(colProps):
	"""returns mapper for datetime objects to python time tuples.
	"""
	if isinstance(colProps["sample"], (datetime.date, datetime.datetime)):
		def mapper(val):
			return val.timetuple()
		return mapper
_registerMF(datetimeMapperFactory)


def serializePrimaryTable(data, service):
	"""returns a SOAP serialization of the DataSet data's primary table.
	"""
	table = data.getPrimaryTable()
	class Row(TC.Struct):
		def __init__(self):
			TC.Struct.__init__(self, None, [
		sqltypeToTC(f.get_dbtype())("tns:"+f.get_dest())
			for f in table.fieldDefs], 'tns:outRow')

	class Table:
		def __init__(self, name):
			pass
	Table.typecode = TC.Array('outRow', Row(), 'tns:outList')

	outF = cStringIO.StringIO()
	sw = ZSI.SoapWriter(outF, 
		nsdict={"tns": registry.computeIdentifier(service)})
	mapped = list(valuemappers.getMappedValues(table, _wsdlMFRegistry))
	sw.serialize(mapped, Table.typecode)
	sw.close()
	return outF.getvalue()


def unicodeXML(obj):
	"""returns an XML-clean version of obj's unicode representation.

	I'd expect ZSI to worry about this, but clearly they don't.
	"""
	return unicode(obj
		).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def formatFault(exc, service):
	if isinstance(exc, gavo.ValidationError):
		val = ZSI.Fault(ZSI.Fault.Client, unicodeXML(exc))
	else:
		val = ZSI.Fault(ZSI.Fault.Server, unicodeXML(exc))
	return val.AsSOAP(
		nsdict={"tns": registry.computeIdentifier(service)})


def _tryWSDL():
	from gavo.parsing import importparser
	from gavo import resourcecache
	from gavo.web import common
	rd = resourcecache.getRd("ucds/ui")
	sv = rd.get_service("ui")
	print makeSOAPWSDLForService(sv, common.QueryMeta()).render()


def _trySOAP():
	from gavo.parsing import importparser
	from gavo import resourcecache
	from gavo.web import common
	qm = common.QueryMeta()
	rd = resourcecache.getRd("ucds/ui")
	sv = rd.get_service("ui")
	core = sv.get_core()
	core._makeOutputDD()
	try:
		data = core._parseOutput(core._compute(""), qm)
		print serializePrimaryTable(data, sv)
	except Exception, exc:
		print formatFault(exc, sv)

if __name__=="__main__":
	_trySOAP()
