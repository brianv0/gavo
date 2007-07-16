"""
The main entry points to the masquerator.
"""

import os

import gavo
# shut up messages from the parsing infrastructure.
from gavo import nullui

from gavo.web.querulator import queryrun
import forms


def getMasqForm(context, subPath):
	tpl = forms.ServiceCollection(subPath, context)
	return "text/html", tpl.asHtml(context), {}


def processMasqQuery(context, subPath):
	subPath = subPath.rstrip("/")
	tpl = forms.ServiceTemplate(
		forms.ServiceCollection(os.path.dirname(subPath), context),
		os.path.basename(subPath),
		context.getfirst("outputName", "output"))
	return queryrun.processQuery(tpl, context)


if __name__=="__main__":
#	service = Service(parseService("/auto/gavo/inputs/apfs/res/apfs_dyn", 
#		"single"))
	from gavo.web.querulator import context
	ctx = context.DebugContext(args={"alpha": 219.90206583333332,
		"delta": -60.833974722222223,	"mu_alpha": -3678.08, 
		"mu_delta": 482.87, "parallax": 0.742, "rv": -21.6,
		"year": 2008, "month": 10, "day": 5, "hour": 3})
	tpl = ServiceTemplate("apfs.cq", ctx)
	print tpl.asHtml(ctx)
