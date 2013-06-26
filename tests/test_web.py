"""
Tests for various parts of the server infrastructure, using trial.
"""

import os

from gavo.helpers import testhelpers

from gavo import api
from gavo import svcs
from gavo import utils
from gavo.imp import formal
from gavo.svcs import streaming
from gavo.web import root

import trialhelpers


api.setConfig("web", "enabletests", "True")


class ArchiveTest(trialhelpers.RenderTest):
	renderer = root.ArchiveService()


class AdminTest(ArchiveTest):
	def _makeAdmin(self, req):
		req.user = "gavoadmin"
		req.password = api.getConfig("web", "adminpasswd")

	def testDefaultDeny(self):
		return self.assertStatus("/seffe/__system__/adql", 401)
	
	def testFormsRendered(self):
		return self.assertGETHasStrings("/seffe/__system__/adql", {}, [
			"ADQL Query</a>", 
			"Schedule downtime for", 
			'action="http://localhost'],
			rm=self._makeAdmin)
	
	def testDowntimeScheduled(self):
		def checkDowntimeCanceled(ignored):
			self.assertRaises(api.NoMetaKey,
				api.getRD("__system__/adql").getMeta, "_scheduledDowntime",
				raiseOnFail=True)

		def cancelDowntime(ignored):
			return self.assertPOSTHasStrings("/seffe/__system__/adql", 
				{"__nevow_form__": "setDowntime"}, [],
				rm=self._makeAdmin)

		def checkDowntime(ignored):
			self.assertEqual(
				str(api.getRD("__system__/adql").getMeta("_scheduledDowntime")),
				'2009-10-13')
			return self.assertGETHasStrings("/__system__/adql/query/availability", 
				{}, ["<avl:downAt>2009-10-13<"])

		return trialhelpers.runQuery(self.renderer,
			"POST", "/seffe/__system__/adql", 
			{"__nevow_form__": "setDowntime", "scheduled": "2009-10-13"}, 
			self._makeAdmin
		).addCallback(checkDowntime
		).addCallback(cancelDowntime
		).addCallback(checkDowntimeCanceled)

	def testBlockAndReload(self):
		def checkUnBlocked(ignored):
			return self.assertGETHasStrings("/seffe/__system__/adql", {},
				["currently is not blocked"], self._makeAdmin)
	
		def reload(ignored):
			return trialhelpers.runQuery(self.renderer,
				"POST", "/seffe/__system__/adql", 
				{"__nevow_form__": "adminOps", "submit": "Reload RD"}, 
				self._makeAdmin
			).addCallback(checkUnBlocked)

		def checkBlocked(ignored):
			return self.assertGETHasStrings("/seffe/__system__/adql", {},
				["currently is blocked", "invalid@whereever.else"], self._makeAdmin
			).addCallback(reload)

		return trialhelpers.runQuery(self.renderer,
			"POST", "/seffe/__system__/adql", 
			{"__nevow_form__": "adminOps", "block": "Block"}, 
			self._makeAdmin
		).addCallback(checkBlocked)


class CustomizationTest(ArchiveTest):
	def testSidebarRendered(self):
		return self.assertGETHasStrings("/data/test/basicprod/form", {}, [
			'<a href="mailto:invalid@whereever.else">site operators</a>',
			'<div class="exploBody"><span class="plainmeta">ivo://'
				'x-unregistred/data/test/basicprod</span>'])
	
	def testMacrosExpanded(self):
		return self.assertGETHasStrings("/__system__/dc_tables/list/info", {}, [
			"Information on Service 'Unittest Suite Public Tables'",
			"tables available for ADQL querying within the\nUnittest Suite",
			"Unittest Suite Table Infos</a>",])

	def testExpandedInXML(self):
		return self.assertGETHasStrings("/oai.xml", {
			"verb": "GetRecord",
			"metadataPrefix": "ivo_vor",
			"identifier": "ivo://x-unregistred/__system__/services/registry"
		}, [
			"<title>Unittest Suite Registry</title>",
			"<managedAuthority>x-unregistred</managedAuthority>"])


class FormTest(ArchiveTest):
	def testSimple(self):
		return self.assertGETHasStrings("/data/test/basicprod/form", {}, [
				'<a href="/static/help_vizier.shtml#floats">[?num. expr.]</a>',
				"<h1>Somebody else's problem</h1>",
			])
	
	def testInputSelection(self):
		return self.assertGETHasStrings("/data/cores/cstest/form", {}, [
				'Coordinates (as h m s, d m s or decimal degrees), or SIMBAD',
				'Search radius in arcminutes',
				'A sample magnitude'
			])
	
	def testMultigroupMessages(self):
		return self.assertGETHasStrings("/data/cores/impgrouptest/form", {
				"rV": "invalid", 
				"mag": "bogus", 
				formal.FORMS_KEY: "genForm",
			}, [
				# assert multiple form items in one line:
				'class="description">Ah, you know.',
				'class="inmulti"',
				'<div class="message">Not a valid number; Not a valid number</div>',
				'value="invalid"'])
	
	def testCSSProperties(self):
		return self.assertGETHasStrings("/data/cores/cstest/form", {}, [
			'class="field string numericexpressionfield rvkey"',
			'.rvkey { background:red; }'])
	
	def testInputKeyDefault(self):
		return self.assertGETHasStrings("/data/cores/grouptest/form", {}, [
				'value="-4.0"'
			])

	def testInputKeyFilled(self):
		return self.assertGETHasStrings("/data/cores/grouptest/form", 
			{"rV": "9.25"}, [
				'value="9.25"'
			])


class StreamingTest(ArchiveTest):
	def testStreamingWorks(self):
		return self.assertGETHasStrings("/test/stream", {"size": 30}, [
			"123456789012345678901234567890"])
	
	def testChunksWork(self):
		return self.assertGETHasStrings("/test/stream", {"chunksize": "10",
			"size": "35"}, [
			"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx12345"])
	
	def testCrashStreamDoesNotHang(self):
		return self.assertGETHasStrings("/test/streamcrash", {}, [
			"Here is some data.",
			"XXX Internal",
			"raise Exception"])
	
	def testStopProducing(self):

		class StoppingRequest(trialhelpers.FakeRequest):
			def write(self, data):
				trialhelpers.FakeRequest.write(self, data)
				self.producer.stopProducing()

		def assertResult(result):
			# at least one chunk must have been delivered
			self.failUnless(result[0].startswith("xxxxxxxxxx"), 
				"No data delivered at all")
			# ...but the kill must become active before the whole mess
			# has been written
			self.failIf(len(result[0])>utils.StreamBuffer.chunkSize,
				"Kill hasn't happened")

		return trialhelpers.runQuery(self.renderer, "GET", "/test/stream",
			{"chunksize": "10", "size": utils.StreamBuffer.chunkSize*2}, 
			requestClass=StoppingRequest
		).addCallback(assertResult)

	def testClosingConnection(self):

		class ClosingRequest(trialhelpers.FakeRequest):
			def write(self, data):
				raise IOError("Connection closed")

		def assertResult(result):
			self.assertEqual(result[0], "")

		return trialhelpers.runQuery(self.renderer, "GET", "/test/stream",
			{"chunksize": "10", "size": "3500"}, requestClass=ClosingRequest
		).addCallback(assertResult)


_TEMPLATE_TEMPLATE = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns:n="http://nevow.com/ns/nevow/0.1" 
		xmlns="http://www.w3.org/1999/xhtml">
	<head>
		<title>Template test</title>
		<n:invisible n:render="commonhead"/>
	</head>
	<body>
		%s
	</body>
</html>
"""

class TemplatingTest(ArchiveTest):
# These must not run in parallel since they're sharing a file name
# (and it's hard to change this since the clean up would have
# to take place in the test callback)

	commonTemplatePath = os.path.join(
		api.getConfig("tempDir"), "trialtemplate")

	def cleanUp(self):
		try:
			os.unlink(self.commonTemplatePath)
		except os.error:
			pass

	def _assertTemplateRendersTo(self, templateBody, args, strings):
		with open(self.commonTemplatePath, "w") as f:
			f.write(_TEMPLATE_TEMPLATE%templateBody)

		api.getRD("//tests").getById("dyntemplate").templates[
			"fixed"] = self.commonTemplatePath
		return self.assertGETHasStrings("//tests/dyntemplate/fixed", 
			args, strings)

	def testContentDelivered(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{"foo": "content delivered test"},
			["<p>stuff: content delivered test", 'href="/static/css/gavo_dc.css'])
	
	def testNoParOk(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{},
			["stuff: </p>"])
	
	def testEightBitClean(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{"foo": u"\u00C4".encode("utf-8")},
			["stuff: \xc3\x84</p>"])

	def testMessEscaped(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{"foo": '<script language="nasty&"/>'},
			['&lt;script language="nasty&amp;"/&gt;'])


class PathResoutionTest(ArchiveTest):
	def testDefaultRenderer(self):
		return self.assertGETHasStrings("/data/cores/impgrouptest", {},
			['id="genForm-rV"']) #form rendered
			
	def testNoDefaultRenderer(self):
		self.assertGETRaises("/data/cores/grouptest", {},
			svcs.UnknownURI)

	def testSlashAtEndRedirects(self):
		def checkRedirect(result):
			self.assertEqual(result[1].code, 301)
			# the destination of the redirect currently is wrong due to trialhelper
			# restrictions.
		return trialhelpers.runQuery(self.renderer, "GET", 
			"/data/cores/convcat/form/", {}
		).addCallback(checkRedirect)


class BuiltinResTest(ArchiveTest):
	def testRobotsTxt(self):
		return self.assertGETHasStrings("/robots.txt", {},
			['Disallow: /login'])


class ConstantRenderTest(ArchiveTest):
	def testVOPlot(self):
		return self.assertGETHasStrings("/__system__/run/voplot/fixed",
			{"source": "http%3A%3A%2Ffoo%3Asentinel"}, 
			['<object archive="http://']) # XXX TODO: votablepath is url-encoded -- that can't be right?


class MetaRenderTest(ArchiveTest):
	def testMacroExpanded(self):
		return self.assertGETHasStrings("/browse/__system__/tap", {},
			['<div class="rddesc"><span class="plainmeta"> Unittest'
				" Suite's Table Access"])


class MetaPagesTest(ArchiveTest):
	def testGetRR404(self):
		return self.assertGETHasStrings("/getRR/non/existing", {},
			['The resource non#existing is unknown at this site.'])

	def testGetRRForService(self):
		return self.assertGETHasStrings("/getRR/data/pubtest/moribund", {},
			['<identifier>ivo://x-unregistred/data/pubtest/moribund</identifier>'])

