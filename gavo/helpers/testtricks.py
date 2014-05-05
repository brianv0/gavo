"""
helper functions and classes for unit tests and similar.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import contextlib
import gzip
import os
import subprocess
import tempfile
import unittest
import urllib

from gavo import base


def getXSDErrorsXerces(data, leaveOffending=False):
	"""returns Xerces error messages for XSD validation of data, or None
	if data is valid.

	See the docstring of XSDTestMixin for how to make this work.

	This raises a unittest.SkipTest exception if the validator cannot be
	found.
	"""
	# schemata/makeValidator.py dumps its validator class in the cacheDir
	validatorDir = base.getConfig("cacheDir")
	if not os.path.exists(os.path.join(validatorDir, "xsdval.class")):
		raise unittest.SkipTest("java XSD valdiator not found -- run"
			" schemata/makeValidator.py")

	classpath = ":".join([validatorDir]+base.getConfig("xsdclasspath"))
	handle, inName = tempfile.mkstemp("xerctest", "rm")
	try:
		with os.fdopen(handle, "w") as f:
			f.write(data)
		args = ["java", "-cp", classpath, "xsdval", 
			"-n", "-v", "-s", "-f", inName]

		f = subprocess.Popen(args,
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		xercMsgs = f.stdout.read()
		status = f.wait()
		if status or "Error]" in xercMsgs:
			if leaveOffending:
				with open("badDocument.xml", "w") as of:
					of.write(data)
			return xercMsgs
	finally:
		os.unlink(inName)
	return None


class XSDTestMixin(object):
	"""provides a assertValidates method doing XSD validation.

	assertValidates raises an assertion error with the validator's
	messages on an error.  You can optionally pass a leaveOffending
	argument to make the method store the offending document in
	badDocument.xml.

	The whole thing needs Xerces-J in the form of xsdval.class in the
	current directory.

	The validator itself is a java class xsdval.class built by 
	../schemata/makeValidator.py.  If you have java installed, calling
	that in the schemata directory should just work (TM).  With that
	validator and the schemata in place, no network connection should
	be necessary to run validation tests.
	"""
	def assertValidates(self, xmlSource, leaveOffending=False):
		xercMsgs = getXSDErrorsXerces(xmlSource, leaveOffending)
		if xercMsgs:
			raise AssertionError(xercMsgs)


@contextlib.contextmanager
def testFile(name, content, writeGz=False, inDir=base.getConfig("tempDir")):
	"""a context manager that creates a file name with content in inDir.

	The full path name is returned.

	With writeGz=True, content is gzipped on the fly (don't do this if
	the data already is gzipped).

	You can pass in name=None to get a temporary file name if you don't care
	about the name.
	"""
	if name is None:
		handle, destName = tempfile.mkstemp(dir=inDir)
		os.close(handle)
	else:
		if not os.path.isdir(inDir):
			os.makedirs(inDir)
		destName = os.path.join(inDir, name)

	if writeGz:
		f = gzip.GzipFile(destName, mode="wb")
	else:
		f = open(destName, "w")

	f.write(content)
	f.close()
	try:
		yield destName
	finally:
		try:
			os.unlink(destName)
		except os.error:
			pass


VO_SCHEMATA = [
"simpledc20021212.xsd",
"Characterisation-v1.11.xsd",
"ConeSearch-v1.0.xsd",
"oai_dc.xsd",
"OAI-PMH.xsd",
"RegistryInterface-v1.0.xsd",
"SIA-v1.0.xsd",
"soap.xsd",
"SSA-v1.0.xsd",
"StandardsRegExt-1.0.xsd",
"stc-v1.30.xsd",
"TAPRegExt-v1.0.xsd",
"uws-1.0.xsd",
"VODataService-v1.0.xsd",
"VODataService-v1.1.xsd",
"VOEvent-1.0.xsd",
"VORegistry-v1.0.xsd",
"VOResource-v1.0.xsd",
"VOSIAvailability-v1.0.xsd",
"VOSICapabilities-v1.0.xsd",
"VOSITables-v1.0.xsd",
"VOTable-1.1.xsd",
"VOTable-1.2.xsd",
"wsdl-1.1.xsd",
"wsdlhttp-1.1.xsd",
"wsdlmime-1.1.xsd",
"wsdlsoap-1.1.xsd",
"xlink.xsd",
"XMLSchema.xsd",
"xml.xsd",]

try:
	# XSD validation only with etree
	from lxml import etree

	class QNamer(object):
		"""A hack that generates QNames through getattr.

		Construct with the desired namespace.
		"""
		def __init__(self, ns):
			self.ns = ns
		
		def __getattr__(self, name):
			return etree.QName(self.ns, name.strip("_"))

	XS = QNamer("http://www.w3.org/2001/XMLSchema")

	def getJointValidator(schemaPaths):
		"""returns an lxml validator containing the schemas in schemaPaths.

		schemaPaths must be actual file names.  http and other URLs will not 
		work.
		"""
		subordinates = []
		for fName in schemaPaths:
			with open(fName) as f:
				root = etree.parse(f).getroot()
			subordinates.append((
				"file://"+urllib.quote(os.path.abspath(fName)), 
					root.get("targetNamespace")))

		root = etree.Element(
			XS.schema, attrib={"targetNamespace": "urn:combiner"})
		for schemaLocation, tns in subordinates:
			etree.SubElement(root, XS.import_, attrib={
				"namespace": tns, "schemaLocation": schemaLocation})
		
		doc = etree.ElementTree(root)
		return etree.XMLSchema(doc)

	
	def getDefaultValidator(extraSchemata=[]):
		"""returns a validator that knows the schemata typically useful within
		the VO.

		*Note*: This doesn't work right now since libxml2 insists on
		loading schema files referenced in schema files' schemaLocations.
		Until there's an improved API, this has to wait.

		This will currently only work if DaCHS is installed from an SVN
		checkout with setup.py develop.

		What's returned has a method assertValid(et) that raises an exception 
		if the elementtree et is not valid.  You can simply call it to
		get back True for valid and False for invalid.
		"""
		basePath = "/"+os.path.join(*(__file__.split("/")[:-3]+["schemata"]))
		return getJointValidator(
			[os.path.join(basePath, sp) for sp in VO_SCHEMATA]+extraSchemata)

except ImportError:
	# no lxml
	pass

