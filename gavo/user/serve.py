"""
A wrapper script suitable for starting the server.
"""

import datetime
import os
import pkg_resources
import sys

from nevow import appserver
from nevow import inevow
from nevow import rend
from twisted.internet import reactor
from twisted.python import log

from gavo import base
from gavo import utils
from gavo.web import root
from gavo.base import config


TWISTD_BIN="/usr/bin/twistd"


def parseCmdLine():
	import optparse
	knownActions = ("start", "stop", "restart", "debug")
	parser = optparse.OptionParser(usage="%%prog %s"%("|".join(knownActions)))
	opts, args = parser.parse_args()
	if len(args)!=1 or args[0] not in knownActions:
		parser.print_help()
		sys.exit(1)
	return opts, args


def serverAction(act):
# XXX TODO: Fix this
	'''
	PATH=/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin
	LOGFILE=/data/gavo/logs/web.log
	PIDFILE=/data/gavo/state/twistd.pid
	APP=/home/msdemlei/checkout/gavo/standalone.tac

	TWISTD_OPTS="--no_save --logfile $LOGFILE --pidfile $PIDFILE --rundir /tmp"

	test -f /lib/lsb/init-functions || exit 1
	. /lib/lsb/init-functions

	case "${1}" in
	("start")
			log_begin_msg "Starting VO Server"
			echo "$TWISTD_BIN $TWISTD_OPTS $APP"
			$TWISTD_BIN $TWISTD_OPTS --python $APP
			log_end_msg $?
			exit $?
			;;
	("stop")
			log_begin_msg "Stopping VO Server..."
			kill -INT `cat $PIDFILE`
			log_end_msg $?
			exit $?
			;;
	("restart" | "force-reload")
			"${0}" stop &&
			"${0}" start
			exit $?
			;;
	(*)
			log_success_msg "Usage: $0 {start|stop|restart|force-reload}" >&2
			exit 3
			;;
	esac
	'''


class ExitPage(rend.Page):
	def renderHTTP(self, ctx):
		req = inevow.IRequest(ctx)
		req.setHeader("content-type", "text/plain")
		reactor.stop()
		return "exiting."


def debugAction():
	log.startLogging(sys.stderr)
	config.setMeta("upSince", datetime.datetime.utcnow().strftime(
		utils.isoTimestampFmt))
	root.root.child_exit = ExitPage()
	reactor.listenTCP(int(base.getConfig("web", "serverPort")), root.site)
	reactor.run()


def main():
	opts, args = parseCmdLine()
	if args[0]=="debug":
		debugAction()
	else:
		serverAction(args[0])


if __name__=="__main__":
	main()
