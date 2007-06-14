"""
This module contains code to query and format the database according to
querulator templates.
"""

import os
import sys
import cgi
import urllib
import urlparse
import cStringIO
import tarfile
from mx import DateTime

import gavo
from gavo import sqlsupport
from gavo import votable
from gavo.web import querulator


_resultsJs = """
<script type="text/javascript">
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
	"staticURL": querulator.staticURL,
}

_thumbTarget = """
<img src="%s/empty.png" id="thumbtarget" 
	style="position:fixed;top:0px;left:0px">
"""%(querulator.staticURL)

class Formatter:
	"""is a container for functions that format values from the
	database for the various output formats.

	The idea is that formatting has two phases -- one common to all
	output formats, called preprocessing (useful for completing URLs,
	unserializing stuff, etc), and one that does the real conversion.

	The converters are simply methods with defined names:

	_cook_xxx takes some value from the database and returns another
	value for format hint xxx.

	_xxx_to_fff brings a value with format hint xxx to format fff.

	If a method is not defined, the value is not touched.
	"""
	def __init__(self, template):
		self.template = template

	def _htmlEscape(self, value):
		return str(value).replace("&", "&amp;").replace("<", "&lt;")


	def _cook_date(self, value):
		"""(should check if value is a datetime instance...)
		"""
		return str(value).split()[0]

	def _cook_juliandate(self, value):
		"""(should check if value really is mx.DateTime)
		"""
		return value.jdn

	def _cook_product(self, path):
		"""returns pieces to format a product URL.
		
		Specifically, it qualifies path to a complete URL for the product and
		returns this together with a relative URL for a thumbnail and a
		sufficiently sensible title.
		"""
		return urlparse.urljoin(querulator.serverURL,
			"%s/getproduct/%s?path=%s"%(querulator.rootURL, 
			self.template.getPath(), urllib.quote(path))), \
			"%s/thumbnail/%s?path=%s"%(querulator.rootURL, 
			self.template.getPath(), urllib.quote(path)),\
			os.path.basename(path)

	def _cook_aladinload(self, path):
		"""wraps path into a URL that can be sent to aladin for loading the image.
		"""
		return urlparse.urljoin(querulator.serverURL,
			"%s/getproduct/%s?path=%s"%(querulator.rootURL, 
			self.template.getPath(), urllib.quote(path)))

	def _product_to_html(self, args):
		prodUrl, thumbUrl, title = args
		return ('<a href="%s">%s</a><br>'
			'<a href="%s"  target="thumbs"'
			' onMouseover="showThumbnail(\''
			'%s\')" onMouseout="clearThumbnail()">'
			'[preview]</a>')%(
			prodUrl,
			title,
			thumbUrl, thumbUrl)

	def _product_to_votable(self, args):
		return args[0]
			
	def _url_to_html(self, url):
		return '<a href="%s">[%s]</a>'%(self._htmlEscape(url), 
			self._htmlEscape(urlparse.urlparse(value)[1]))

	def _aladinquery_to_html(self, value):
		aladinPrefix = ("http://aladin.u-strasbg.fr/java/nph-aladin.pl"
			"?frame=launching&script=get%20aladin%28%29%20")
		return '<a href="%s%s" target="aladin">[Aladin]</a>'%(
			aladinPrefix, urllib.quote(value))

	def _aladinquery_to_votable(self, value):
		return ""

	def _aladinload_to_html(self, value):
		aladinPrefix = ("http://aladin.u-strasbg.fr/java/nph-aladin.pl"
			"?frame=launching&script=load%20")
		return '<a href="%s%s" target="aladin">[Aladin]</a>'%(
			aladinPrefix, urllib.quote(value))

	def _string_to_html(self, value):
		return self._htmlEscape(value)

	def format(self, hint, targetFormat, value):
		cooker = getattr(self, "_cook_%s"%hint, lambda a: a)
		formatter = getattr(self, "_%s_to_%s"%(hint, targetFormat),
			lambda a:a)
		return formatter(cooker(value))


def _formatAsVoTable(template, form, queryResult, stream=False):
	"""returns a callable that writes queryResult as VOTable.
	"""
	colDesc = []
	metaTable = sqlsupport.MetaTableHandler()
	defaultTableName = template.getDefaultTable()
	for itemdef in template.getItemdefs():
		try:
			colDesc.append(metaTable.getFieldInfo(
				itemdef["name"], defaultTableName))
		except sqlsupport.FieldError:
			colDesc.append({"fieldName": "ignore", "type": "text"})
	formatter = Formatter(template)
	hints = [itemdef["hint"] for itemdef in template.getItemdefs()]
	rows = []
	for row in queryResult.fetchall():
		rows.append([formatter.format(
				hint, "votable", item)
			for item, hint in zip(row, hints)])

	if stream:
		def produceOutput(outputFile):
			votable.writeSimpleTable(colDesc, rows, {}, 
				outputFile)
			queryResult.close()
		return produceOutput
	
	else:
		f = cStringIO.StringIO()
		votable.writeSimpleTable(colDesc, rows, {}, f)
		queryResult.close()
		return f.getvalue()


def _getHeaderRow(template):
	"""returns a header row for HTML table output.
	"""
	res = ['<tr>']
	itemdefs = template.getItemdefs()
	metaTable = sqlsupport.MetaTableHandler()
	defaultTableName = template.getDefaultTable()
	for itemdef in itemdefs:
		additionalTag, additionalContent = "", ""
		if itemdef["title"]:
			title = itemdef["title"]
		else:
			fieldInfo = metaTable.getFieldInfo(itemdef["name"], defaultTableName)
			title = fieldInfo["tablehead"]
			if fieldInfo["description"]:
				additionalTag += " title=%s"%repr(fieldInfo["description"])
			if fieldInfo["unit"]:
				additionalContent += "<br>[%s]</br>"%fieldInfo["unit"]
		res.append("<th%s>%s%s</th>"%(additionalTag, title, additionalContent))
	res.append("</tr>")
	return res


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


def _formatAsHtml(template, form, queryResult):
	"""returns an HTML formatted table showing queryResult.

	TODO: Refactor, use to figure out a smart way to do templating.
	"""
	def makeTarForm(template):
		doc = []
		if template.getProductCols():
			doc.append('<form action="%s/run/%s" method="post" class="tarForm">\n'%(
				querulator.rootURL, template.getPath()))
			doc.append(template.getHiddenForm(form))
			try:
				sizeEstimate = ' (approx. %s)'%_formatSize(
					template.getProductSizes(form))
			except sqlsupport.OperationalError:
				sizeEstimate = ""
			doc.append('<input type="submit" name="tar" value="Get tar of '
				' matched products%s">\n'%sizeEstimate)
			doc.append('</form>')
		return "\n".join(doc)

	tarForm = makeTarForm(template)
	headerRow = _getHeaderRow(template)
	doc = ["<head><title>Result of your query</title>",
		_resultsJs,
		'<link rel="stylesheet" type="text/css"'
			'href="%s/querulator.css">'%querulator.staticURL,
		"</head><body><h1>Result of your query</h1>", _thumbTarget]
	rows = queryResult.fetchall()   # without this, rowcount is not valid.
		#  XXX figure out a "leaner" way to do this
	numberMatched = queryResult.rowcount
	doc.append('<div class="resultMeta">')
	if numberMatched:
		doc.append('<p>Selected items: %d</p>'%numberMatched)
	else:
		doc.append("<p>No data matched your query.</p></body>")
	doc.append('<ul class="queries">%s</ul>'%("\n".join([
		"<li>%s</li>"%qf for qf in template.getConditionsAsText(form)])))
	doc.append("</div>")
	if not numberMatched:
		return "\n".join(doc+["</body>\n"])
	doc.append(template.getLegal())

	if numberMatched>20:
		doc.append(tarForm)
	doc.append('<table border="1" class="results">')
	hints = [itemdef["hint"] for itemdef in template.getItemdefs()]
	formatter = Formatter(template)
	for count, row in enumerate(rows):
		if not count%20:
			doc.extend(headerRow)
		doc.append("<tr>%s</tr>"%("".join(["<td>%s</td>"%formatter.format(
				hint, "html", item)
			for item, hint in zip(row, hints)])))
	doc.append("</table>\n")
	doc.append(tarForm)
	doc.append("</body>")
	return "\n".join(doc)


def _formatAsTar(template, queryResult):
	"""probably obsolete.  Use _formatAsTarStream.  If you think you need it,
	refactor stuff so that both functions use the same code base.
	"""
	productCols = template.getProductCols()
	outputFile = cStringIO.StringIO()
	outputTar = tarfile.TarFile("results.tar", "w", outputFile)
	productRoot = os.path.join(gavo.rootDir, template.getMeta("PRODUCT_ROOT"))
	for row in queryResult.fetchall():
		for colInd in productCols:
			path = querulator.resolvePath(productRoot, row[colInd])
			outputTar.add(path, os.path.basename(path))
	outputTar.close()
	return outputFile.getvalue()


def _formatAsTarStream(template, queryResult):
	"""returns a callable that writes a tar stream of all products.
	"""
	productCols = template.getProductCols()
	productRoot = os.path.join(gavo.rootDir, template.getMeta("PRODUCT_ROOT"))
	resultRows = queryResult.fetchall()
	
	def produceOutput(outputFile):
		outputTar = tarfile.TarFile("results.tar", "w", outputFile)
		for rowInd, row in enumerate(resultRows):
			for colInd in productCols:
				path = querulator.resolvePath(productRoot, row[colInd])
				outputTar.add(path, "%d%04d_%s"%(colInd, 
					rowInd, os.path.basename(path)))
		outputTar.close()

	return produceOutput


def processQuery(template):
	"""returns a content type, the result of the query and a dictionary of
	additional headers for a cgi query.

	The return value is for direct plugin into queryExpander's "framework".
	"""
	form = cgi.FieldStorage()
	sqlQuery = template.asSql(set(form.keys()))
	if sqlQuery.strip().endswith("WHERE"):
		raise querulator.Error("No valid query parameter found.")

	vals = template.getQueryArguments(form)
	querier = sqlsupport.SimpleQuerier()
	result = querier.query(sqlQuery, vals)

	if form.has_key("submit"):
		return "text/html", _formatAsHtml(template, form, result), {}
	elif form.has_key("votable"):
		return "application/x-votable", _formatAsVoTable(template, form, result
			), {"Content-disposition": 'attachment; filename="result.xml"'}
	elif form.has_key("tar"):
		return "application/tar", _formatAsTarStream(template, result), {
			"Content-disposition": 'attachment; filename="result.tar"'}


def getProduct(context):
	"""returns all data necessary to deliver one product to the user.
	"""
	form = cgi.FieldStorage()
	prodKey = form.getfirst("path")
	querier = sqlsupport.SimpleQuerier()
	matches = querier.query("select owner, embargo, accessPath from products"
		" where key=%(key)s", {"key": prodKey}).fetchall()
	if not matches:
		raise querulator.Error("No product %s known -- you're not guessing,"
			" are you?"%prodKey)
	owner, embargo, accessPath = matches[0]
	if embargo>DateTime.today() and owner!=context.loggedUser:
		raise querulator.Error("The product %s still is under embargo.  The "
			" embargo will be lifted on %s"%(prodKey, embargo))
	return "image/fits", open(os.path.join(
			gavo.inputsDir, accessPath)).read(), {
		"Content-disposition": 'attachment; filename="%s"'%os.path.basename(
			form.getfirst("path")),}

