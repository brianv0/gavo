"""
The renderer for VOSI examples, plus the docutils extensions provided for
them.

If you have a renderer that needs custom text roles or directives, read the
docstring of misctricks.RSTExtensions and add whatever roles you need below,
more or less like this::

	misctricks.RSTExtensions.makeTextRole("niceRole")

Only go through RSTExtensions, as these will make sure HTML postprocessing
happens as required.

The reason we keep the roles here and not in the renderer modules where they'd
logically belong (and where they should be documented in the renderer
docstrings) is that we don't want docutils imports all over the place.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import re

from docutils import nodes
from docutils import utils as rstutils
from docutils.parsers import rst

from lxml import etree

from nevow import rend

from gavo import utils
from gavo.utils import misctricks
from .. import base
from .. import svcs
from . import grend


class _Example(rend.DataFactory, base.MetaMixin):
	"""A formatted example.

	These get constructed with example meta items and glue these
	together with the nevow rendering system.

	An important role of this is the translation from the HTML class
	attribute values we use in ReStructuredText to the RDFa properties
	in the output.  The first class that has a matching property wins.

	There's the special exmeta render function that works like metahtml,
	except it's using the example's meta.
	"""
	def __init__(self, exMeta):
		base.MetaMixin.__init__(self)
		self.setMetaParent(exMeta)
		self.original = exMeta
		self.title = base.getMetaText(self.original, "title", propagate=False)
		self.htmlId = re.sub("\W", "", self.title)

	def data_id(self, ctx, data):
		return self.htmlId

	def _getTranslatedHTML(self):
		rawHTML = self.original.getContent("html")
		parsed = etree.fromstring(
			'<div typeof="example" id="%s" resource="#%s">\n'
			'<h2 property="name">%s</h2>\n'
			'%s\n</div>'%(
				self.htmlId, 
				self.htmlId, 
				utils.escapePCDATA(self.title),
				rawHTML))
		actOnClasses = set(misctricks.RSTExtensions.classToProperty)

		for node in parsed.iterfind(".//*[@class]"):
			nodeClasses = set(node.attrib["class"].split())
			properties = " ".join(misctricks.RSTExtensions.classToProperty[c] 
				for c in actOnClasses & nodeClasses)
			if properties:
				node.set("property", properties)

			# For now, I assume element content always is intended to
			# be the relation object (rather than a href that might
			# be present and would take predence by RDFa
			if "href" in node.attrib or "src" in node.attrib:
				node.set("content", node.text)
	
		return etree.tostring(parsed, encoding="utf-8").decode("utf-8")

	def data_rendered(self, ctx, data):
		if not hasattr(self.original, "renderedDescription"):
			self.original.renderedDescription = self._getTranslatedHTML()
		return self.original.renderedDescription
	

class Examples(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	r"""A renderer for examples for service usage.

	This renderer formats _example meta items in its service.  Its output
	is XHTML compliant to VOSI examples; clients can parse it to, 
	for instance, fill forms for service operation or display examples
	to users.

	The examples make use of RDFa to convey semantic markup.  To see
	what kind of semantics is contained, try 
	http://www.w3.org/2012/pyRdfa/Overview.html and feed it the
	example URL of your service.

	The default content of _example is ReStructuredText, and really, not much
	else  makes sense.  An example for such a meta item can be viewed by
	executing ``gavo admin dumpDF //userconfig``, in the tapexamples STREAM.

	To support annotation of things within the example text, DaCHS
	defines several RST extensions, both interpreted text roles (used like
	``:role-name:`content with blanks```) and custom directives (used
	to mark up blocks introduced by a single line like
	``.. directive-name ::`` (the blanks before and after the
	directive name are significant).

	Here's the custom interpreted text roles:

	* *dl-id*: An publisher DID a service returns data for (used in 
	  datalink examples)
	* *taptable*: A (fully qualified) table name a TAP example query is
	  (particularly) relevant for; in HTML, this is also a link
	  to the table description.
	* *genparam*: A "generic parameter" as defined by DALI.  The values
	  of these have the form param(value), e.g., :genparam:\`POS(32,4)\`.
	  Right now, not parantheses are allowed in the value.  Complain
	  if this bites you.
	
	These are the custom directives:

	* *tapquery*: The query discussed in a TAP example.
	"""
	name = "examples"
	checkedRenderer = False
	customTemplate = svcs.loadSystemTemplate("examples.html")

	@classmethod
	def isCacheable(self, segments, request):
		return True

	def render_title(self, ctx, data):
		return ctx.tag["Examples for %s"%base.getMetaText(
			self.service, "title")]

	def data_examples(self, ctx, data):
		"""returns _Example instances from the service metadata.
		"""
		for ex in self.service.iterMeta("_example"):
			yield _Example(ex)


################## RST extensions
# When you add anything here, be sure to update the Examples docstring
# above.


### ...for TAP

def _taptableRoleFunc(name, rawText, text, lineno, inliner,
		options={}, content=[]):
	tablename = nodes.emphasis(rawText, text)
	tablename["classes"] = ["dachs-ex-taptable"]
	descr = nodes.reference(u"\u2197", u"\u2197",
		refuri="/tableinfo/%s"%text) 
	descr["classes"] = ["taptable-link"]
	return [descr, tablename], []

misctricks.RSTExtensions.makeTextRole("taptable", _taptableRoleFunc,
	propertyName="table")
del _taptableRoleFunc

class _TAPQuery(rst.Directive):
	has_content = True

	def run(self):
		body = "\n".join(self.content)
		res = nodes.literal_block(body, body)
		res["classes"] = ["dachs-ex-tapquery"]
		return [res]

misctricks.RSTExtensions.addDirective("tapquery", _TAPQuery,
	propertyName="query")
del _TAPQuery


### ...for datalink

misctricks.RSTExtensions.makeTextRole("dl-id")

### ...for DALI-style generic parameters

def _genparamRoleFunc(name, rawText, text, lineno, inliner,
		options={}, content=[]):
	mat = re.match(r"([^(]+)\(([^)]*)\)$", text)
	if not mat:
		msg = inliner.reporter.error(
			"genparam content must have the form key(value); %s does not."%text)
		return [inliner.problematic(rawText, rawText, msg)], [msg]
			
	key, value = mat.groups()

	formatted = """<span property="generic-parameter" typeof="keyval"
		class="generic-parameter">
		<span property="key" class="genparam-key">%s</span> =
		<span property="value" class="genparam-value">%s</span>
		</span>"""%(
			utils.escapePCDATA(rstutils.unescape(key, 1)),
			utils.escapePCDATA(rstutils.unescape(value, 1)))
	res = nodes.raw(
		rawsource=rawText,
		text=formatted,
		format='html')
	return [res], []

misctricks.RSTExtensions.makeTextRole("genparam", _genparamRoleFunc)
del _genparamRoleFunc

