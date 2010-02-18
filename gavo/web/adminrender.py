"""
A renderer to do RD-based maintainance.
"""

import os
import urllib

from nevow import inevow
from nevow import rend
from nevow import tags as T, entities as E
from nevow import url

from zope.interface import implements

from gavo import base
from gavo import registry
from gavo import stc
from gavo import svcs
from gavo.imp import formal
from gavo.web import common
from gavo.web import grend
from gavo.web import resourcebased
from gavo.web import weberrors


class AdminRenderer(formal.ResourceMixin, grend.ServiceBasedRenderer):
	"""A renderer allowing to block and/or reload services.
	"""
	name = "admin"
	customTemplate = common.loadSystemTemplate("admin.html")
	clientRD = None

	def form_setDowntime(self, ctx):
		form = formal.Form()
		form.addField("scheduled", formal.String(),
			label="Schedule downtime for",
			description="Note that this is purely informative.  The server"
				" will not take down the services at this point in time."
				" Leave empty to cancel.  This will also be cleared on a"
				" reload.")
		form.addAction(self.setDowntime, label="Ok")
		form.data = {
			"scheduled": base.getMetaText(self.clientRD, "_scheduledDowntime")}
		return form

	def setDowntime(self, ctx, form, data):
		scheduleFor = data.get("scheduled")
		if scheduleFor is None:
			self.clientRD.delMeta("_scheduledDowntime")
		else:
			try:
				stc.parseISODT(scheduleFor)  # check syntax
				self.clientRD.setMeta("_scheduledDowntime", scheduleFor)
			except stc.STCLiteralError: # bad date syntax
				raise formal.FieldError("Doesn't look like ISO", "scheduleFor")

	def form_adminOps(self, ctx):
		form = formal.Form()
		if hasattr(self.clientRD, "currently_blocked"):
			label = "Unblock"
		else:
			label = "Block"
		form.addAction(self.toggleBlock, label=label, name="block")
		form.addAction(self.reloadRD, label="Reload RD", name="submit")
		return form

	def toggleBlock(self, ctx, form, data):
		if hasattr(self.clientRD, "currently_blocked"):
			delattr(self.clientRD, "currently_blocked")
		else:
			self.clientRD.currently_blocked = True

	def reloadRD(self, ctx, form, data):
# XXX TODO: load the supposedly changed RD here and raise errors before
# booting out the old stuff.
		base.caches.clearForName(self.clientRD.sourceId)

	def data_blockstatus(self, ctx, data):
		if hasattr(self.clientRD, "currently_blocked"):
			return "blocked"
		return "not blocked"

	def data_services(self, ctx, data):
		"""returns a sequence of service items belonging to clientRD, sorted
		by id.
		"""
		return sorted(self.clientRD.services)

	def render_svclink(self, ctx, data):
		"""renders a link to a service info with a service title.
		
		data must be an item returned from data_services.
		"""
		return ctx.tag(href=data.getURL("info"))[unicode(data.getMeta("title"))]

	def render_rdId(self, ctx, data):
		return ctx.tag[self.clientRD.sourceId]

	def render_ifmeta(self, metaName):
		return grend.GavoRenderMixin.render_ifmeta(self, metaName,
			metaCarrier=self.clientRD)

	def _doRenderMeta(self, ctx, raiseOnFail=False, plain=False):
		return grend.GavoRenderMixin._doRenderMeta(self, ctx, raiseOnFail,
			plain, self.clientRD)

	def renderHTTP(self, ctx):
		# naked renderer (i.e., no locateChild) is a non-existing resource
		if self.clientRD is None:
			raise svcs.UnknownURI("No root on this renderer")
		return common.runAuthenticated(ctx, "admin", 
			super(AdminRenderer, self).renderHTTP, ctx)

	def locateChild(self, ctx, segments):
		rdId = "/".join(segments)
		try:
			self.clientRD = base.caches.getRD(rdId)
		except base.RDNotFound:
			raise svcs.UnknownURI("No such resource descriptor: %s"%rdId)
		return self, ()

	defaultDocFactory =  common.doctypedStan(
		T.html[
			T.head[
				T.title["Missing Template"]],
			T.body[
				T.p["Admin services are only available with a admin.html template"]]
		])

svcs.registerRenderer(AdminRenderer)
