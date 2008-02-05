#!/usr/bin/env python
# ** ARI-Location: ella.cl.uni-heidelberg.de:gavotest/

"""
A script to run a series of tests on our local server to see if a software
update didn't kill anything important.

This requires a roughtestconfig.py script defining URL prefixes to the 
services to test, currently qu_root (querulator) and nv_root (nevow-based
services).
"""

import httplib
import sys
import time
import traceback
import urllib
import urlparse

from roughtestconfig import *


class TestGroup(object):
	def __init__(self, name, *tests):
		self.name = name
		self.tests = tests
		self.nOk, self.nFail = 0, 0
	
	def run(self):
		for test in self.tests:
			try:
				print "Running %s..."%test.description
				test.run()
				self.nOk += 1
			except KeyboardInterrupt:
				break
			except AssertionError:
				self.nFail += 1
				print "**** Test failed: %s -- %s\n"%(test.description, test.url)
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
	
	def run(self):
		assert self.sentinel in urllib.urlopen(self.url).read()
	

class GetHasStringsTest(GetHasStringTest):
	"""is a test that the GET of a URL contains each in a sequence of strings.
	"""
	def run(self):
		tx = urllib.urlopen(self.url).read()
		for phrase in self.sentinel:
			assert phrase in tx


class HeadStatusTest:
	"""is a test that issues a HEAD request for a URL and checks that it
	has the given query status.
	"""
	def __init__(self, url, status, description):
		self.url, self.status = url, status
		self.description = description

	def run(self):
		_, host, path, query, _ = urlparse.urlsplit(self.url)
		conn = httplib.HTTPConnection(host)
		conn.request("HEAD", path+"?"+query)
		resp = conn.getresponse()
		conn.close()
		assert self.status==resp.status


myTests = [
	TestGroup("apfs",
		GetHasStringTest(nv_root+"/apfs/res/"
			"apfs_new/catquery/form",
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
		HeadStatusTest(nv_root+"/maidanak/res/rawframes/q/form",
			401,
			"Auth required for protected form."),
		HeadStatusTest(nv_root+"/maidanak/res/rawframes/q/form"
			"?__nevow_form__=genForm&object=H1413%2B117&_DBOPTIONS_ORDER=&"
			"_DBOPTIONS_LIMIT=100&_FORMAT=HTML&_VERB=2&_TDENC=True&submit=Go",
			401,
			"Auth requried for protected form result."),
		HeadStatusTest(nv_root+"/apfs/res/apfs_new/catquery/upload",
			404,
			"Disallowed renderer yields 404."),
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
			"SCS successful query, binary"),
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
	),
]


def tally(groupsRun):
	nOk = sum([g.nOk for g in groupsRun])
	nFail = sum([g.nFail for g in groupsRun])
	if nFail==0:
		print "%d tests passed"%nOk
	else:
		print "********* %d tests of %d failed"%(nFail, nFail+nOk)


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
