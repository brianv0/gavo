"""
CLI function to show various things.

Maybe gavo config and gavo info should be folded in here if this grows.
"""

from gavo import base
from gavo import rscdesc  # (register getRD)
from gavo.user import common
from gavo.user.common import Arg, exposedFunction, makeParser


@exposedFunction([
	Arg("rdId", help="an RD id (or a path to RD xml)"),
	Arg("ddIds", help="optional dd ids to select (as for imp or drop)",
		nargs='*')],
	help="show what data items are avalailable")
def dds(args):
	rd = rscdesc.openRD(args.rdId)
	for dd in common.getPertainingDDs(rd, args.ddIds):
		outLine = dd.id
		if dd.auto:
			outLine += "*"
		print outLine

def main():
	args = makeParser(globals()).parse_args()
	args.subAction(args)
