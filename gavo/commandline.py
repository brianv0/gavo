#!/usr/bin/env python

"""
This script is the interface to importing resources into the VO.
"""

import sys
import os
import textwrap
import traceback
from optparse import OptionParser

from gavo import base
from gavo import grammars
from gavo import rscdesc     # for registration
from gavo import rsc
from gavo.protocols import basic  # for registration
from gavo import web         # for registration


class Abort(Exception):
	pass


def process(opts, args):
	src, ddIds = args[0], set(args[1:])
	try:
		rd = base.caches.getRD(os.path.join(os.getcwd(), src))
	except base.RDNotFound:
		rd = base.caches.getRD(src, forImport=True)
	connection = base.getDBConnection("admin")
	rd.runScripts("preCreation")
	for dd in rd.dds:
		if ddIds and not dd.id in ddIds:
			continue
		print ">>>>>>>>>>> Now processing", dd.id
		if opts.metaOnly:
			res = rsc.Data.create(dd, parseOptions=opts).updateMeta()
		else:
			res = rsc.makeData(dd, parseOptions=opts, connection=connection)
		print "Columns affected:", res.nAffected


def parseCmdline():
	def enablePdb(opt, s, val, parser):
		import pdb
		def enterPdb(type, value, tb):
			traceback.print_exception(type, value, tb)
			pdb.pm()
		sys.excepthook = enterPdb
		parser.values.reraise = True

	parser = OptionParser(usage="%prog [options] <rd-name> {<data-id>}")
	parser.add_option("-z", "--start-pdb", help="run pdb  when an exception"
		" is not caught", callback=enablePdb, action="callback")
	parser.add_option("-n", "--updateRows", help="Use UPDATE on primary"
		" key rather than INSERT with rows inserted to DBTables.",
		action="store_true", dest="doTableUpdates", default=False)
	parser.add_option("-d", "--dumpRows", help="Dump raw rows as they are"
		" emitted by the grammar.", dest="dumpRows", action="store_true",
		default=False)
	parser.add_option("-m", "--meta-only", help="just update table meta"
		" (privileges, column descriptions,...).", dest="metaOnly", 
		action="store_true")
	parser.add_option("-u", "--update", help="update mode -- don't drop"
		" tables before writing.", dest="updateMode", 
		action="store_true", default=False)
	parser.add_option("-p", "--profile", help="use PROFILE to access db",
		dest="dbProfile", action="store", type="str", 
		default="admin", metavar="PROFILE")
	parser.add_option("-s", "--system", help="create shared tables",
		dest="systemImport", action="store_true")
	parser.add_option("-v", "--verbose", help="talk a lot while working",
		dest="verbose", action="store_true")
	parser.add_option("-r", "--reckless", help="Do not validate rows"
		" before ingestion", dest="validateRows", action="store_false",
		default=True)
	parser.add_option("-b", "--batch-size", help="deliver N rows at a time"
		" to the database.", dest="batchSize", action="store", type="int",
		default=1024, metavar="N")
	parser.add_option("-c", "--continue-bad", help="go on after a source had"
		" an error", dest="ignoreBadSources", action="store_true")
	(opts, args) = parser.parse_args()
	base.setDBProfile(opts.dbProfile)
	if not args:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
	opts, args = parseCmdline()
	try:
		process(opts, args)
	except Abort, msg:
		sys.exit(1)
	except SystemExit, msg:
		sys.exit(msg.code)
	except grammars.ParseError, msg:
		errTx = unicode(msg)
		if msg.location:
			errTx = "Parse error at %s: %s"%(msg.location, errTx)
		else:
			errTx = "Parse error: %s"%errTx
		sys.stderr.write(textwrap.fill(errTx, break_long_words=False)+"\n\n")
		if msg.record:
			sys.stderr.write("Offending input was:\n")
			sys.stderr.write(repr(msg.record)+"\n")
		sys.exit(1)
	except (base.ValidationError, base.ReportableError), msg:
		errTx = unicode(msg).encode(base.getConfig("ui", "outputEncoding"))
		sys.stderr.write(textwrap.fill(errTx, break_long_words=False)+"\n\n")
		sys.exit(1)
	except Exception, msg:
		sys.stderr.write("Oops.  Unhandled exception.  Here's the traceback:\n")
		if getattr(opts, "reraise", False):
			raise
		else:
			traceback.print_exc()
			sys.exit(1)
