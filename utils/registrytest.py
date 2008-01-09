"""
This is crappy code that gets all kinds of response documents from
the registry interface and checks if they're valid.  This requires
xerces-java.

XXX TODO: include this in roughtest and request things via the web?  
Or is this something conceptually different?
"""

import popen2
import os
import sys
import tempfile

from gavo.web import registry
from elementtree import ElementTree

classpath = ("/usr/share/doc/libxerces2-java-doc/examples/xercesSamples.jar:"
	"/usr/share/java/xercesImpl.jar:/usr/share/java/xmlParserAPIs.jar")


def validateFile(targetFile):
	"""returns something true if targetFile xsd-valid.
	"""
	os.environ["CLASSPATH"] = classpath
	f = popen2.Popen4("java dom.Counter -n -v -s -f '%s'"%targetFile)
	xercMsgs = f.fromchild.read()
	status = f.wait()
	return not status and "[Error]" not in xercMsgs

def validateTree(aTree):
	handle, name = tempfile.mkstemp()
	try:
		f = os.fdopen(handle, "w")
		aTree.write(f, "utf-8")
		f.close()
		retval = validateFile(name)
		if not retval:
			f = open("lastBad.xml", "w")
			aTree.write(f, "utf-8")
			f.close()
	finally:
		os.unlink(name)
	return retval

def runATest(title, pars):
	print "Running %s..."%title,
	sys.stdout.flush()
	theTree = registry.getPMHResponse(pars)
	print "Validating...",
	sys.stdout.flush()
	theTree = registry.getPMHResponse(pars)
	if not validateTree(theTree):
		print "*** Error ***"
	else:
		print "Ok."


testId = "ivo://org.gavo.dc/maidanak/res/rawframes/siap"

_testSpecs = [
	("Identify", {"verb": ["Identify"]}),
	("ListIdentifiers", {"verb": ["ListIdentifiers"], 
		"metadataPrefix": ["ivo_vor"]}),
	("ListIdentifiers", {"verb": ["ListIdentifiers"], 
		"metadataPrefix": ["oai_dc"]}),
	("ListRecords (oai_dc)", {"verb": ["ListRecords"], 
		"metadataPrefix": ["oai_dc"], "set": ["ivo_managed"]}),
	("ListRecords (ivo_vor)", {"verb": ["ListRecords"], 
		"metadataPrefix": ["ivo_vor"], "set": ["local"]}),
	("GetRecord (oai_dc)", {"verb": ["GetRecord"], "metadataPrefix": ["oai_dc"], 
		"identifier": [testId]}),
	("GetRecord (ivo_vor)", {"verb": ["GetRecord"], 
		"metadataPrefix": ["ivo_vor"], "identifier": [testId]}),
	("ListMetadataFormats with identifier", {"verb": ["ListMetadataFormats"], 
		"identifier": [testId]}),
	("ListSets", {"verb": ["ListSets"]}),
]

if __name__=="__main__":
	from gavo import config
	from gavo import nullui
	config.setDbProfile("querulator")
	from gavo.parsing import importparser  # for registration of getRd
	for test in _testSpecs:
		runATest(*test)
	try:
		registry.getPMHResponse({})
	except Exception, msg:
		if not validateTree(registry.getErrorTree(msg, {})):
			print "*** Error validating error response ***"
