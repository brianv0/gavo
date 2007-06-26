"""
This module contains code to format embedded querulator queries into
HTML forms.

This needs only the clauses -- the basic idea is that conditions come as
{{<human-readable key> |<sqlid> <op> <python expression>}}.

The python expression is evaluated, its result is pasted into the form.
This expression will usually be a function call.  All evaluations take
place in the namespace of the htmlgenfuncs module.  For the available
functions, see there.  The magic for that is happening in 
sqlparse.<whatever>.asHtml.

This module also contains querybuilders.  These are functions that check the
context for certain standard keys and modify the query to make it perform
the desired operations.  For example, buildConeSearchQuery looks for RA, DEC,
and SR and, if found, creates a c_x, c_y, c_z-based search.

XXX TODO: we probably want a querybuilder for products that automatically
includes owner and embaro fields.  However, since we copy the query,
adding fields doesn't make sense right now.  Not copying the query would
be a pain, too, since ensuring idempotency would be a nightmare and fiddling
around with instance variables in that way is uncool anyway.  We probably
want an abstract similar to querybuilder for adding "magic" fields; that
would probably happen at construction time.
"""

import re
import os

from gavo import sqlsupport
from gavo.web import querulator
from gavo.web.querulator import sqlparse
from gavo.web.querulator import condgens


# I doubt we want these.  Punt this at some point
_querybuilders = [
]


def getAvailableQueries(path):
	"""returns queries and folders for (templateRoot-relative) path.

	queries are returned as pairs of (query title, query path)
	for all queries defined in path.

	folders are pairs of (title, subdirectory) -- for these,
	getAvailableQueries might return more queries.
	"""
	queries = []
	folders = []
	templatePath = querulator.resolvePath(querulator.templateRoot, path)
	for fName in os.listdir(templatePath):
		if os.path.isfile(os.path.join(templatePath, fName)):
			if fName.endswith(".cq"):
				queries.append((os.path.splitext(fName)[0],
					os.path.join(path, fName)))
		if os.path.isdir(os.path.join(templatePath, fName)):
			folders.append((fName, os.path.join(path, fName)))
	return queries, folders


# these are a few quick'n'dirty macros.  If we actually want to do
# macros and stuff, we'll want to move these into a module of their
# own, like it's done with parsing
class MacroHandler:
	def __init__(self, template):
		self.template = template

	def querysel(self):
		jsHack = ('onChange="setQuery(this.form.qselect.options['
			'this.form.qselect.options.selectedIndex].value)"')
		jsFun = ('function setQuery(qpath) {'
			'document.location.href="%s/query/"+qpath;'
			'}'%querulator.rootURL)
		queries, _ = getAvailableQueries(
			os.path.dirname(self.template.getPath()))
		curPath = self.template.getPath()
		selectDict = {True: ' selected="selected"', False: ""}
		queries = [(title, path, selectDict[path==curPath])
			for title, path in queries]
		return ('<script type="text/javascript" language="javascript">%s</script>\n'
			'<form action=""><select name="qselect" size="1" %s>%s</select></form>'%(
			jsFun,
			jsHack,
			"\n".join(['<option value="%s"%s>%s</option>'%(path, isdefault, title)
				for title, path, isdefault in queries])))

	def legalblurb(self):
		return self.template.getLegal()


class Template:
	"""is a template with embedded configuration and SQL queries.
	"""
	def __init__(self, templatePath, rawText):
		self.path = templatePath
		self.rawText = rawText
		self._parse()

	def _parseMeta(self):
		self.metaItems = {}
		mat = querulator.metaElementPat.search(self.rawText)
		if mat:
			self.metaItems = dict([(key.strip(), value.strip())
				for key, value in
					[kv.split("=", 1) 
						for kv in mat.group(1).strip().split("\n")]])

	def _parse(self):
		self.query = sqlparse.parse(
			querulator.queryElementPat.search(
				self.rawText).group(2))
		self._parseMeta()
	
	def getPath(self):
		return self.path

	def getMeta(self, key):
		return self.metaItems[key]

	def getRaw(self):
		return self.rawText

	def getLegal(self):
		try:
			legalpath = os.path.join(os.path.dirname(
					querulator.resolveTemplate(self.getPath())),
				self.getMeta("LEGAL"))
			return '<div class="legal">%s</div>'%open(legalpath).read()
		except KeyError:
			pass
		return ""

	def _handleMacros(self, rawTx):
		macroHandler = MacroHandler(self)
		return re.sub(querulator.macroPat, lambda mat, m=macroHandler: eval(
			"m."+mat.group(1).strip()), rawTx)
	
	def asHtml(self, formTemplate, context):
		return self._handleMacros(
			querulator.metaElementPat.sub("",
				querulator.queryElementPat.sub(
					lambda mat: formTemplate%self.query.asHtml(context), self.rawText)))

	def asSql(self, context):
		"""returns a pair of query, arguments for the currenty query plus
		any automatic queries and the values in context.
		"""
		query = self.query.copy()
		for querybuilder in _querybuilders:
			querybuilder(query, context)
		return query.asSql(context)

	def getItemdefs(self):
		return self.query.getItemdefs()

	def getDefaultTable(self):
		return self.query.getDefaultTable()

	def getProductCols(self):
		return [index 
			for index, itemdef in enumerate(self.getItemdefs())
				if itemdef["hint"]=="product"]
	
	def getHiddenForm(self, context):
		"""returns an html form body setting all relevant query parameters
		from context in hidden fields.

		This can be used to reproduce queries with different meta parameters.
		("this stuff as tar", "this stuff as votable").

		As a special hack, query arguments with names starting with "submit"
		will not be included.  This is done because we use these to
		distinguish between various products.
		"""
		formItems = []
		for name, value in context.iteritems():
			if name.startswith("submit"):
				continue
			if isinstance(value, list):
				for item in value:
					formItems.append('<input type="hidden" name="%s" value=%s>'%(
						name, repr(str(item))) )
			else:
				formItems.append('<input type="hidden" name="%s" value=%s>'%(
					name, repr(str(value))) )
		return "\n".join(formItems)

	def getProductSizes(self, context):
		"""returns the total size of all products.

		This, of course, will only work for tables actually implementing
		the product interface (in this case, the fsize field is used).
		"""
		newquery = sqlparse.Query(sqlparse.selectItems.parseString(
			"{{fsize||int}}")[0], self.query.defaultTable, self.query.tests)
		querier = sqlsupport.SimpleQuerier()
		res = querier.query(*newquery.asSql(context))
		return sum([int(size[0]) for size in res.fetchall() if size[0]])
	
	def getConditionsAsText(self, context):
		"""returns a "barely-user-compatible" form of the query.

		I guess we should have methods rendering this at some point.
		"""
		condTexts = []
		for node in self.query.getConditions():
			if isinstance(node, condgens.CondGen):
				tx = node.asCondition(context)
				if tx:
					condTexts.append(tx)
		return condTexts
	
	def addConjunction(self, sqlCondition):
		"""see Query.addConjunction
		"""
		self.query.addConjunction(sqlCondition)

	def setSelectItems(self, items):
		"""see Query.setSelectItems
		"""
		self.query.setSelectItems(items)


def makeTemplate(templatePath):
	"""returns a template instance for the template in templatePath.

	This indirection is present because at some point we may want to
	instanciate different kinds of templates, depending on, e.g.,
	path, extension or content of the template.
	"""
	rawTxt = open(querulator.resolveTemplate(templatePath)).read()
	return Template(templatePath, rawTxt)


def getForm(template, context):
	"""returns templateTxt with the a form for the sqlparse.Query
	instance query filled in.

	The submit buttons need names so we can later distinguish what
	type of product was requested.  To avoid their inclusion into
	the hidden forms used for resubmitting a query, these names all
	have to start with "submit".  It's a hack, but I think it's not
	a bad one.
	"""
	moreFormMaterial = []
	moreFormMaterial.append('\n<input type="submit" value="Table as VOTable"'
		' name="submit-votable">\n')
	formTemplate = ('\n<form class="querulator" method="post"'
		' action="%(rootUrl)s/run/%(templatePath)s">\n'
		'%%s'
		'\n<p><input type="submit" value="Table as HTML" name="submit">\n'
		'%(moreFormMaterial)s</p>'
		'</form>')%{
			"templatePath" : template.getPath(),
			"rootUrl": querulator.rootURL,
			"moreFormMaterial": "\n".join(moreFormMaterial),
			}
	return template.asHtml(formTemplate, context)
