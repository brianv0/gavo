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
import urllib

from gavo import sqlsupport
from gavo import config
from gavo.web import common
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
	templatePath = common.resolvePath(config.get(
		"querulator", "templateRoot"), path)
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
			'}'%config.get("web", "rootURL"))
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


class AbstractTemplate:
	"""is a model for a template.

	A template is HTML with embedded stuff in <?...?> pseudo elements.
	This HTML is read from the full path srcPath.
	"""
	def __init__(self, srcPath):
		self.fullPath = srcPath
		f = open(srcPath)
		self.rawText = f.read()
		f.close()
		self._parseMeta()

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

	def getFullPath(self):
		"""returns the relative path to the template source.
		"""
		return self.fullPath

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
					self.getFullPath()),
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

	def asHtml(self, context):
		"""returns html for a query page.

		This method will call _handlePrivateElements -- this method
		has to be filled in by deriving classes.  It has to take
		a context and some text and must return a string in which the
		elements specific to the derived template class are substituted
		by forms or whatever the deriving class desires.
		"""
		return self._handleMacros(
			querulator.metaElementPat.sub("",
				self._handlePrivateElements(self.rawText, context)))


class Template(AbstractTemplate):
	"""is a template for querulator (i.e. support for <?query ...?>)

	The content of query is an SQL select statement with embedded markup.

	Templates should know about interfaces.  Currently, only the product
	interface is relevant, so it's handled by hand.  If there is any
	formatting hint "product" present in the select list, it is assumed
	that the table supports the product interface and suppressed fields
	owner, embargo, and accsize are added.

	XXX TODO: Template should be immutable, i.e., all the crap manipulating
	query should go.  Instead, templates should return a query object with
	all the manipulation methods.  The query object can be discarded,
	the template could live on.
	"""
	def __init__(self, templatePath):
		self.path = templatePath
		AbstractTemplate.__init__(self, querulator.resolveTemplate(templatePath))
		self._parseQuery()
		self._handleInterfaces()

	def getPath(self):
		return self.path

	def getName(self):
		return os.path.splitext(self.getPath())[0]

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
		fields from the corresponding interface (e.g. accsize, owner and embago
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
			self.addSelectItem("accsize||suppressed")

	def _getSortForm(self, context):
		return '<select name="sortby">%s</select>'%(
			"\n".join(['<option value=%s>%s</option>'%(repr(item.sqlExpr),
					item.sqlExpr)
				for item in self.query.getSelectItems() 
					if not item.displayHint=="suppressed"]))

	def _getLimitForm(self, context):
		items = [
			(100, 100, ""),
			(1000, 1000, ' selected="selected"'),
			(5000, 5000, ""),
			("all", "No limit", ""),]
		return '<select name="limitto">%s</select>'%(
			"\n".join(['<option value="%s"%s>%s</option>'%(val, opt, title)
				for val, title, opt in items]))

	def _getAutoFields(self, context):
		"""returns form fields for the "built-in" query aspects.

		This includes sort order and match limit.
		"""
		return ('<div id="autofields"><div class="autofield">Sort by: %s</div>'
				'<div class="autofield">Match limit: %s</div></div>')%(
			self._getSortForm(context),
			self._getLimitForm(context))

	def _getFormContent(self, context):
		"""returns a standard query form for the query.
		"""
		return "%s\n%s\n"%(self.query.asHtml(context), 
			self._getAutoFields(context))

	def _getForm(self, context):
		"""returns HTML for a form containing all fields required by the
		condition generators of self.query.
		"""
		return ('\n<form class="querulator" method="post"'
			' action="%(rootURL)s/run/%(templatePath)s">\n'
			'%(formItems)s'
			'%(submitButtons)s'
			'</form>')%{
				"formItems": self._getFormContent(context),
				"templatePath" : self.getPath(),
				"rootURL": config.get("web", "rootURL"),
				"submitButtons": common.getSubmitButtons(context),
				}

	def _handlePrivateElements(self, rawText, context):
		"""returns rawText with any <?query ?> elements substituted
		by a form generating a query for the the sql statement in there.
		"""
		return querulator.queryElementPat.sub(self._getForm(context), rawText)

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
			context.addWarning("The sort expression you gave (%s)"
				" was not in the set of allowed query keys.  Results"
				" cropped by the query limit may be inconsistent."%passedExpr)
			return ""
	
	def _getLimitClause(self, context):
		"""returns an appropriate "LIMIT" clause for the current query.

		We first see if theres a "limitto" parameter in the context that's
		either a number or all.  If it's given, we use that.  Otherwise
		the config's querulator.defaultMaxMatches parameter kicks in.

		As a side effect, this method leaves the limit given to postgresql
		in a used_limit context argument, so table builders can check
		against it and warn if the limit has been reached.
		"""
		limit = context.getfirst("limitto")
		if limit==None or not re.match(r"\d+$|all", limit.lower()):
			limit = config.get("querulator", "defaultMaxMatches")
		if limit=="all":
			context.addArgument("used_limit", 1e30) # ok, it's a hack
		else:
			context.addArgument("used_limit", int(limit))
		return "LIMIT %s"%limit

	def asSql(self, context):
		"""returns a pair of query, arguments for the currenty query plus
		any automatic queries and the values in context.
		"""
		query = self.query.copy()
		for querybuilder in _querybuilders:
			querybuilder(query, context)
		q, args = query.asSql(context)
		return "%s %s %s"%(q, self._getOrderClause(context), 
			self._getLimitClause(context)), args

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
				if "product" in itemdef["hint"]]
		if len(productCols)==0:
			return None
		elif len(productCols)==1:
			return productCols[0]
		else:
			raise querulator.Error("More than one product hint in query")

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

	def getConditionsAsFieldInfos(self, context):
		"""returns a sequence of fieldInfos for the condition generators
		defined here.

		Of course, CondGens know nowhere near enough about what to expect
		to make these fieldInfos really useful, but for simple WSDL generation
		it should do.
		"""
		fieldInfos = []
		for node in self.query.getConditions():
			if isinstance(node, condgens.CondGen):
				fieldInfos.extend(node.getFieldInfos())
		return fieldInfos

	def addConjunction(self, sqlCondition):
		"""see sqlparse.Query.addConjunction.
		"""
		self.query.addConjunction(sqlCondition)

	def setSelectItems(self, items):
		"""see sqlparse.Query.setSelectItems.
		"""
		self.query.setSelectItems(items)

	def addSelectItem(self, item):
		"""see sqlparse.Query.addSelectItem.
		"""
		self.query.addSelectItem(item)
	
	def getColIndexFor(self, colExpr):
		"""see sqlparse.Query.getcolIndexFor.
		"""
		return self.query.getColIndexFor(colExpr)

	def runQuery(self, context):
		sqlQuery, args = self.asSql(context)
		querier = context.getQuerier()
		return querier.query(sqlQuery, args).fetchall()

