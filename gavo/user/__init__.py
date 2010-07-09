"""
"User-interface"-type code.
"""

from gavo.user import useless
from gavo.user import plainui
from gavo.user import problemlog

interfaces = {
	"deluge": useless.DelugeUI,
	"null": useless.NullUI,
	"stingy": plainui.StingyPlainUI,
	"plain": plainui.PlainUI,
	"problemlog": problemlog.FailedRowCollector,
}
