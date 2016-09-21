"""
Helper functions and classes for unit tests and similar.

Whatever is useful to unit tests from here should be imported into
testhelpers, too.  Unit test modules should not be forced to import
this.
"""

#c Copyright 2008-2016, the GAVO project
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

from lxml import etree

from gavo import base
from gavo import utils


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


class XSDResolver(etree.Resolver):
	"""A resolver for external entities only returning in-tree files.
	"""
	def __init__(self):
		self.basePath = "schemata"

	def getPathForName(self, name):
		xsdName = name.split("/")[-1]
		return base.getPathForDistFile(
			os.path.join(self.basePath, xsdName))

	def resolve(self, url, pubid, context):
		try:
			path = self.getPathForName(url)
			res = self.resolve_filename(path, context)
			return res
		except:
			base.ui.notifyError("Did not find local file for schema %s --"
				" this will fall back to network resources and thus probably"
				" be slow"%url)


RESOLVER = XSDResolver()
XSD_PARSER = etree.XMLParser()
XSD_PARSER.resolvers.add(RESOLVER)


@contextlib.contextmanager
def MyParser():
	if etree.get_default_parser is XSD_PARSER:
		yield
	else:
		etree.set_default_parser(XSD_PARSER)
		try:
			yield
		finally:
			etree.set_default_parser()

class QNamer(object):
	"""A hack that generates QNames through getattr.

	Construct with the desired namespace.
	"""
	def __init__(self, ns):
		self.ns = ns
	
	def __getattr__(self, name):
		return etree.QName(self.ns, name.strip("_"))

XS = QNamer("http://www.w3.org/2001/XMLSchema")


VO_SCHEMATA = [
		"Characterisation-v1.11.xsd",
		"ConeSearch-v1.0.xsd",
		"DocRegExt-v1.0.xsd",
		"oai_dc.xsd",
		"OAI-PMH.xsd",
		"RegistryInterface-v1.0.xsd",
		"SIA-v1.1.xsd",
		"SLAP-v1.0.xsd",
		"SSA-v1.1.xsd",
		"StandardsRegExt-1.0.xsd",
		"stc-v1.30.xsd",
		"stc-v1.20.xsd",
		"coords-v1.20.xsd",
		"region-v1.20.xsd",
		"TAPRegExt-v1.0.xsd",
		"uws-1.0.xsd",
		"VODataService-v1.0.xsd",
		"VODataService-v1.1.xsd",
		"VOEvent-1.0.xsd",
		"VORegistry-v1.0.xsd",
		"VOResource-v1.1.xsd",
		"VOSIAvailability-v1.0.xsd",
		"VOSICapabilities-v1.0.xsd",
		"VOSITables-v1.0.xsd",
		"VOTable-1.1.xsd",
		"VOTable-1.2.xsd",
		"VOTable-1.3.xsd",
		"vo-dml-v1.0.xsd",
		"xlink.xsd",
		"XMLSchema.xsd",
		"xml.xsd",]


def getJointValidator(schemaPaths):
	"""returns an lxml validator containing the schemas in schemaPaths.

	schemaPaths must be actual file paths, absolute or
	trunk/schema-relative.
	"""
	with MyParser():
		subordinates = []
		for fName in schemaPaths:
			fPath = RESOLVER.getPathForName(fName)
			root = etree.parse(fPath).getroot()
			subordinates.append((
				"http://vo.ari.uni-heidelberg.de/docs/schemata/"+fName,
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

	This will currently only work if DaCHS is installed from an SVN
	checkout with setup.py develop.

	What's returned has a method assertValid(et) that raises an exception 
	if the elementtree et is not valid.  You can simply call it to
	get back True for valid and False for invalid.
	"""
	return getJointValidator(VO_SCHEMATA+extraSchemata)


def _makeLXMLValidator():
	"""returns an lxml-based schema validating function for the VO XSDs

	This is not happening at import time as it is time-consuming, and the 
	DaCHS server probably doesn't even validate anything.

	This is used below to build getXSDErrorsLXML.
	"""
	VALIDATOR = getDefaultValidator()

	def getErrors(data, leaveOffending=False):
		"""returns error messages for the XSD validation of the string in data.
		"""
		try:
			with MyParser():
				if VALIDATOR.validate(etree.fromstring(data)):
					return None
				else:
					if leaveOffending:
						with open("badDocument.xml", "w") as of:
							of.write(data)
					return str(VALIDATOR.error_log)
		except Exception, msg:
			return str(msg)
	
	return getErrors


def getXSDErrorsLXML(data, leaveOffending=False):
	"""returns error messages for the XSD validation of the string in data.

	This is the lxml-based implemenation, much less disruptive than the
	xerces-based one.
	"""
	if not hasattr(getXSDErrorsLXML, "validate"):
		getXSDErrorsLXML.validate = _makeLXMLValidator()
	return getXSDErrorsLXML.validate(data, leaveOffending)


getXSDErrors = getXSDErrorsLXML


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
		xercMsgs = getXSDErrors(xmlSource, leaveOffending)
		if xercMsgs:
			raise AssertionError(xercMsgs)


def getMemDiffer(allItems=False):
	"""returns a function to call that returns a list of new DaCHS structures
	since this was called.

	With allItems=True, this returns all items, including frames and stuff
	from the function call itself.  That's only useful if you have an idea
	what you're looking for.
	"""
	import gc
	from gavo import base

	gc.collect()
	seen_ids = set(id(ob) for ob in gc.get_objects()
		if allItems or isinstance(ob, base.Structure))
	seen_ids.add(id(seen_ids))

	def getNewObjects():
		newObjects = []
		for ob in gc.get_objects():
			if id(ob) not in seen_ids and (
					allItems or isinstance(ob, base.Structure)):
				newObjects.append(ob)
		return newObjects
	
	return getNewObjects


def debugReferenceChain(ob):
	"""a sort-of-interactive way to investigate where ob is referenced.
	"""
	import gc
	while True:
		print repr(ob)
		refs = gc.get_referrers(ob)
		while refs:
			nob = refs.pop()
			print len(refs), utils.makeEllipsis(repr(nob))
			res = raw_input()
			
			if res=="h":
				print "d,x,<empty>,g"

			elif res=="d":
				import ipdb;ipdb.set_trace()

			elif res=="x":
				return

			elif res:
				ob = nob
				break


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
