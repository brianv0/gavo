"""
This module contains code to query and format the database according to
querulator templates.
"""

import os
import re
import sys
import urllib
import urlparse
import cStringIO
import tarfile
import math
from mx import DateTime

import gavo
from gavo import sqlsupport
from gavo import votable
from gavo import config
from gavo.web import voplot
from gavo.web import querulator
from gavo.web.querulator import sqlparse


_resultsJs = """
<script type="text/javascript" language="javascript">
emptyImage = new Image();
emptyImage.src = "%(staticURL)s/empty.png";

function showThumbnail(srcUrl) {
	thumb = new Image();
	thumb.src = srcUrl;
	window.document.getElementById("thumbtarget").src = thumb.src;
}

function clearThumbnail() {
	window.document.getElementById("thumbtarget").src = emptyImage.src;
}
</script>
"""%{
	"staticURL": config.get("web", "staticURL"),
}

_thumbTarget = """
<img src="%s/empty.png" id="thumbtarget" 
	style="position:fixed;top:0px;left:0px">
"""%(config.get("web", "staticURL"))


class UniqueNameGenerator:
	"""is a factory to build unique file names from possibly ambiguous ones.

	If the lower case of a name is not known to an instance, it just returns
	that name.  Otherwise, it disambiguates by adding characters in front
	of the extension.
	"""
	def __init__(self):
		self.knownNames = set()

	def _buildNames(self, baseName):
		base, ext = os.path.splitext(baseName)
		yield baseName
		i = 1
		while True:
			yield "%s-%03d%s"%(base, i, ext)
			i += 1

	def makeName(self, baseName):
		for name in self._buildNames(baseName):
			if name.lower() not in self.knownNames:
				self.knownNames.add(name)
				return name


def _isTruncated(queryResult, context):
	"""returns true if queryResult is likely to be truncated due to a limit
	clause.
	"""
	return len(queryResult)==context.getfirst("used_limit")


def _formatAsVoTable(template, context, stream=True, verbosity=None):
	"""returns a callable that writes queryResult as VOTable.

	Verbosity is an integer or None.  If it's None or <=0, the select items
	given in the query are used to decide which fields to include
	into the VOTable and how to format them.  If it's an integer>0,
	we return all fields from the primary table with fields with
	votImportance >= verbosity.

	Regardless of verbosity, if a VERB is in the context, verbosity will
	be set to VERB*10.
	"""
# XXXXXXXX TODO: I guess this belongs into the context.  We'd just need
# a sane way to store junk like this.
	def productMapperFactory(srcInstance, colProps):
		if colProps.get("displayHint")=="product":
			def coder(val):
				if val==None:
					return "Embargoed"
				return urlparse.urljoin(context.getServerURL(),
					"%s/getproduct?path=%s"%(config.get("web", "rootURL"), 
					urllib.quote(val)))
			return coder

	def getSelectItemFieldInfos(template, context):
		"""returns the field infos for the response columns when they
		are given by the SQL query.

		As a side effect, fields unsuitable for VOTables are purged from
		the SQL select items.
		"""
		fieldInfos = []
		metaTable = sqlsupport.MetaTableHandler(context.getQuerier())
		defaultTableName = template.getDefaultTable()
		newSelectItems = []
		for itemDef in template.getItemdefs():
			try:
				fieldInfos.append(metaTable.getFieldInfo(
					itemDef["name"], defaultTableName))
				newSelectItems.append(sqlparse.SelectItem(itemDef["name"],
					itemDef["title"], itemDef["hint"]))
			except sqlsupport.FieldError:
				# ignore this field for a VOTable
				pass
		template.setSelectItems(sqlparse.SelectItems(
			*newSelectItems))
		return fieldInfos

	def getFieldInfos(template, context, verbosity):
		"""returns the field infos for the response columns when they are
		computed from the verbosity.

		As a side effect, the select items of the SQL query are set
		to what the desired verbosity suggests.
		"""
		metaTable = sqlsupport.MetaTableHandler(context.getQuerier())
		fieldInfos = []
		for info in metaTable.getFieldInfos(template.getDefaultTable()):
			if info["verbLevel"]==None or info["verbLevel"]<=verbosity:
				fieldInfos.append(info)
		template.setSelectItems(sqlparse.SelectItems(
			*[sqlparse.SelectItem(info["fieldName"], "",
					info.get("displayHint", "string").split(",")) 
				for info in fieldInfos]))
		return fieldInfos

	if context.hasArgument("VERB"):
		verbosity = int(context.getfirst("VERB"))*10
	if verbosity==None or verbosity<=0:
		fieldInfos = getSelectItemFieldInfos(template, context)
	else:
		fieldInfos = getFieldInfos(template, context, verbosity)
	rows = template.runQuery(context)
	
	mapperFactory = votable.getMapperRegistry()
	mapperFactory.registerFactory(productMapperFactory)
	tdEncoding = not not context.get("tabledataEnc")
	if stream:
		def produceOutput(outputFile):
			votable.writeSimpleTable(fieldInfos, rows, {}, 
				outputFile, tdEncoding=tdEncoding, mapperFactory=mapperFactory)
		return produceOutput
	
	else:
		f = cStringIO.StringIO()
		votable.writeSimpleTable(fieldInfos, rows, {}, f, tdEncoding=tdEncoding,
			mapperFactory=mapperFactory)
		return f.getvalue()


def _makeSortButton(fieldName, template, context):
	"""returns a form asking for the content re-sorted to fieldName.
	"""
	hiddenForm = context.getHiddenForm(suppress=["sortby"])
	if not hiddenForm:
		return ""
	buttonTemplate = ('<img src="%s/%%(img)s" alt="%%(alt)s"'
		' title="%%(title)s" class="sortButton">')%config.get("web", "staticURL")
	if context.getfirst("sortby")==fieldName:
		title = "Sorted by %s"%fieldName.replace('"', '')
		buttonImage = buttonTemplate%{"img": "sortedArrow.png", "alt": "V",
			"title": title}
	else:
		title = "Sort by %s"%fieldName.replace('"', '')
		buttonImage = buttonTemplate%{"img": "toSortArrow.png", "alt": "v",
			"title": title}
	return ('<form action="%(rootURL)s/run/%(tPath)s" method="post"'
		' class="sortArrow">'
		'%(hiddenform)s'
		'<input type="hidden" name="sortby" value="%(keyname)s">'
		'<button type="submit" name="submit" class="transparent"'
		' title="%(title)s">'
		'%(buttonImage)s</button>'
		'</form>'
	)%{
		"rootURL": config.get("web", "rootURL"),
		"tPath": template.getPath(),
		"hiddenform": hiddenForm,
		"keyname": urllib.quote(fieldName),
		"buttonImage": buttonImage,
		"title": title,
	}


def _getHeaderRow(template, context):
	"""returns a header row and a row with sort buttons for HTML table output.
	"""
	plainHeader = ['<tr>']
	sortLine = ['<tr>']
	itemdefs = template.getItemdefs()
	metaTable = sqlsupport.MetaTableHandler(context.getQuerier())
	defaultTableName = template.getDefaultTable()
	for itemdef in itemdefs:
		if itemdef.get("hint")[0]=="suppressed":
			continue
		additionalTag, additionalContent = "", ""
		if itemdef["title"]:
			title =  itemdef["title"]
		else:
			fieldInfo = metaTable.getFieldInfo(itemdef["name"], defaultTableName)
			title = fieldInfo["tablehead"]
			if fieldInfo["description"]:
				additionalTag += " title=%s"%repr(fieldInfo["description"])
			if fieldInfo["unit"]:
				additionalContent += "<br>[%s]</br>"%fieldInfo["unit"]
		plainHeader.append("<th%s>%s%s</th>"%(
			additionalTag, title, additionalContent))
		sortLine.append("<td>%s</td>"%(_makeSortButton(itemdef["name"], 
			template, context)))
	plainHeader.append("</tr>")
	sortLine.append("</tr>")
	return "".join(plainHeader), "".join(sortLine)


def _formatSize(anInt):
	"""returns a size in a "human-readable" form.
	"""
	if anInt<2000:
		return "%dB"%anInt
	if anInt<2000000:
		return "%dk"%(anInt/1000)
	if anInt<2000000000:
		return "%dM"%(anInt/1000000)
	return "%dG"%(anInt/1000000000)


def _makeTarForm(template, context, queryResult):
	"""returns html for a form to get products as tar.
	"""
	doc = []
	if template.getProductCol()!=None:
		doc.append('<form action="%s/run/%s" method="post" class="tarForm">\n'%(
			config.get("web", "rootURL"), template.getPath()))
		doc.append(context.getHiddenForm(suppress=["outputFormat"]))
		sizeEstimate = template.getProductsSize(queryResult, context)
		if not sizeEstimate:
			return ""
		sizeEstimate = ' (approx. %s)'%_formatSize(sizeEstimate)
		doc.append('<input type="hidden" name="outputFormat" value="tar">')
		doc.append('<input type="submit" value="Get tar of matched products%s">\n'
			%sizeEstimate)
		doc.append('</form>')
	return "\n".join(doc)


class HtmlValueFormatter:
	"""is a container for functions that format values from the
	database for HTML.

	There is a special hint "suppressed" that makes any call to format
	return None.  Formatter clients are supposed to ignore such fields,
	whatever that may mean for the formatter.

	This means that format may never return None for non-suppressed fields.
	The format method substitutes any None by "N/A".
	"""
	def __init__(self, template, context):
		self.template = template
		self.context = context

	def _htmlEscape(self, value):
		return str(value).replace("&", "&amp;").replace("<", "&lt;")

	def _cook_date(self, value, row):
		"""(should check if value is a datetime instance...)
		"""
		return str(value).split()[0]

	def _cook_juliandate(self, value, row):
		"""(should check if value really is mx.DateTime)
		"""
		return value.jdn

	def _cook_product(self, path, row):
		"""returns pieces to format a product URL.
		
		Specifically, it qualifies path to a complete URL for the product and
		returns this together with a relative URL for a thumbnail and a
		sufficiently sensible title.
		"""
		owner, embargo = row[self.template.getColIndexFor("owner")
			],row[self.template.getColIndexFor("embargo")]
		if self.context.isAuthorizedProduct(embargo, owner):
			productUrl = urlparse.urljoin(self.context.getServerURL(),
			"%s/getproduct/%s?path=%s"%(config.get("web", "rootURL"), 
			self.template.getPath(), urllib.quote(path)))
			title = os.path.basename(path)
		else:
			productUrl = None
			title = "Embargoed through %s"%embargo.strftime("%Y-%m-%d")
		return productUrl, \
			"%s/thumbnail/%s?path=%s"%(config.get("web", "rootURL"),
			self.template.getPath(), urllib.quote(path)),\
			title

	def _cook_aladinload(self, path, row):
		"""wraps path into a URL that can be sent to aladin for loading the image.
		"""
		return urlparse.urljoin(self.context.getServerURL(),
			"%s/getproduct/%s?path=%s"%(config.get("web", "rootURL"),
			self.template.getPath(), urllib.quote(path)))

	def _cook_feedback(self, key, row, targetTemplate=None):
		if targetTemplate==None:
			targetTemplate = self.template.getPath()
		return urlparse.urljoin(self.context.getServerURL(),
			"%s/query/%s?feedback=%s"%(config.get("web", "rootURL"), targetTemplate,
				urllib.quote(key)))

	def _cook_hourangle(self, deg, row, secondFracs=2):
		"""converts a float angle in degrees to an hour angle.
		"""
		secondFracs = int(secondFracs)
		rest, hours = math.modf(deg/360.*24)
		rest, minutes = math.modf(rest*60)
		return "%d %02d %2.*f"%(int(hours), int(minutes), secondFracs, rest*60)

	def _cook_sexagesimal(self, deg, row, secondFracs=1):
		"""converts a float angle in degrees to a sexagesimal angle.
		"""
		secondFracs = int(secondFracs)
		rest, degs = math.modf(deg)
		rest, minutes = math.modf(rest*60)
		return "%+d %02d %2.*f"%(int(degs), abs(int(minutes)), secondFracs,
			abs(rest*60))

	def _product_to_html(self, args):
		prodUrl, thumbUrl, title = args
		if prodUrl==None:
			return title
		else:
			return ('<a href="%s">%s</a><br>'
				'<a href="%s"  target="thumbs"'
				' onMouseover="showThumbnail(\''
				'%s\')" onMouseout="clearThumbnail()">'
				'[preview]</a>')%(
				prodUrl,
				title,
				thumbUrl, thumbUrl)

	def _url_to_html(self, url, title=None):
		if title==None:
			title = "[%s]"%self._htmlEscape(urlparse.urlparse(value)[1])
		return '<a href="%s">%s</a>'%(self._htmlEscape(url), title)

	def _feedback_to_html(self, url):
		return self._url_to_html(url, "[Find similar]")

	def _aladinquery_to_html(self, value):
		aladinPrefix = ("http://aladin.u-strasbg.fr/java/nph-aladin.pl"
			"?frame=launching&script=get%20aladin%28%29%20")
		return '<a href="%s%s" target="aladin">[Aladin]</a>'%(
			aladinPrefix, urllib.quote(value))

	def _aladinload_to_html(self, value):
		aladinPrefix = ("http://aladin.u-strasbg.fr/java/nph-aladin.pl"
			"?frame=launching&script=load%20")
		return '<a href="%s%s" target="aladin">[Aladin]</a>'%(
			aladinPrefix, urllib.quote(value))
	
	def _simbad_to_html(self, value):
		value = re.sub(r"(\d)\s+(\d)", r"\1+\2", value.strip())
		value = re.sub("\s*[+-]s\*", r"d\g<0>", value)+"d"
		simbadURL = ("http://simbad.u-strasbg.fr/simbad/sim-coo?Coord=%s"
			"&Radius=1")%urllib.quote(value)
		return '<a href="%s">[Simbad]</a>'%self._htmlEscape(simbadURL)

	def _hourangle_to_html(self, value):
		return value.replace(" ", "&nbsp;")
	_sexagesimal_to_html = _hourangle_to_html

	def _string_to_html(self, value):
		return self._htmlEscape(value)

	def format(self, hint, value, row):
		if hint[0]=="suppressed":
			return None
		if value==None:
			return "N/A"
		cooker = getattr(self, "_cook_%s"%hint[0], lambda a, row: a)
		formatter = getattr(self, "_%s_to_html"%(hint[0]),
			lambda *a: a[0])
		res = formatter(cooker(value, row, *hint[1:]))
		return res


def _formatAsHtml(template, context):
	"""returns an HTML formatted table showing the result of a query for
	template using the arguments specified in context.

	TODO: Refactor, use to figure out a smart way to do templating.
	"""
	queryResult = template.runQuery(context)
	numberMatched = len(queryResult)
	tarForm = _makeTarForm(template, context, queryResult)
	headerRow, sortButtons = _getHeaderRow(template, context)
	doc = ["<head><title>Result of your query</title>",
		_resultsJs,
		'<link rel="stylesheet" type="text/css"'
			' href="%s/querulator.css">'%config.get("web", "staticURL"),
		"</head><body><h1>Result of your query</h1>", _thumbTarget]
	doc.append('<div class="resultMeta">')
	if numberMatched:
		doc.append('<p>Selected items: %d</p>'%numberMatched)
		if _isTruncated(queryResult, context):
			doc.append("<p>It is likely that your result was truncated"
				" due to reaching the match limit.  You may want to re-run it"
				" using a higher limit.</p>")
	else:
		doc.append("<p>No data matched your query.</p></body>")
	doc.append('<ul class="queries">%s</ul>'%("\n".join([
		"<li>%s</li>"%qf for qf in template.getConditionsAsText(context)])))
	doc.append("</div>")
	if not numberMatched:
		return "\n".join(doc+["</body>\n"])
	doc.append(template.getLegal())

	if numberMatched>20:
		doc.append(tarForm)
	doc.append('<table border="1" class="results">')
	doc.append(sortButtons)
	hints = [itemdef["hint"] for itemdef in template.getItemdefs()]
	formatter = HtmlValueFormatter(template, context)
	for count, row in enumerate(queryResult):
		if not count%20:
			doc.append(headerRow)
		doc.append("<tr>%s</tr>"%("".join(["<td>%s</td>"%formatter.format(
				hint, item, row)
			for item, hint in zip(row, hints) if hint[0]!="suppressed"])))
	doc.append("</table>\n")
	doc.append('<p id="querylink"><a href="%s">Link to VOTable</a></p>'%
		"%s/run/%s?%s&outputFormat=VOTable%%2030"%(
			config.get("web", "rootURL"), template.getPath(), 
			context.getQueryArgs(suppress=["outputFormat"])))
	doc.append(tarForm)
	doc.append("</body>")
	return "\n".join(doc)


def _formatAsTarStream(template, context):
	"""returns a callable that writes a tar stream of all products matching
	template with arguments in form.

	This assumes that the query supports the "product interface", i.e.,
	has columns owner and embargo.
	"""
	def getProducts(template, context):
		"""returns a list of (productKey, targetName) tuples.
		"""
		queryResult = template.runQuery(context)
		ownerCol, embargoCol = template.getColIndexFor("owner"
			), template.getColIndexFor("embargo")
		productCol = template.getProductCol()
		productKeys = []
		nameGen = UniqueNameGenerator()
		for row in queryResult:
			if context.isAuthorizedProduct(row[embargoCol], row[ownerCol]):
				productKeys.append((row[productCol], 
					nameGen.makeName(os.path.basename(row[productCol]))))
			else:
				productKeys.append((None,
					nameGen.makeName(os.path.basename(row[productCol]))))
		return productKeys

	def resolveProductKeys(productKeys, context):
		"""resolves product keys to file names in the (productKey, targetName) list
		productKeys.
		"""
		foundKeys = [key for key, name in productKeys if key!=None]
		querier = context.getQuerier()
		keyResolver = dict(querier.query("SELECT key, accessPath FROM"
			" products WHERE key in %(keys)s", {"keys": foundKeys}).fetchall())
		return [(keyResolver[key], name) for key, name in productKeys if key!=None]

	def getEmbargoedFile(name):
		"""returns a tarInfo for an embargoed file.
		"""
		b = TarInfo(name)
		stuff = cStringIO.StringIO("This file is embargoed.  Sorry.")
		return b, stuff

	tarContent = resolveProductKeys(
		getProducts(template, context), context)

	if _isTruncated(tarContent, context):
		resultsName = "results_truncated.tar"
	else:
		resultsName = "results.tar"

	def produceOutput(outputFile):
		outputTar = tarfile.TarFile(resultsName, "w", outputFile)
		for srcPath, name in tarContent:
			if srcPath!=None:
				path = os.path.join(config.get("inputsDir"), srcPath)
				outputTar.add(path, name)
			else:
				outputTar.addfile(*getEmbargoedFile(name))
		outputTar.close()

	return produceOutput


def _parseOutputFormat(context):
	"""returns output format and verbosity from a context.

	The rules are: 

	* The default output format is a full VOTable (verbosity 30)
	* If there's a outputFormat parameter, we try to parse it into verbosity
	  and a format specifier.
	* If there's a VERB specifier, it overrides any verbosity established 
	  before to int(VERB)*10.

	outputFormat must look like <format>[ <number>], where format may be
	stuff like HTML, VOT, or tar (anything processQuery is prepared to handle).

	Verbosity is ignored for anything but VOTable.
	"""
	format, verbosity = "VOTable", 30
	if context.hasArgument("outputFormat"):
		mat = re.match("(\w+) (\d+)$", context.getfirst("outputFormat"))
		if mat:
			format, verbosity = mat.group(1), int(mat.group(2))
		else:
			format = context.getfirst("outputFormat")
	if context.hasArgument("VERB"):
		verbosity = int(context.getfirst("VERB"))*10
	return format, verbosity


def processQuery(template, context):
	"""returns a content type, the result of the query and a dictionary of
	additional headers for a cgi query.

	The return value is for direct plugin into querulator's "framework".
	"""
	outputFormat, verbosity = _parseOutputFormat(context)
	if outputFormat=="HTML":
		return "text/html", _formatAsHtml(template, context), {}
	elif outputFormat=="VOTable":
		return "application/x-votable", _formatAsVoTable(template, context,
			verbosity=verbosity), {
				"Content-disposition": 'attachment; filename="result.xml"'}
	elif outputFormat=="VOPlot":
		context.addArgument("VERB", verbosity/10)
		return "text/html", voplot.getVOPlotPage(template, context), {}
	elif outputFormat=="tar":
		return "application/tar", _formatAsTarStream(template, context), {
			"Content-disposition": 'attachment; filename="result.tar"'}
	else:
		raise querulator.Error("Invalid output format: %s"%outputFormat)


def getProduct(context):
	"""returns all data necessary to deliver one product to the user.
	"""
	prodKey = context.getfirst("path")
	querier = context.getQuerier()
	matches = querier.query("select owner, embargo, accessPath from products"
		" where key=%(key)s", {"key": prodKey}).fetchall()
	if not matches:
		raise querulator.Error("No product %s known -- you're not guessing,"
			" are you?"%prodKey)
	owner, embargo, accessPath = matches[0]
	if not context.isAuthorizedProduct(embargo, owner):
		raise querulator.Error("The product %s still is under embargo.  The "
			" embargo will be lifted on %s"%(prodKey, embargo))
	return "image/fits", open(os.path.join(
			config.get("inputsDir"), accessPath)).read(), {
		"Content-disposition": 'attachment; filename="%s"'%os.path.basename(
			context.getfirst("path")),}
