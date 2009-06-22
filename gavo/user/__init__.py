"""
"User-interface"-type code.
"""

from gavo.user import useless
from gavo.user import plainui
from gavo.user import problemlog

interfaces = {
	"deluge": useless.DelugeUI,
	"null": useless.NullUI,
	"plain": plainui.PlainUI,
	"problemlog": problemlog.FailedRowCollector,
}
