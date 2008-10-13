#!/usr/bin/env python
# ** ARI-Location: ella.cl.uni-heidelberg.de:gavotest/

"""
A script to run a series of tests on our local server to see if a software
update didn't kill anything important.

This requires a roughtestconfig.py script defining URL prefixes to the 
services to test, currently qu_root (querulator) and nv_root (nevow-based
services).
"""

from email.Message import Message
from email.MIMEMultipart import MIMEMultipart
import httplib
import sys
import time
import traceback
import urllib
import urlparse

from roughtestconfig import *
import roughtestdata


class TestURLopener(urllib.FancyURLopener):
	version = "GAVO regression test suite"
	def prompt_user_passwd(self, host, realm):
		return "test", "test"


urllib._urlopener = TestURLopener()


class TestGroup(object):
	def __init__(self, name, *tests):
		self.name = name
		self.tests = tests
		self.nOk, self.nFail = 0, 0
	
	def run(self):
		for test in self.tests:
			if test==None:
				break
			try:
				print "Running %s..."%test.description
				test.run()
				self.nOk += 1
			except KeyboardInterrupt:
				raise
			except AssertionError, msg:
				self.nFail += 1
				print "**** Test failed: %s -- %s\n"%(test.description, test.url)
				print ">>>>", msg
			except Exception:
				self.nFail += 1
				print "**** Internal Failure: %s -- %s\n"%(test.description, 
					test.url)
				traceback.print_exc()


class GetHasStringTest:
	"""is a test that the GET of a URL contains a certain string.
	"""
	def __init__(self, url, sentinel, description):
		self.url, self.sentinel = url, sentinel
		self.description = description
		self.lastResult = ""
	
	def run(self):
		self.lastResult = urllib.urlopen(self.url).read()
		assert self.sentinel in self.lastResult


class GetLacksStringTest(GetHasStringTest):
	"""is a test that a GET response does not have a string.
	"""
	def run(self):
		self.lastResult = urllib.urlopen(self.url).read()
		assert self.sentinel not in self.lastResult


class GetHasStringsTest(GetHasStringTest):
	"""is a test that the GET of a URL contains each in a sequence of strings.
	"""
	def run(self):
		self.lastResult = urllib.urlopen(self.url).read()
		for phrase in self.sentinel:
			assert phrase in self.lastResult, "%s missing"%repr(phrase)


class PostHasStringsTest:
	"""is a test for the presence of some strings in a server response to a
	data POST.
	"""
	def __init__(self, url, data, sentinel, description, **kwargs):
		self.url, self.sentinel = url, sentinel
		self.description = description
		self.data = data
		self.headers = dict([(key.replace("_", "-"), val) for key, val
			in kwargs.iteritems()])
	
	def run(self):
		_, host, path, query, _ = urlparse.urlsplit(self.url)
		if query:
			query = '?'+query
		headers = self.headers.copy()
		if self.data:
			headers["content-length"] = len(self.data)
		conn = httplib.HTTPConnection(host)
		conn.request("POST", path+query, self.data, headers=headers)
		self.lastResult = conn.getresponse().read()
		for sent in self.sentinel:
			assert sent in self.lastResult


class PostFormHasStringsTest(PostHasStringsTest):
	"""is a test posting a form to a server.
	"""
	def __init__(self, url, data, sentinel, description, **kwargs):
		data = urllib.urlencode(data)
		kwargs["content-type"] = "application/x-www-form-urlencoded"
		PostHasStringsTest.__init__(self, url, data, sentinel, 
			description, **kwargs)


class HeadStatusTest:
	"""is a test that issues a HEAD request for a URL and checks that it
	has the given query status.
	"""
	def __init__(self, url, status, description):
		self.url, self.status = url, status
		self.description = description
		self.lastResult = 0

	def run(self):
		_, host, path, query, _ = urlparse.urlsplit(self.url)
		conn = httplib.HTTPConnection(host)
		conn.request("HEAD", path+"?"+query)
		resp = conn.getresponse()
		conn.close()
		self.lastResult = resp
		assert self.status==resp.status


class HeadFieldTest:
	"""is a test that issues a HEAD request for a URL and checks that 
	specified fields have the specified values.
	"""
	def __init__(self, url, expectedFields, description):
		self.url, self.expectedFields = url, expectedFields
		self.description = description

	def run(self):
		_, host, path, query, _ = urlparse.urlsplit(self.url)
		conn = httplib.HTTPConnection(host)
		conn.request("HEAD", path+"?"+query)
		resp = conn.getresponse()
		conn.close()
		self.lastResult = resp
		for key, value in self.expectedFields:
			assert resp.getheader(key)==value


class _FormData(MIMEMultipart):
  """is a container for multipart/form-data encoded messages.

  This is usually used for file uploads.
  """
  def __init__(self):
    MIMEMultipart.__init__(self, "form-data")
    self.epilogue = ""
  
  def addFile(self, paramName, fileName, data):
    """attaches the contents of fileName under the http parameter name
    paramName.
    """
    msg = Message()
    msg.set_type("application/octet-stream")
    msg["Content-Disposition"] = "form-data"
    msg.set_param("name", paramName, "Content-Disposition")
    msg.set_param("filename", fileName, "Content-Disposition")
    msg.set_payload(data)
    self.attach(msg)

  def addParam(self, paramName, paramVal):
    """adds a form parameter paramName with the (string) value paramVal
    """
    msg = Message()
    msg["Content-Disposition"] = "form-data"
    msg.set_param("name", paramName, "Content-Disposition")
    msg.set_payload(paramVal)
    self.attach(msg)


class UploadTest:
	"""is a test that does an upload and then calls a user-defined routine.

	In contrast to the other test classes, this is abstract, since it's
	just too messy to abstract whatever you may want to test and upload
	into constructor arguments.

	Derived classes must define a function genForm() returning a _formData
	instance, and a function check(status, answer) doing the assertions.

	They may define a getAuth function returning a username/password pair
	for HTTP Basic auth.
	"""
	def __init__(self, url, data, description):
		self.url, self.data = url, data
		self.description = description

	def _upload(self, uploadURL, auth=None):
		_, host, path, _, query, _ = urlparse.urlparse(uploadURL)
		uri = path+"?"+query
		form = self.genForm()
		form.set_param("boundary", "========== roughtest deadbeef")
		hdr = {	
			"Content-Type": form.get_content_type()+'; boundary="%s"'%
				"========== roughtest deadbeef",
			}
		if auth:
			hdr["Authorization"] = "Basic %s"%auth.encode("base64"),
		conn = httplib.HTTPConnection(host)
		conn.connect()
		conn.request("POST", uri, form.as_string(), hdr)
		resp = conn.getresponse()
		res = resp.read()
		conn.close()
		return resp.status, res

	def run(self):
		self.check(*self._upload(self.url, 
			getattr(self, "getAuth", lambda: None)()))


class DexterUploadTest(UploadTest):
	def genForm(self):
		form = _FormData()
		form.addFile("inFile", "foo.jpg", self.data)
		form.addParam("_charset_", "UTF-8")
		form.addParam("__nevow_form__", "upload")
		return form
	
	def check(self, status, response):
		assert status==200
		assert 'custom/__testing__/edit/0"' in response


class UploadHasStringTest(UploadTest):
	"""is a test for GAVO's built-in file upload service.
	"""
	def __init__(self, url, dataDesc, expected, description):
		self.dataName, self.data, self.mode = dataDesc
		self.expected = expected
		UploadTest.__init__(self, url, self.data, description)
	
	def genForm(self):
		form = _FormData()
		form.addFile("File", self.dataName, self.data)
		form.addParam("Mode", self.mode)
		form.addParam("_charset_", "UTF-8")
		form.addParam("__nevow_form__", "genForm")
		return form

	def check(self, status, response):
		if status!=200:
			print "Additional Failure Info: status=%d"%status
		assert status==200
		if self.expected not in response:
			print "Additional Failure Info: response was %s"%repr(response)
		assert self.expected in response


myTests = [
	TestGroup("apfs",
		GetHasStringTest(nv_root+"/apfs/res/apfs_new/catquery/form",
			"Output format",
			"NV APFS form"),
		GetHasStringTest(nv_root+"/apfs/res/apfs_new"
			"/catquery/form?__nevow_form__=genForm&object=56&hrInterval=24"
			"&_FILTER=default&_FORMAT=HTML&_VERB=2&TDENC=True&submit=Go",
			"Required</li>",
			"NV APFS formal argument validation"),
		GetHasStringTest(nv_root+"/apfs/res/apfs_new/"
			"catquery/form?__nevow_form__=genForm&object=fdsfa&startDate__day=12&"
			"startDate__month=12&startDate__year=2006&endDate__day=20&"
			"endDate__month=12&endDate__year=2006&hrInterval=24&_FILTER=default"
			"&_FORMAT=HTML&_VERB=2&TDENC=True&submit=Go",
			"known by simbad",
			"NV APFS custom argument validation"),
		GetHasStringTest(nv_root+"/apfs/res/apfs_new/catquery/form?"
			"__nevow_form__=genForm&object=56&startDate__day=12&startDate__month=12"
			"&startDate__year=2006&endDate__day=20&endDate__month=12&endDate__year"
			"=2006&hrInterval=24&_FILTER=default&_FORMAT=HTML&_VERB=2&TDENC=True"
			"&submit=Go",
			"+5 31 28.714",
			"NV APFS computation")),

	TestGroup("maidanak-siap",
		GetHasStringTest(nv_root+"/maidanak/res/rawframes/siap/siap.xml?"
			"POS=q2237%2B0305&SIZE=0.1&INTERSECT=OVERLAPS&_TDENC=True&"
			"_DBOPTIONS_LIMIT=10",
			'<VALUES type="actual">',
			"NV Maidanak SIAP successful query"),
		GetHasStringTest(nv_root+"/maidanak/res/rawframes/siap/siap.xml?"
			"POS=q2237%2B0305&SIZE=0.a1&INTERSECT=OVERLAPS&_TDENC=True&"
			"_DBOPTIONS_LIMIT=10",
			'name="QUERY_STATUS" value="ERROR"',
			"NV Maidanak error document"),
		GetHasStringTest(nv_root+"/getproduct?key=maidanak/raw/cd029/oct1603"
			"/q2237/mj160043.gz&siap=true",
			'60043\x00\xec\xbdip\x9e\xd7\x95\xdf\x99T*\x93\x9at',
			"NV Maidanak product delivery"),
		GetHasStringTest(nv_root+"/maidanak/res/rawframes/siap/form?"
			"__nevow_form__=genForm&POS=M1&SIZE=0.5&INTERSECT=OVERLAPS",
			'<div class="resmeta"><p>Matched:',
			"Simbad resolution of positions works"),
		HeadStatusTest(nv_root+"/getproduct?key=maidanak/raw/cd002/aug1305/"
			"q2237_ogak/oh130102.gz&siap=true",
			401,
			"NV Maidanak auth test (will fail starting 2008-12-31)"),
		GetHasStringTest(nv_root+"/maidanak/res/rawframes/siap/siap.xml"
			"?FORMAT=METADATA",
			'<FIELD ID="wcs_refValues" arraysize="*" datatype="double"'
				' name="wcs_refValues"',
			"NV Maidanak metadata query"),
	),

	TestGroup('tar',
		GetHasStringsTest(nv_root+"/lensdemo/view/q/form?__nevow_form__=genForm"
			"&object=APM%2008279%2B5255&_DBOPTIONS_ORDER=date_obs&_DBOPTIONS_LIMIT=2&"
			"_FORMAT=tar&submit=Go", [
				"\0\0\0\0\0\0",
				"This file is embargoed"],
			"Tar output looks like a tar output with embargoed files"
				" (will fail starting 2008-12-31)"),
		HeadFieldTest(nv_root+"/maidanak/res/rawframes/siap/form?"
			"__nevow_form__=genForm&POS=q2237%2B0305&SIZE=1&INTERSECT=OVERLAPS&"
			"FORMAT=image%2Ffits&dateObs=2001-01-01%20..%202005-10-10&"
			"_DBOPTIONS_LIMIT=1&_FORMAT=tar&_DBOPTIONS_ORDER=dateObs", [
				("content-disposition", "attachment; filename=truncated_data.tar"),
				("content-type", "application/x-tar")],
			"Tar output declared in header"),
	),

	TestGroup("auth",
		HeadStatusTest(nv_root+"/rauchspectra/theospectra/upload/upload",
			401,
			"Auth required for protected upload."),
		HeadStatusTest(nv_root+"/rauchspectra/theospectra/"
			"upload/mupload",
			401,
			"Auth required for protected machine upload."),
		HeadStatusTest(nv_root+"/maidanak/res/rawframes/q/form",
			401,
			"Auth required for protected form."),
		HeadStatusTest(nv_root+"/maidanak/res/rawframes/q/form"
			"?__nevow_form__=genForm&object=H1413%2B117&_DBOPTIONS_ORDER=&"
			"_DBOPTIONS_LIMIT=100&_FORMAT=HTML&_VERB=2&_TDENC=True&submit=Go",
			401,
			"Auth requried for protected form result."),
		HeadStatusTest(nv_root+"/apfs/res/apfs_new/catquery/upload",
			403,
			"Disallowed renderer yields 403."),
	),

	TestGroup("siap.xml",
		GetHasStringsTest(nv_root+"/lswscans/res/positions/siap/siap.xml?"
			"POS=168,22&SIZE=0.5",
			["wcs_equinox", "BINARY", '<MIN value="168', 'POS_EQ_DEC_MAIN'],
			"SIAP reply looks like a SIAP VOTable"),
		GetHasStringsTest(nv_root+"/lswscans/res/positions/siap/siap.xml?"
			"POSS=168,22&SIZE=0.5",
			["VOTABLE", 'value="ERROR"', 'POS: Required'],
			"SIAP error reporting is a VOTable and include parameter names"),
		GetLacksStringTest(nv_root+"/lswscans/res/positions/siap/siap.xml?"
			"POS=168,22&SIZE=0.5&dateObs=%3C%201950-01-01",
			"1985-10-31",
			"SIAP services include custom arguments"),
		GetHasStringsTest(nv_root+"/lswscans/res/positions/siap/siap.xml?"
			"POS=168,22&SIZE=0.5&_TDENC=True",
			["wcs_equinox", "</TD>", "<TD>Heidelberg"],
			"SIAP reply in TDENC works"),
	),

	TestGroup("cns-scs",
		GetHasStringsTest(nv_root+"/cns/res/cns/scs/scs.xml",
			["VOTABLE", "in given Parameters"],
			"SCS error reporting 1"),
		GetHasStringsTest(nv_root+"/cns/res/cns/scs/scs.xml?RA=17.0&DEC=30&SR=a",
			["VOTABLE", "invalid literal"],
			"SCS error reporting 2"),
# The following two are probably too fragile
		GetHasStringsTest(nv_root+"/cns/res/cns/scs/scs.xml?RA=17.0&DEC=30&SR=2",
			["VOTABLE", 'encoding="base64">A'],
			"SCS successful query, binary"),
		GetHasStringsTest(nv_root+"/cns/res/cns/scs/scs.xml?RA=17.0&DEC=30&SR=2"
			"&_TDENC=True",
			["VOTABLE", "TABLEDATA><TR><TD>21029"],
			"SCS successful query, tdenc"),
		),

	TestGroup("registry",  # Maybe build xsd validation into these?
		GetHasStringsTest(nv_root+"/oai.xml", [
				"<oai:OAI-PMH", 'Argument">verb'],
			"Credible PMH error message"),
		GetHasStringsTest(nv_root+"/oai.xml?verb=ListSets", [
				'verb="ListSets" />',
				'ivo_managed'],
			"PMH ListSets response looks all right"),
		GetHasStringsTest(nv_root+"/oai.xml?verb=Identify", [
				'xsi:type="vg:Registry',
				'ivo://ivoa.net/std/Registry',
				'OAIHTTP'],
			"PMH Identify response looks all right"),
		GetHasStringsTest(nv_root+"/oai.xml?verb=ListMetadataFormats", [
				'metadataPrefix>oai_dc',
				'ivo_vor</oai:metadataPrefix'],
			"PMH ListMetadataFormats response looks all right"),
		GetHasStringsTest(nv_root+"/oai.xml?verb=ListIdentifiers&"
				"metadataPrefix=oai_dc", [
					'oai:ListIdentifiers>',
					'ivo_managed'],
			"PMH ListIdentifiers response looks all right in oai_dc"),
		GetHasStringsTest(nv_root+"/oai.xml?"
				"verb=GetRecord&"
				"identifier=ivo://org.gavo.dc/maidanak/res/rawframes/siap&"
				"metadataPrefix=ivo_vor", [
					'oai:GetRecord>',
					'ri:Resource'],
			"PMH GetRecord response looks all right in ivo_vor"),
		GetHasStringsTest(nv_root+"/oai.xml?"
				"verb=GetRecord&"
				"identifier=ivo://org.gavo.dc/maidanak/res/rawframes/siap&"
				"metadataPrefix=oai_dc", [
					'oai:GetRecord>',
					'dc:title'],
			"PMH GetRecord response looks all right in oai_dc"),
		GetHasStringTest(nv_root+"/oai.xml?"
				"verb=ListRecords&from=2007-10-10&metadataPrefix=ivo_vor",
					'<oai:ListRecords>', # Think of something better, this may be empty
			"PMH ListRecords response looks all right in ivo_vor"),
		),
	
	TestGroup("dexter",  # CAUSES SERVER-SIDE STATE!
		DexterUploadTest(nv_root+"/dexter/ui/ui/custom/__testing__/",
			roughtestdata.get("dexterImage.jpg"),
			"Dexter processes jpeg image"),
		GetHasStringTest(nv_root+"/dexter/ui/ui/custom/__testing__/edit/0",
			'object classid="java:Dexter"',
			"Dexter returns an applet container on edit pages"),
		HeadStatusTest(nv_root+"/dexter/ui/ui/custom/__testing__/nonexisting",
			404,
			"Dexter doesn't crap out on wild children"),
		HeadStatusTest(nv_root+"/dexter/ui/ui/custom/__testing__/p/201",
			404,
			"Dexter returns 404 for non-existing previews"),
		GetHasStringTest(nv_root+"/dexter/ui/ui/custom/__testing__/p/0",
			"\x89PNG",
			"Dexter preview returns something looking like a PNG"),
		GetHasStringTest(nv_root+"/dexter/ui/ui/custom/__testing__/img/0?"
			"ignored=52888&scale=3&coord=1,1,10,10",
			"GIF87a",
			"Dexter image retrieval returns something like a GIF"),
		GetHasStringTest(nv_root+"/dexter/ui/ui/custom/__testing__/purgeData",
			"Confirm deletion",
			"Dexter asks for confirmation before purging data"),
		PostFormHasStringsTest(nv_root+"/dexter/ui/ui/custom/__testing__/purgeData",
			{"__nevow_form__": "confirmation", "goAhead": "Confirm deletion"},
			['content="0;URL=', '/dexter/ui/ui/custom/'],
			"Dexter deletes data on request"),
		GetLacksStringTest(nv_root+"/dexter/ui/ui/custom/__testing__/",
			'custom/__testing__/edit/0"',
			"Dexter has actually deleted data"),
		PostFormHasStringsTest(nv_root+"/dexter/ui/ui/custom/__testing__/purgeData",
			{"__nevow_form__": "confirmation", "goAhead": "Confirm deletion"},
			['content="0;URL=', '/dexter/ui/ui/custom/'],
			"Dexter deletes empty dataset"),
	),

	TestGroup("formats",
		GetHasStringsTest(nv_root+"/inflight/res/lc1/table/form?"
			"__nevow_form__=genForm&line=200%20..%20800&_DBOPTIONS_ORDER="
			"&_DBOPTIONS_LIMIT=100&_FORMAT=VOPlot&_VERB=2", [
				"<embed ",
				"&amp;_TDENC=True&amp",
				"&amp;line=200+..+800&amp;"],
			"Roughly correct looking VOPlot container"),
		GetHasStringsTest(nv_root+"/inflight/res/lc1/table/form?"
			"__nevow_form__=genForm&line=2%20..%205&"
			"&_DBOPTIONS_LIMIT=100&_FORMAT=FITS&_VERB=2", [
				"'BINTABLE'",
				"TTYPE1  = 'line    '  ",
				"TFORM1  = 'J       '  ",],
			"Lightcurve FITS looks like a binary FITS table"),
		),

	TestGroup("misc",
		GetHasStringTest(nv_root+"/inflight/res/lc1/img/mimg.jpeg?"
			"startLine=20&endLine=30",
			'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00',
			"Infinite Lightcurve image delivery"),
		GetHasStringTest(nv_root,
			"L...",
			"Home page shows services"),
		GetHasStringTest(nv_root+"/lensdemo/view/q/form?__nevow_form__=genForm&"
			"object=SBSS%200909%2B531&_DBOPTIONS_ORDER=&_DBOPTIONS_LIMIT=100"
			"&_FORMAT=HTML&_ADDITEM=owner&submit=Go",
			"Product owner</th>",
			"Additional fields show up in HTML responses"),
		GetHasStringTest(nv_root+"/lensdemo/view/q/form?__nevow_form__=genForm&"
			"object=SBSS%200909%2B531&_ADDITEM=junkfield",
			"the additional field 'junkfield' you requested does not",
			"Invalid additional fields give an at least remotely useful message"),
		GetHasStringTest(nv_root+"/lensdemo/view/q/form?__nevow_form__=genForm&"
			"object=APM%2008279%2B5255&_FORMAT=junk",
			"Invalid output format: junk",
			"Invalid output format is correctly complained about"),
		GetHasStringTest(nv_root+"/getproduct?key=maidanak/raw/cd037/jun_2003/"
			"jun2603/q2237/mf260110.gz&siap=true&preview=True",
			"JFIF",
			"Preview looks like a JPEG"),
		GetHasStringsTest(nv_root+"/maidanak/res/rawframes/siap/info",
			["SIAP Query", "siap.xml", "form", "Other services",
				"SIZE</td>", "Verb. Level"],
			"Info page looks ok"),
		GetHasStringsTest(nv_root+"/__system__/tests/misc/timeout/form",
			["Just wait a while", "Query timed out (took too"],
			"DB timeout yields a nice response"),
	),

	TestGroup('ucds',
		GetHasStringsTest(nv_root+'/ucds/ui/hideui/form?'
				'__nevow_form__=genForm&description=Weird%20uninterpretable%20'
				'gobbledegook&_FORMAT=HTML&submit=Go',
			["No known words", "Query Form", "Weird"],
			"UCD resolver yields nice error message for garbage input"),
		GetHasStringsTest(nv_root+'/ucds/ui/hideui/form?'
				'__nevow_form__=genForm&description=airmass%20measured%20'
				'at%20center%20of%20plate&_FORMAT=HTML&submit=Go',
			["Score</th", "Show known", "toggleDescriptions"],
			"UCD resolver yields credible table for good input"),
		GetHasStringsTest(nv_root+'/ucds/ui/known/form?ucd=phot.mag.sb%3B'
				'em.opt.B&__nevow_form__=genForm',
			["Average blue", "surface brightness"],
			"UCD known descriptions returns something sensible"),
	),

	TestGroup("upload", # CAUSES INTERMEDIATE SERVER-SIDE STATE!
		GetHasStringsTest(nv_root+"/__system__/tests/misc/upload/upload",
			["insert", "update", 'type="file"'],
			"Upload service shows a form"),
		UploadHasStringTest(nv_root+"/__system__/tests/misc/upload/upload",
			("c.foo", "a: 15\nb:10\n", 'u'),
			"0 record(s) modified.",
			"Update of non-existing data is a no-op (may fail on state)"),
		UploadHasStringTest(nv_root+"/__system__/tests/misc/upload/upload",
			("c.foo", "a: 15\nb:10\n", 'i'),
			"1 record(s) modified.",
			"Insert of non-existing data touches one record."),
		UploadHasStringTest(nv_root+"/__system__/tests/misc/upload/upload",
			("c.foo", "a: 15\nb:17\n", 'i'),
			"Cannot enter c.foo in database: duplicate key violates"
				" unique constraint",
			"Duplicate insertion of data yields error"),
		UploadHasStringTest(nv_root+"/__system__/tests/misc/upload/upload",
			("c.foo", "a: 15\nb:10\n", 'u'),
			"1 record(s) modified.",
			"Updates of existing data modify db"),
		GetHasStringTest(nv_root+"/__system__/tests/misc/reset/form",
			"Matched: 0",
			"Reset of db seems to work"),
	),

	TestGroup("soap",
# To come up with the stuff posted, use soappy and 
# proxy.soapproxy.config.debug = True
		GetHasStringsTest(nv_root+"/ucds/ui/hideui/soap/go?wsdl",
			["wsdl:definitions", '<schema targetNamespace="ivo://', 
				"ivo://org.gavo.dc/ucds/ui/hideui"],
			"UCD WSDL for SOAP looks all right"),
		PostHasStringsTest(nv_root+"/ucds/ui/hideui/soap/go",
			'eJydkU1vgzAMhu/7FSh34kW9jAiotqo97Utiq3ZFIaKRaIJwCOXfz3Sl6rrDpkk5JLb'
			'zvPbrdHnY\nN1HQHRpnMyb4LYu0Va4yts7Y+9smvmPL/CYtXu5f4/XzVq5t0I1rdXSO'
			'zOWFHxudsZ33rQRAtdP7\nEjnh0ZUtd10N0wXmcmAR5SzKE2j1j68HNOdfwzDwYXEsF'
			'kmSwMfTY3EExcaiL63SV4Lbvwh+DXsh\nWP0uyC79enDVSG+LQvaoC90Fo/SJRsGMme'
			'AIRhRel8HxSkGvKoTe0GGzyyvZOedpPxM7iIgGl35s\nyW7qSKLvyBWWpxAE5eG72BS'
			'5bgd+7DP/BCkQrjo=\n'.decode("base64").decode("zlib"),
			[':Client</faultcode>', 'No known words'],
			'UCD SOAP error messaging returns client error on junk input',
			SOAPAction='"useService"', content_type="text/xml"),
		PostHasStringsTest(nv_root+"/ucds/ui/hideui/soap/go",
			'eJydkU1PwzAMhu/8iij3JlRcaNR2gmmc+JIKE9eoibpIbVLFabr+e9yxTmMcQEg5JI7'
			'9vPbrfLXv\nWhK1B+NsQVN2TYm2tVPGNgV9f3tIbumqvMqrl7vXZPO8FRsbdet6TU6R'
			'Jb0KU6sLuguhF5xDvdOd\nBIZ4cLJnzjd8vvAlnVOCfxbEEbT+R+kezKlqHEc23hyS0'
			'yzL+MfTY3UAJcZCkLbWF4Lbvwh+DXsm\nqH4XpOd+3Ts14dtCKgbQlfbR1PpIw2BBTX'
			'QIQwprZHRM1XyoFfDB4KGLy2vhnQu4n5kdU4KDizD1\naDd2JCB4dIWW0ngcA4gMpDM'
			'qmE7nPKZYwb/Lz5HLBvmPDZefAse1KA==\n'.decode("base64").decode("zlib"),
			['tns:outList', 'obs.airMass', '</tns:outList>'],
			"UCD SOAP request yields something reasonable",
			SOAPAction='"useService"', content_type="text/xml"),
		PostHasStringsTest(nv_root+"/apfs/res/apfs_new/qall/soap/go",
			'eJydkl9PgzAUxd/3KUjfoRSmYQ2w6DKf/Jegi2+GQGVNWIttLePbe8GxTIyZ8a2999'
			'dzek8bL/e7\n2rFMaS5FgojnI4eJQpZcVAl6frpxI7RMZ3H2cPXoru83dC0sq2XDnG'
			'NlxDPT1SxBW2MairEutmyX\naw/ktcwbT6oK9ws84hg50BOaHoRW/zi61/x4qm1brw'
			'0HmCwWC/xyd5sNQi4X2uSiYBPDzV8Mv4Y9\nMSzPG6LTvK5l2cFeaEI/NMuYsrxgBz'
			'UoJohbCWKg4lW5lV5Z4Lx501gxPSxeBWvxe17XaEx8RZWU\nBt6q97HEgRCo6RqIHm'
			'5HtVGQEEovLmNsSU8EvxCB70euH7h+CGTQk+E5MgIy7Mn5hOTCoJRAdw5d\n/H3Yvj'
			'KNA//4T+nsE44V1dA=\n'.decode("base64").decode("zlib"), [
				'="xsd:date">2008-02-03Z</tns:isodate>', 
				'<tns:raCio xsi:type="xsd:double">25.35'],
			'APFS SOAP returns something reasonable',
			SOAPAction='"useService"', content_type="text/xml"),
		),

	TestGroup("infopages",
		GetHasStringsTest(nv_root+"/__system__/dc_tables/show/tableinfo?"
				"tableName=ppmx.data",
			["Table information", "ADQL", "Bmag", "Unit", "The following services"],
			"Table info looks credible"),
		GetHasStringsTest(nv_root+"/apfs/res/apfs_new/catquery/info",
			["Service Documentation", "form</em> --", "SOAP", "endDate"],
			"Service info looks credible and includes some meta information"),
		GetHasStringsTest(nv_root+"/__system__/dc_tables/list/form",
			["Fully qualified table", "ppmx.data", "motions extension"],
			"ADQL tables can be listed"),
		),

	TestGroup("adql",
		GetHasStringsTest(nv_root+"/__system__/adql/query/form?"
				"__nevow_form__=genForm&query=foobar%0A&_FORMAT=HTML&submit=Go",
			["Service info", "Could not parse", 'Expected "SELECT"'],
			"Parse errors are reported in-form"),
		GetHasStringsTest(nv_root+"/__system__/adql/query/form?"
				"__nevow_form__=genForm&query=select%20*%20from%20users.users&"
				"_FORMAT=HTML&submit=Go",
			["permission denied for schema users", "Result link"],
			"Users table is not accessible through ADQL"),
		GetHasStringsTest(nv_root+"/__system__/adql/query/form?"
				"__nevow_form__=genForm&query=select%20*%20from%20weblogs.accesses&"
				"_FORMAT=HTML&submit=Go",
			["permission denied for schema weblogs", "Result link"],
			"Log table is not accessible through ADQL"),
		),

	TestGroup("services",
		GetHasStringsTest(nv_root+"/lswscans/res/positions/q/form?"
				"__nevow_form__=genForm&POS=1.5%2C6.3&SIZE=0.5&INTERSECT=OVERLAPS&"
				"FORMAT=image%2Ffits&cutoutSize=0.5&_DBOPTIONS_ORDER=&"
				"_DBOPTIONS_LIMIT=100&_FORMAT=HTML&submit=Go",
			["Plate alpha", "Bandpass", "B2866b"],
			"LSW plate service gives plausible answer"),
		GetHasStringsTest(nv_root+"/getproduct?"
				"key=lswscans/data/Bruceplatten/FITS/B2866b.fits"
				"%26amp%3Bra%3D2.0%26amp%3Bdec"
				"%3D2.0%26amp%3Bsra%3D0.5%26amp%3Bsdec%3D0.5",
			["SIMPLE  =                    T", "OBSERVER= 'F.Kaiser'", 
				"NAXIS1  =                 17"],
			"LSW cutout delivers plausible FITS"),
		GetHasStringsTest(nv_root+"/liverpool/res/rawframes/q/form",
			["<h1>Liverpool", "QSO B0957+5608A"],
			"Liverpool service delivers form"),
		GetHasStringsTest(nv_root+"/liverpool/res/rawframes/q/form?"
				"__nevow_form__=genForm&object=QSO%20B0957%2B5608A&dateObs="
				"%3C%202007-12-31&_DBOPTIONS_ORDER=&_DBOPTIONS_LIMIT=100&"
				"_FORMAT=HTML&submit=Go",
			["Product", "insertPreview(this"],
			"Liverpool service delivers data"),
		GetHasStringsTest(nv_root+"/apfs/times/q/form?__nevow_form__=genForm"
				"&ut1=2008-10-04T10%3A30%3A23%20..%202008-10-05T10%3A30%3A23&"
				"interval=3600&_FORMAT=HTML&submit=Go",
			["Greenwich mean sidereal", "12:24:29.3052", "+306 20 18.341", 
				"04:27:07.6839"],
			"Times service delivers expected values"),
		GetHasStringsTest(nv_root+"/apfs/times/q/form?__nevow_form__=genForm"
				"&ut1=wirres%20Zeug&interval=3600&_FORMAT=HTML&submit=Go",
			["wirres Zeug", "Invalid date expression (at 0)"],
			"Times service delivers nice error message for malformed vexprs"),
	)
]


def tally(groupsRun):
	nOk = sum([g.nOk for g in groupsRun])
	nFail = sum([g.nFail for g in groupsRun])
	if nFail==0:
		print "%d test(s) passed"%nOk
	else:
		print "********* %d test(s) of %d failed"%(nFail, nFail+nOk)


""" Old querulator tests.
	TestGroup("querulator",
		GetHasStringTest(qu_root+"/list",
			"Further Queries",
			"Main query page"),
		GetHasStringTest(qu_root+"/list/demo",
			">objects<",
			"Demo queries present"),
		GetHasStringTest(qu_root+"/query/demo/objects.cq",
			"Object observed",
			"Demo object query is served"),
		GetHasStringTest(qu_root+"/run/demo/"
				"objects.cq?4f626a656374206f62736572766564=Q2237%2B0305&sortby="
				"date_obs&limitto=100&outputFormat=HTML",
			"truncated due to reaching the match limit.",
			"Demo query somewhat runs"),
		GetHasStringTest(qu_root+"/run/demo2/objects.cq?"
				"4f626a656374206f62736572766564=APM%2008279%2B5255&46696c746572="
				"Johnson%20B&46696c746572=Johnson%20I&46696c746572="
				"Johnson%20R&46696c746572=Johnson%20U&46696c746572=Johnson%20V&"
				"sortby=date_obs&limitto=1000&outputFormat=HTML",
			"Selected items:",
			"Multiple selection works"),
		GetHasStringTest(qu_root+"/run/demo2/objects.cq?"
				"4f626a656374206f62736572766564=Q2237%2B0305&sortby=date_obs&"
				"limitto=100&outputFormat=VOTable%2030",
			'name="datapath"',
			"VOTable output"),
		GetHasStringTest(qu_root+"/getproduct"
			"/demo/objects.cq?path=apo/cd/9506/L2237_950602_r_01.fits",
		"L2237_950602_R_01[1/1]",
		"Basic product delivery")),
"""


if __name__=="__main__":
	if len(sys.argv)>1 and sys.argv[1]=="-h":
		for group in myTests:
			print group.name
		sys.exit()
	testsToRun = set(sys.argv[1:])
	testsRun = []
	try:
		for group in myTests:
			if testsToRun:
				if not group.name in testsToRun:
					continue
			group.run()
			testsRun.append(group)
	finally:
		urllib.urlcleanup()
	tally(testsRun)
