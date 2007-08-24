"""
This module is a helper to succinctly produce WSDL specs for gavo web
interfaces.

Right now, we only want to support HTTP request/response services.
"""

import sys

try:
	import cElementTree as ET
except ImportError:
	import elementtree.ElementTree as ET

from gavo import typesystems


# Namespace handling: Since I need namespaces in attributes and 
# elementtree doesn't do these, and I can't make old versions of
# elementtree use my namespace identifiers, I'm going a rather manual
# approach to namespaces.  When we can rely on an elementtree with
# convenient namespace handling, we should change the definition of the
# _n_<bla> functions so they do {long namespace}name and remove the
# manual xmlns things from makeWSDLDefinitions.
_namespaces = {
	'soap': 'http://schemas.xmlsoap.org/wsdl/soap/',
	'http': 'http://schemas.xmlsoap.org/wsdl/http/',
	'mime': 'http://schemas.xmlsoap.org/wsdl/mime/',
	'xs': 'http://www.w3.org/2001/XMLSchema',
	'tns': 'urn:GAVO',
}

for short, uri in _namespaces.iteritems():
	if hasattr(ET, "_namespace_map"):
		ET._namespace_map[uri] = short
#	exec """def _n_%s(tagName):
#			return "{%s}%%s"%%tagName"""%(short, uri)
	exec """def _n_%s(tagName):
			return "%s:%%s"%%tagName"""%(short, short)


defaultNamespace = 'http://schemas.xmlsoap.org/wsdl/'

def _n_(tagName):
	return tagName


def bE(name, attrs={}, children=()):
	el = ET.Element(name, **attrs)
	for child in children:
		el.append(child)
	return el


builtinNodes = [
	bE(_n_("message"), {_n_("name"): "opaqueBinary"}, [
		bE(_n_("part"), {_n_("name"): "response", 
			_n_("type"): _n_xs("binary")})]),
]

def makeWSDLDefinitions(name, childNodes):
	"""returns an elementtree definitions element serializable into a
	WSDL XML document.

	childNodes is a sequence of elementtree nodes; the function will
	make sure they're serialized in the correct sequence.  You can therefore
	add the individual subelements in any way you like.
	"""
	orderedNodes = []
	childNodes = builtinNodes+childNodes
	for subElName in map(_n_, ["import", "documentation", "types", "message",
			"portType", "binding", "service"]):
		orderedNodes.extend([node for node in childNodes
			if node.tag==subElName])
	rootAttrs = dict([
		("xmlns:"+short, long) for short, long in _namespaces.iteritems()])
	rootAttrs["xmlns"] = defaultNamespace
	rootAttrs["targetNamespace"] = _namespaces["tns"]
	rootAttrs["name"] = name
	return ET.ElementTree(
		bE(_n_("definitions"), rootAttrs, orderedNodes))


def _makeWsdlFromFieldinfo(fieldInfo):
	return {
		_n_("name"): fieldInfo["fieldName"],
		_n_("type"): "xs:"+typesystems.sqltypeToXSD(fieldInfo["type"]),
	}

def makeHTTPBinding(name, uri, inputArgs, outputType):
	"""returns a sequence of elements describing an HTTP service taking
	inputArgs and returning an opaque binary of MIME type outputType.

	inputArgs is a sequence of sqlsupport-type fieldinfos
	"""
	portType = "%s_t1"%name
	opName = "%s_o1"%name
	messageName = "%s_mIn"%name
	items = [bE(_n_("binding"), {
		"name": name,
		"type": portType,
	}, [
		bE(_n_http("binding"), {_n_("verb"): "GET"}),
		bE(_n_("operation"), {_n_("name"): opName}, [
			bE(_n_http("operation"), {_n_("location"): uri}),
			bE(_n_("input"), {}, [
				bE(_n_http("urlEncoded"))
			]),
			bE(_n_("output"), {}, [
				bE(_n_mime("content"), {_n_("type"): outputType})
			])
		])
	])]
	items.append(bE(_n_("portType"), {_n_("name"): portType}, [
		bE(_n_("operation"), {_n_("name"): opName}, [
			bE(_n_("input"), {_n_("message"): _n_tns(messageName)}),
			bE(_n_("output"), {_n_("message"): _n_tns("opaqueBinary")}),
		])
	]))
	items.append(bE(_n_("message"), {_n_("name"): messageName},
		[bE(_n_("part"), _makeWsdlFromFieldinfo(fieldInfo))
			for fieldInfo in inputArgs]))
	return (portType, name), items


def makeService(name, baseUrl, portBindings):
	return bE(_n_("service"), {_n_("name"): name},
		[bE(_n_("port"), 
				{_n_("name"): _n_tns(portName), _n_("binding"): _n_tns(bindingName)},
				[bE(_n_http("address"), {_n_("location"): baseUrl})])
			for portName, bindingName in portBindings])


if __name__=="__main__":
	from gavo import sqlsupport
	from gavo import config
	config.setDbProfile("querulator")
	mth = sqlsupport.MetaTableHandler()
	fieldInfos = mth.getFieldInfos("views.lenses")
	portBindings, children = [], []
	portBinding, elements = makeHTTPBinding("foo", "/ql/masqrun", fieldInfos, 
		"application/votable")
	portBindings.append(portBinding)
	children.extend(elements)
	children.append(makeService("Foo", "http://vo.ari.uni-heidelberg.de/ql/", portBindings))
	makeWSDLDefinitions("foo", children).write(sys.stdout)
	print
