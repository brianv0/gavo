import os
import sys
import cPickle
import xml.sax
import tempfile
import warnings

import SOAPpy
import SOAPpy.WSDL

from gavo import base
from gavo import utils
from gavo.utils import ElementTree


class ObjectCache(object):
	def __init__(self, id):
		self.id = id
		self._loadCache()

	def _getCacheName(self):
		return os.path.join(base.getConfig("cacheDir"), "oc"+self.id)

	def _loadCache(self):
		try:
			self.cache = cPickle.load(open(self._getCacheName()))
		except IOError:
			self.cache = {}
	
	def _saveCache(self, silent=False):
		try:
			handle, name = tempfile.mkstemp(dir=base.getConfig("cacheDir"))
			f = os.fdopen(handle, "w")
			cPickle.dump(self.cache, f)
			utils.safeclose(f)
			os.rename(name, self._getCacheName())
		except (IOError, os.error):
			if not silent:
				raise

	def addItem(self, key, record, save, silent=False):
		self.cache[key] = record
		if save:
			self._saveCache(silent)
	
	def sync(self):
		self._saveCache(silent=True)
	
	def getItem(self, key):
		return self.cache[key]


class Sesame(object):
	"""is a simple interface to the simbad name resolver.
	"""
	wsdl = """<?xml version="1.0" encoding="UTF-8"?>
			<wsdl:definitions targetNamespace="urn:Sesame" xmlns:apachesoap="http://xml.apache.org/xml-soap" xmlns:impl="urn:Sesame" xmlns:intf="urn:Sesame" xmlns:soapenc="http://schemas.xmlsoap.org/soap/encoding/" xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:wsdlsoap="http://schemas.xmlsoap.org/wsdl/soap/" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
			<!--WSDL created by Apache Axis version: 1.3
			Built on Oct 05, 2005 (05:23:37 EDT)-->
				 <wsdl:message name="SesameResponse">
						<wsdl:part name="return" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="SesameXMLRequest">
						<wsdl:part name="name" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="getAvailabilityRequest">
				 </wsdl:message>
				 <wsdl:message name="sesameRequest">
						<wsdl:part name="name" type="xsd:string"/>
						<wsdl:part name="resultType" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="sesameRequest2">
						<wsdl:part name="name" type="xsd:string"/>
						<wsdl:part name="resultType" type="xsd:string"/>
						<wsdl:part name="all" type="xsd:boolean"/>
						<wsdl:part name="service" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="sesameResponse2">
						<wsdl:part name="return" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="getAvailabilityResponse">
						<wsdl:part name="getAvailabilityReturn" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="SesameRequest">
						<wsdl:part name="name" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="sesameRequest1">
						<wsdl:part name="name" type="xsd:string"/>
						<wsdl:part name="resultType" type="xsd:string"/>
						<wsdl:part name="all" type="xsd:boolean"/>
				 </wsdl:message>
				 <wsdl:message name="sesameResponse1">
						<wsdl:part name="return" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="sesameResponse">
						<wsdl:part name="return" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:message name="SesameXMLResponse">
						<wsdl:part name="return" type="xsd:string"/>
				 </wsdl:message>
				 <wsdl:portType name="Sesame">
						<wsdl:operation name="sesame" parameterOrder="name resultType">
							 <wsdl:input message="impl:sesameRequest" name="sesameRequest"/>
							 <wsdl:output message="impl:sesameResponse" name="sesameResponse"/>
						</wsdl:operation>
						<wsdl:operation name="sesame" parameterOrder="name resultType all">
							 <wsdl:input message="impl:sesameRequest1" name="sesameRequest1"/>
							 <wsdl:output message="impl:sesameResponse1" name="sesameResponse1"/>
						</wsdl:operation>
						<wsdl:operation name="sesame" parameterOrder="name resultType all service">
							 <wsdl:input message="impl:sesameRequest2" name="sesameRequest2"/>
							 <wsdl:output message="impl:sesameResponse2" name="sesameResponse2"/>
						</wsdl:operation>
						<wsdl:operation name="SesameXML" parameterOrder="name">
							 <wsdl:input message="impl:SesameXMLRequest" name="SesameXMLRequest"/>
							 <wsdl:output message="impl:SesameXMLResponse" name="SesameXMLResponse"/>
						</wsdl:operation>
						<wsdl:operation name="Sesame" parameterOrder="name">
							 <wsdl:input message="impl:SesameRequest" name="SesameRequest"/>
							 <wsdl:output message="impl:SesameResponse" name="SesameResponse"/>
						</wsdl:operation>
						<wsdl:operation name="getAvailability">
							 <wsdl:input message="impl:getAvailabilityRequest" name="getAvailabilityRequest"/>
							 <wsdl:output message="impl:getAvailabilityResponse" name="getAvailabilityResponse"/>
						</wsdl:operation>
				 </wsdl:portType>
				 <wsdl:binding name="SesameSoapBinding" type="impl:Sesame">
						<wsdlsoap:binding style="rpc" transport="http://schemas.xmlsoap.org/soap/http"/>
						<wsdl:operation name="sesame">
							 <wsdlsoap:operation soapAction=""/>
							 <wsdl:input name="sesameRequest">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:input>
							 <wsdl:output name="sesameResponse">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:output>
						</wsdl:operation>
						<wsdl:operation name="sesame">
							 <wsdlsoap:operation soapAction=""/>
							 <wsdl:input name="sesameRequest1">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:input>
							 <wsdl:output name="sesameResponse1">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:output>
						</wsdl:operation>
						<wsdl:operation name="sesame">
							 <wsdlsoap:operation soapAction=""/>
							 <wsdl:input name="sesameRequest2">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:input>
							 <wsdl:output name="sesameResponse2">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:output>
						</wsdl:operation>
						<wsdl:operation name="SesameXML">
							 <wsdlsoap:operation soapAction=""/>
							 <wsdl:input name="SesameXMLRequest">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:input>
							 <wsdl:output name="SesameXMLResponse">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:output>
						</wsdl:operation>
						<wsdl:operation name="Sesame">
							 <wsdlsoap:operation soapAction=""/>
							 <wsdl:input name="SesameRequest">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:input>
							 <wsdl:output name="SesameResponse">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:output>
						</wsdl:operation>
						<wsdl:operation name="getAvailability">
							 <wsdlsoap:operation soapAction=""/>
							 <wsdl:input name="getAvailabilityRequest">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="http://DefaultNamespace" use="encoded"/>
							 </wsdl:input>
							 <wsdl:output name="getAvailabilityResponse">
									<wsdlsoap:body encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" namespace="urn:Sesame" use="encoded"/>
							 </wsdl:output>
						</wsdl:operation>
				 </wsdl:binding>
				 <wsdl:service name="SesameService">
						<wsdl:port binding="impl:SesameSoapBinding" name="Sesame">
							 <wsdlsoap:address location="http://cdsws.u-strasbg.fr/axis/services/Sesame"/>
						</wsdl:port>
				 </wsdl:service>
			</wsdl:definitions>"""

	def __init__(self, id="simbad", debug=False, saveNew=False):
		self.proxy = SOAPpy.WSDL.Proxy(self.wsdl)
		self.saveNew = saveNew
		self.debug = debug
		self._getCache(id)

	def _getCache(self, id):
		self.cache = ObjectCache(id)

	def _parseXML(self, simbadXML):
		try:
			et = ElementTree.fromstring(simbadXML)
		except Exception, msg: # simbad returned weird XML
			warnings.warn("Bad XML from simbad (%s)"%str(msg))
			return None
		
		def getVal(path, morph=unicode):
			el = et.find(path)
			if el is not None:
				return morph(el.text)

		res = {}
		res["otype"] = getVal("Target/Resolver/otype")
		res["oname"] = getVal("Target/name")
		res["RA"] = getVal("Target/Resolver/jradeg", float)
		res["dec"] = getVal("Target/Resolver/jdedeg", float)
		if res["RA"] is None:
			return None
		return res

	def query(self, ident):
		try:
			return self.cache.getItem(ident)
		except KeyError:
			newOb = self._parseXML(self.proxy.sesame(name=ident, 
				resultType="SNx"))
			self.cache.addItem(ident, newOb, save=self.saveNew)
			return newOb
	
	def getPositionFor(self, identifier):
		data = self.query(identifier)
		if not data:
			raise KeyError(identifier)
		return float(data["RA"]), float(data["dec"])
	

def getSimbadPositions(identifier):
	"""returns ra and dec from Simbad for identifier.

	It raises a KeyError if Simbad doesn't know identifier.
	"""
	return base.caches.getSesame("simbad").getPositionFor(identifier)


base.caches.makeCache("getSesame", lambda key: Sesame(key, saveNew=True))


if __name__=="__main__":
	s = Sesame(debug=True)
	print s.query("Wurzelfurz")
