"""
Tests for various parts of the server infrastructure, using trial.
"""

from gavo import api
from gavo.web import root
from gavo.helpers import testhelpers

import trialhelpers


class AdminTest(trialhelpers.RenderTest):
	renderer = root.ArchiveService()

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
				["currently is blocked"], self._makeAdmin
			).addCallback(reload)

		return trialhelpers.runQuery(self.renderer,
			"POST", "/seffe/__system__/adql", 
			{"__nevow_form__": "adminOps", "block": "Block"}, 
			self._makeAdmin
		).addCallback(checkBlocked)


class FormTest(trialhelpers.RenderTest):
	renderer = root.ArchiveService()

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

