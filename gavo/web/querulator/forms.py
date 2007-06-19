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
from gavo import coords
from gavo.web import querulator
from gavo.web.querulator import sqlparse


def _buildConeSearchQuery(query, context):
	"""adds a global conjunction to ensure all matches are within a cone.

	This is supposed to implement the simple cone search spec of IVOA.
	Trouble in the moment: We don't look at equinoxes. This could probably
	be solved by storing equinox info in the context as necessary.
	"""
	if not context.checkArguments(["RA", "DEC", "SR"]):
		return
	c_x, c_y, c_z = coords.computeUnitSphereCoords(
		float(context.getfirst("RA")), float(context.getfirst("DEC")))
	query.addConjunction(sqlparse.LiteralCondition(
		"sqrt((%f-c_x)^2+(%f-c_y)^2+(%f-c_z)^2)"%(c_x, c_y, c_z),
		"<=", str(float(context.getfirst("SR"))/360)))


_querybuilders = [
	_buildConeSearchQuery,
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
		return ('<script language="javascript">%s</script>\n'
			'<form><select name="qselect" size="1" %s>%s</select></form>'%(
			jsFun,
			jsHack,
			"\n".join(['<option value="%s"%s>%s</option>'%(path, isdefault, title)
				for title, path, isdefault in queries])))

	def legalblurb(self):
		return self.template.getLegal()


class Template:
	"""is a template with embedded configuration and SQL queries.
	"""
	def __init__(self, templatePath):
		self.path = templatePath
		self.rawText = open(querulator.resolveTemplate(templatePath)).read()
		self._parse()

	def _parseMeta(self, rawMetas):
		self.metaItems = dict([(key.strip(), value.strip())
			for key, value in
				[kv.split("=", 1) 
					for kv in rawMetas.strip().split("\n")]])

	def _parse(self):
		self.query = sqlparse.simpleSql.parseString(
			querulator.queryElementPat.search(
				self.rawText).group(1))[0]
		mat = querulator.metaElementPat.search(self.rawText)
		if mat:
			self._parseMeta(mat.group(1))
		else:
			self.metaItems = {}
	
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
	
	def asHtml(self, formTemplate):
		return self._handleMacros(
			querulator.metaElementPat.sub("",
				querulator.queryElementPat.sub(
					lambda mat: formTemplate%self.query.asHtml(), self.rawText)))

	def asSql(self, context):
		query = self.query.copy()
		for querybuilder in _querybuilders:
			querybuilder(query, context)
		return query.asSql(context.keys())

	def getItemdefs(self):
		return self.query.getItemdefs()

	def getDefaultTable(self):
		return self.query.getDefaultTable()

	def getProductCols(self):
		return [index 
			for index, itemdef in enumerate(self.getItemdefs())
				if itemdef["hint"]=="product"]
	
	def _getVarInfos(self):
		varInfos = {}
		for node in self.query:
			try:
				varInfos.update(node.getQueryInfo())
			except AttributeError:
				pass
		return varInfos
	
	def getQueryArguments(self, context):
		"""returns a dictionary suitable as argument for dbapi2 cursor.execute
		from the values given in context.
		"""
		varInfos = self._getVarInfos()
		valDict = {}
		getterDict = {
			'l': context.getlist,
			'a': context.getfirst,
		}
		for key in context.keys():
			if varInfos.has_key(key):
				valDict[key] = getterDict[varInfos[key][0]](key)
		return valDict
	
	def getHiddenForm(self, context):
		"""returns an html form body setting all relevant query parameters
		from context in hidden fields.

		This can be used to reproduce queries with different meta parameters.
		("this stuff as tar", "this stuff as votable").
		"""
		formItems = []
		for name, value in self.getQueryArguments(context).iteritems():
			if len(value)>1:
				for item in value:
					formItems.append('<input type="hidden" name="%s" value=%s>'%(
						name, repr(str(item))) )
			elif len(value)==1:
				formItems.append('<input type="hidden" name="%s" value=%s>'%(
					name, repr(str(value))) )
		return "\n".join(formItems)

	def getProductSizes(self, form):
		"""returns the total size of all products.

		This is a major hack -- we assume that, if there's a product
		in the query, there's also an fsize field that gives the size
		of the product.  This is what we sum and return.

		To do this, we need to do major surgery on the query object.
		It's one big pain in the neck.

		We ought to figure out a better way to do this, but that would
		probably require a much better description of the data set.
		"""
		newquery = sqlparse.Query(sqlparse.selectItems.parseString(
			"{{fsize||int}}")[0], self.query.defaultTable, self.query.tests)
		querier = sqlsupport.SimpleQuerier()
		res = querier.query(newquery.asSql(set(form.keys())), 
			self.getQueryArguments(form))
		return sum([int(size[0]) for size in res.fetchall() if size[0]])
	
	def getConditionsAsText(self, context):
		"""returns a "barely-user-compatible" form of the query.

		I guess we should have methods rendering this at some point.
		"""
		condTexts = []
		pars = self.getQueryArguments(context)
		for node in self.query.getConditions():
			if isinstance(node, sqlparse.CondTest):
				tx = node.asCondition(context)%pars
				if tx:
					condTexts.append(tx)
		return condTexts
	
	def addConjunction(self, sqlCondition):
		"""adds the sql search condition as an AND clause to the current Query.

		sqlCondition has to match the clauses production in sqlparse.
		"""
		self.query.addConjunction(sqlCondition)


def getForm(template):
	"""returns templateTxt with the a form for the sqlparse.Query
	instance query filled in.
	"""
	moreFormMaterial = []
#	if template.getProductCols():
#		moreFormMaterial.append(
#			'\n<input type="submit" value="Products as tar" name="tar">\n')
	moreFormMaterial.append(
		'\n<input type="submit" value="Table as VOTable" name="votable">\n')
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
	return template.asHtml(formTemplate)
