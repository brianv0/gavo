import gavo
from gavo import config
from gavo.web import common
import re
import os

class Error(Exception):
	pass

import sys

def resolveTemplate(relpath):
	return common.resolvePath(config.get("querulator", "templateRoot"), relpath)


queryElementPat = re.compile(r"(?s)<\?(\w*)query (.*?)\?>")
metaElementPat = re.compile(r"(?s)<\?meta(.*?)\?>")
macroPat = re.compile(r"(?s)<\?macro(.*?)\?>")
