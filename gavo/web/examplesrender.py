"""
The renderer for VOSI examples, plus the docutils extensions provided for
them.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

import re

from nevow import rend

from .. import base
from .. import svcs
from .. import utils
from . import grend

class _Example(rend.DataFactory):
	"""A formatted example.

	These get constructed with example meta items and glue these
	together with the nevow rendering system.
	"""
	def __init__(self, exMeta):
		self.original = exMeta
	
	def data_id(self, ctx, data):
		return re.sub("\W", "", base.getMetaText(self.original, "title",
			propagate=False))

	def _translateDescription(self):
		rawHTML = self.original.getContentAsHTML()
		# we should do XML parsing here, but frankly, there's little that
		# could go wrong when just substituting stuff
		return re.sub('(class="[^"]*ivo_tap_exampletable[^"]*")',
			r'\1 property="table"', rawHTML)

	def data_renderedDescription(self, ctx, data):
		if not hasattr("renderedDescription", self.original):
			self.original.renderedDescription = self._translateDescription()
		return self.original.renderedDescription
	

# To allow for easy inclusion of table references in TAP example
# descriptions, we add a custom interpreted text role, taptable.
# Since this module has to be imported before the renderer can
# be used, this is not a bad place to put it.
#
# For RST convenience, this only adds a class attribute.  In HTML,
# this needs to become a property attribute;  there's code in _TAPEx
# that does this.

def _registerDocutilsExtension():
	from docutils.parsers.rst import roles
	from docutils import nodes

	def _docutils_taptableRuleFunc(name, rawText, text, lineno, inliner,
			options={}, content=[]):
		node = nodes.reference(rawText, text,
			refuri="/tableinfo/%s"%text) 
		node["classes"] = ["ivo_tap_exampletable"]
		return [node], []

	roles.register_local_role("taptable", _docutils_taptableRuleFunc)

try:
	_registerDocutilsExtension()
except:
	base.ui.notifyWarning("Could not register taptable RST extension."
		"  TAP examples might be less pretty.")


class Examples(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""A page with query examples.

	This will only run on services with the TAP rd (or one that has
	an examples table structured in the same way).
	"""
	name = "examples"
	checkedRenderer = False
	customTemplate = svcs.loadSystemTemplate("examples.html")

	@classmethod
	def isCacheable(self, segments, request):
		return True

	def data_examples(self, ctx, data):
		"""returns _Example instances from the service metadata.
		"""
		for ex in self.service.iterMeta("_example"):
			yield _Example(ex)
