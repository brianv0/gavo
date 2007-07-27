"""
A little utility to speed up processing of fits collections.

It analyzes the primary header of a fits file and outputs a skeleton
resource descriptor for it.

This is *very* quick and dirty.  Let's see if something like this really
helps and then think again.
"""

import sys

from gavo import fitstools
from gavo import datadef
from gavo.parsing import resource

ignoredHeaders = set(["COMMENT", "SIMPLE", "CRPIX1", "CRVAL1",
	"CDELT1", "CTYPE1"])

rdTemplate="""
<?xml version="1.0" encoding="utf-8"?>

<!DOCTYPE GavoResourceDescriptor [
	<!ENTITY master-name "$resname$">
]>


<ResourceDescriptor srcdir="&master-name;/$sourcessubdir$">
	<schema>&master-name;</schema>

	<Data sourcePat="$srcpat$" id="$anything$">
		<FitsGrammar qnd="True">
		</FitsGrammar>

		<Semantics>
			%s
		</Semantics>
	</Data>
</ResourceDescriptor>
"""


def makeItemXML(itemDef):
	return ('<Field dest="%s" source="%s" unit="%s" ucd="%s" description="%s"'
		' dbtype="text"/>')%(
		itemDef.get_dest(), itemDef.get_source(), itemDef.get_unit(),
		itemDef.get_ucd(), itemDef.get_description())


def makeRecXML(recordDef):
	lines = ['<Record table="%s">'%recordDef.get_table()]
	for item in recordDef.get_items():
		lines.append("\t"+makeItemXML(item))
	lines.append('</Record>')
	return "\n\t\t\t".join(lines)


def makeRdXML(recordDef):
	"""returns the XML for a FitsGrammar resource descriptor for recordDef.

	This should probably go into XML/DOM generating methods within the
	classes themselves (or even record.Record itself).  For now, we want it
	quick.
	"""
	return rdTemplate%makeRecXML(recordDef)


def makeRecord(cardList):
	record = resource.RecordDef()
	record.set_table("$tablename$")
	for index, card in enumerate(cardList):
		if card.key in ignoredHeaders:
			continue
		record.addto_items(datadef.DataField(dest="$fieldname%02d$"%index, 
			source=card.key, unit="$fillin$", ucd="$fillin$", 
			description=card.comment))
	return record


def getHeaderKeys(srcName):
	header = fitstools.openFits(srcName)[0].header
	return header.ascardlist()


def getUsage():
	return "Usage: %s <fitsfile>\n"%sys.argv[0]


def main():
	if len(sys.argv)!=2:
		sys.exit(getUsage())
	recordDef = makeRecord(
		getHeaderKeys(sys.argv[1]))
	print makeRdXML(recordDef)

if __name__=="__main__":
	main()
