"""
Creation of resource descriptors

When we get structured data, we can suggest resource descriptors.

Here, we try this for data described through primary FITS headers and 
VOTables.
"""

# We probably want to turn this around and first create the RD and pass
# that around so the individual analyzers can add, e.g. global metadata.

import os
import re
import sys

from gavo import config
from gavo import datadef
from gavo import fitstools
from gavo import stanxml
from gavo import typesystems
from gavo import utils
from gavo.imp import VOTable
from gavo.parsing import resource

ignoredFITSHeaders = set(["COMMENT", "SIMPLE", "CRPIX1", "CRVAL1",
	"CDELT1", "CTYPE1"])


class RD(object):
	"""is a container for resource descriptor stanxml elements.
	"""
	class RDElement(stanxml.Element):
		mayBeEmpty = True  # here, we want empty elements for the user to fill out.
		local = True
	
	class ResourceDescriptor(RDElement):
		a_srcdir = None
	
	class schema(RDElement): pass

	class Data(RDElement):
		a_sourcePat = None
		a_source = None
	
	class FitsGrammar(RDElement):
		a_qnd = None

	class VOTableGrammar(RDElement): pass

	class Semantics(RDElement): pass
	
	class Record(RDElement): 
		a_table = None
	
	class Field(RDElement):
		a_dest = None
		a_source = None
		a_dbtype = None
		a_description = None
		a_unit = None
		a_ucd = None


def makeField(itemDef):
	return RD.Field(**{"dest": itemDef.get_dest(),
		"source": itemDef.get_source(), "unit": itemDef.get_unit(),
		"ucd": itemDef.get_ucd(), "description": itemDef.get_description(),
		"dbtype": itemDef.get_dbtype()})

def makeRecord(tableDef):
	return RD.Record(table=tableDef.get_table())[[
		makeField(f) for f in tableDef.get_items()]]

def makeRdXML(tableDef, grammar, args, opts):
	if opts.srcForm=="FITS":
		dataEl = RD.Data(id="main", sourcePat="*.fits")
	else:
		dataEl = RD.Data(id="main", source=args[0])
	return RD.ResourceDescriptor(srcdir=utils.getRelativePath(
			os.path.abspath("."), config.get("inputsDir")))[
		RD.schema[os.path.basename(os.getcwd())],
		dataEl[
			grammar,
			RD.Semantics[
				makeRecord(tableDef)]]]


def makeFromFITS(srcName, opts):

	def getHeaderKeys(srcName):
		header = fitstools.openFits(srcName)[0].header
		return header.ascardlist()

	record = resource.TableDef()
	record.set_table("data")
	for index, card in enumerate(getHeaderKeys(srcName)):
		if card.key in ignoredFITSHeaders:
			continue
		record.addto_items(datadef.DataField(dest=card.key.lower(),
			source=card.key, unit="$fillin$", ucd="$fillin$", dbtype="$fillin$",
			description=card.comment))
	return record, RD.FitsGrammar(qnd="True")


def makeVOTableFieldName(field, ind):
	return re.sub("[^\w]+", "x", (field.name or field.id or "field%02d"%ind))

def makeFromVOTable(srcName, opts):
	vot = VOTable.parse(open(srcName))
	srcTable = vot.resources[0].tables[0]
	record = resource.TableDef()
	record.set_table("data")
	for ind, f in enumerate(srcTable.fields):
		colName = makeVOTableFieldName(f, ind)
		record.addto_items(datadef.DataField(dest=colName, source=colName,
			ucd=f.ucd, description=f.description, tablehead=colName,
			dbtype=typesystems.voTableToSQLType(f.datatype, f.arraysize)))
	return record, RD.VOTableGrammar


formatters = {
	"FITS": makeFromFITS,
	"VOT": makeFromVOTable,
}


def parseCommandLine():
	from optparse import OptionParser
	parser = OptionParser(usage = "%prog [options] <sample>")
	parser.add_option("-f", "--format", help="FITS or VOT, source format."
		"  Default: Detect from file name", dest="srcForm", default=None,
		action="store", type="str")
	opts, args = parser.parse_args()
	if len(args)!=1:
		parser.print_help()
		sys.exit(1)
	if not opts.srcForm:
		ext = os.path.splitext(args[0])[1].lower()
		if ext in set([".xml", ".vot"]):
			opts.srcForm = "VOT"
		elif ext==".fits":
			opts.srcForm = "FITS"
		else:
			sys.stderr.write("Cannot guess format: %s"%args[0])
			parser.print_help()
			sys.exit(1)
	return opts, args


def main():
	opts, args = parseCommandLine()
	rec, grammar = formatters[opts.srcForm](args[0], opts)
	os.popen("xmlstarlet fo", "w").write(
		makeRdXML(rec, grammar, args, opts).render())


if __name__=="__main__":
	main()
