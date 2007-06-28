"""
This module contains code to format embedded querulator queries into
HTML forms.

This needs only the clauses -- the basic idea is that conditions come as
{{<human-readable key> |<sqlid> <op> <python expression>}}.

The python expression is evaluated within the condgen module's namespace
and should yield an condgen (or anything with asHtml, asSql, and asCondition
methods).  This condgen is then used to construct forms and queries.
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

	Templates should know about interfaces.  Currently, only the product
	interface is relevant, so it's handled by hand.  If there is any
	formatting hint "product" present in the select list, it is assumed
	that the table supports the product interface and suppressed fields
	owner, embargo, and fsize are added.
	"""
	def __init__(self, templatePath, rawText):
		self.path = templatePath
		self.rawText = rawText
		self._parseQuery()
		self._parseMeta()
		self._handleInterfaces()

	def _parseMeta(self):
		"""adds a metaItems attribute filled from the ?meta element in the source.

		Used by the constructor only.
		"""
		self.metaItems = {}
		mat = querulator.metaElementPat.search(self.rawText)
		if mat:
			self.metaItems = dict([(key.strip(), value.strip())
				for key, value in
					[kv.split("=", 1) 
						for kv in mat.group(1).strip().split("\n")]])

	def _parseQuery(self):
		"""parses the sql query source, setting the query attribute to
		the parse tree.

		Used by the constructor only.
		"""
		self.query = sqlparse.parse(
			querulator.queryElementPat.search(
				self.rawText).group(2))

	def _handleInterfaces(self):
		"""adds fields from gavo interfaces if it detects their necessity.

		This works by checking certain properties of the query (e.g., the
		presence of a "product" hint in a select item) and then appending
		fields from the corresponding interface (e.g. fsize, owner and embago
		for products) to the list of select items.  All added fields are
		suppressed.  If a field is already present in a non-suppressed form,
		it is not added.

		Since we only have the product interface to worry about right now,
		this code is not too sophisticated -- let's see what happens if
		we have more cases like this.
		"""
		if self.getProductCol()!=None:
			self.addSelectItem("owner||suppressed")
			self.addSelectItem("embargo||suppressed")
			self.addSelectItem("fsize||suppressed")

	def getPath(self):
		"""returns the relative path to the template source.
		"""
		return self.path

	def getMeta(self, key):
		"""returns the meta item key.

		It raises a KeyError if the key is not given.
		"""
		return self.metaItems[key]

	def getLegal(self):
		"""returns the content of the file pointed to by the
		LEGAL item in meta.

		The value of LEGAL is supposed to be relative to the
		location of the template source.
		"""
		try:
			legalpath = os.path.join(os.path.dirname(
					querulator.resolveTemplate(self.getPath())),
				self.getMeta("LEGAL"))
			return '<div class="legal">%s</div>'%open(legalpath).read()
		except KeyError:
			pass
		return ""

	def _handleMacros(self, rawTx):
		"""expands "macros" in the source.

		See MacroHandler's doc for more information.
		"""
		macroHandler = MacroHandler(self)
		return re.sub(querulator.macroPat, lambda mat, m=macroHandler: eval(
			"m."+mat.group(1).strip()), rawTx)
	
	def asHtml(self, formTemplate, context):
		"""returns html for the complete page.

		formTemplate is a string containing a single %s that will be substituted
		by the form fields generated by self.query.  It should, in general,
		provide <form>-container and any submit buttons you need.  The
		formTemplate with the substituted string is then pasted in in place of
		the <?query?> in the template source.
		"""
		return self._handleMacros(
			querulator.metaElementPat.sub("",
				querulator.queryElementPat.sub(
					lambda mat: formTemplate%self.query.asHtml(context), self.rawText)))

	def _getOrderClause(self, context):
		"""returns an appropriate "ORDER BY" clause for the current query.

		This is done by first checking for a sortby element in the context,
		(which has to match an sqlExpression of one of the fields); if that
		doesn't work, we use the sqlExpression of the first column.  If
		none is given, we return the empty string.
		"""
		if not context.hasArgument("sortby"):
			context.addArgument("sortby", self.query.getSelectItems()[0].sqlExpr)
		passedExpr = context.getfirst("sortby")
		for selItem in self.query.getSelectItems():
			if selItem.sqlExpr==passedExpr:
				return " ORDER BY "+passedExpr
		else:
			raise querulator.Error("The sort expression you gave (%s)"
				" is not in the set of allowed query keys.")
		
	def asSql(self, context):
		"""returns a pair of query, arguments for the currenty query plus
		any automatic queries and the values in context.
		"""
		query = self.query.copy()
		for querybuilder in _querybuilders:
			querybuilder(query, context)
		q, args = query.asSql(context)
		return q+self._getOrderClause(context), args

	def getItemdefs(self):
		"""returns a list of (name, dbtype, info) tuples for all items in
		the select list.
		"""
		return self.query.getItemdefs()

	def getDefaultTable(self):
		"""returns the name of the table being queried.
		"""
		return self.query.getDefaultTable()

	def getProductCol(self):
		"""returns the column index of the product column.

		A product is identified by its formatting hint.  You can decide
		if you have a table containing products by checking if this function
		returns None.

		A table satisfying the product interface has exactly one product
		column (since otherwise things like fsize would be ill-defined).
		This function raises an exception if more than one column with a 
		product hint is present.
		"""
		productCols = [index 
			for index, itemdef in enumerate(self.getItemdefs())
				if itemdef["hint"]=="product"]
		if len(productCols)==0:
			return None
		elif len(productCols)==1:
			return productCols[0]
		else:
			raise querulator.Error("More than one product hint in query")
	
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
			if name=="sortby":
				continue
			if isinstance(value, list):
				for item in value:
					formItems.append('<input type="hidden" name="%s" value=%s>'%(
						name, repr(str(item))) )
			else:
				formItems.append('<input type="hidden" name="%s" value=%s>'%(
					name, repr(str(value))) )
		return "\n".join(formItems)

	def getProductsSize(self, queryResult, context):
		"""returns the total size of all products in queryResult.

		This, of course, will only work for tables actually implementing
		the product interface and having products mentioned.
		"""
		sizeCol = self.query.getColIndexFor("fsize")
		if sizeCol==None:
			raise querulator.Error("No size information available.")
		ownerCol, embargoCol = self.getColIndexFor("owner"
			), self.getColIndexFor("embargo")
		return sum([int(row[sizeCol]) for row in queryResult
			if context.isAuthorizedProduct(row[embargoCol], row[ownerCol]) and
					row[sizeCol]])
	
	def getConditionsAsText(self, context):
		"""returns a "barely-user-compatible" form of the query.
		"""
		condTexts = []
		for node in self.query.getConditions():
			if isinstance(node, condgens.CondGen):
				tx = node.asCondition(context)
				if tx:
					condTexts.append(tx)
		return condTexts
	
	def addConjunction(self, sqlCondition):
		"""see Query.addConjunction.
		"""
		self.query.addConjunction(sqlCondition)

	def setSelectItems(self, items):
		"""see Query.setSelectItems.
		"""
		self.query.setSelectItems(items)

	def addSelectItem(self, item):
		"""see Query.addSelectItem.
		"""
		self.query.addSelectItem(item)
	
	def getColIndexFor(self, colExpr):
		"""see Query.getcolIndexFor.
		"""
		return self.query.getColIndexFor(colExpr)


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
