"""
A renderer that makes jpegs out of database lines.

It expects pairs of line number and base64-encoded 8-bit single-channel
image data in its input.
"""

import cStringIO
import traceback

import Image

from nevow import appserver
from nevow import inevow
from nevow import static

from twisted.internet import threads
from twisted.internet import defer
from twisted.python import failure

from zope.interface import implements

import gavo
from gavo import datadef
from gavo import votable
from gavo.parsing import contextgrammar
from gavo.parsing import resource
from gavo.web import common
from gavo.web import resourcebased


class JpegRenderer(resourcebased.Form):
	name="img.jpeg"

	def __init__(self, *args):
		super(JpegRenderer, self).__init__(*args)

	def _runService(self, inputData, queryMeta, ctx):
		pars = inputData.getDocRec()
		if "plotField" in pars:
			queryMeta.setdefault("additionalFields", []).append(
						pars["plotField"])
		return self.service.run(inputData, queryMeta
			).addCallback(self._handleOutputData, ctx
			).addErrback(self._handleError, ctx)

	def _computeLinesWithCurve(self, rawRecs, plotField):
		curveMin = float(self.service.get_property("curveMin", 0))
		valRange = float(self.service.get_property("curveMax"))-curveMin
		curveWidth = int(self.service.get_property("curveWidth", "200"))
		def scale(v):
			return max(0, min(curveWidth, int((v-curveMin)/valRange*curveWidth)))
		curvePix = '\xff'*curveWidth
		lastPos = dotPos = scale(rawRecs[0][plotField])
		for rec in rawRecs:
			dotPos = scale(rec[plotField])
			if lastPos<dotPos:
				curveBytes = curvePix[:lastPos]+'\0'*(dotPos-lastPos
					)+curvePix[dotPos:]
			elif lastPos==dotPos:
				curveBytes = curvePix[:dotPos-1]+'\0'+curvePix[dotPos:]
			else:
				curveBytes = curvePix[:dotPos]+'\0'*(lastPos-dotPos
					)+curvePix[lastPos:]
			lastPos = dotPos
			yield rec["data"].decode("base64")+curveBytes

	def _createImage(self, data):
		if self.service.get_property("curveMax"
				) and "plotField" in data.queryPars and data.queryPars["plotField"]:
			lines = [l for l in self._computeLinesWithCurve(data.getPrimaryTable(),
				data.queryPars["plotField"])]
		else:
			lines = [rec["data"].decode("base64") for rec in data.getPrimaryTable()]
		img = Image.fromstring("L", (len(lines[0]), len(lines)),
			"".join(pixLine for pixLine in lines))
		if data.data_inputRec().get("palette"):
			img.putpalette(palettes[data.data_inputRec()["palette"]])
			img = img.convert("RGB")
			img = img.tostring("jpeg", "RGB")
		else:
			img = img.tostring("jpeg", "L")
		return img

	def _handleOutputData(self, data, ctx):
		return threads.deferToThread(self._createImage, data
			).addCallback(self._deliverJpeg, ctx
			).addErrback(self._handleError, ctx)

	def _deliverJpeg(self, jpegStr, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "image/jpeg")
		request.setHeader("content-length", str(len(jpegStr)))
		if request.method=='HEAD':
			return ''
		static.FileTransfer(cStringIO.StringIO(jpegStr), len(jpegStr), request)
		return request.deferred

	def _handleError(self, failure, ctx):
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/plain")
		request.write("Image generation failed")
		request.finishRequest(False)
		return appserver.errorMarker

import traceback

class MachineJpegRenderer(common.CustomErrorMixin, JpegRenderer):
	"""is a machine version of the JpegRenderer -- no vizier expressions,
	hardcoded parameters, plain text errors.
	"""
	name = "mimg.jpeg"

	def __init__(self, ctx, *args, **kwargs):
		ctx.remember(self, inevow.ICanHandleException)
		super(MachineJpegRenderer, self).__init__(ctx, *args, **kwargs)

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		formalData = {}
		try:
			formalData["line"] = "%d .. %d"%(
				int(args["startLine"][0]), int(args["endLine"][0]))
			formalData["palette"] = str(args.get("palette", [""])[0])
			formalData["plotField"] = str(args.get("plotField", [""])[0])
		except:
			traceback.print_exc()
			raise gavo.ValidationError("Invalid input parameters %s"%args, "line")
		return self.submitAction(ctx, None, formalData)

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		msg = "Image generation failed: %s"%failure.getErrorMessage()
		request = inevow.IRequest(ctx)
		request.setResponseCode(400)
		request.setHeader("content-type", "text/plain")
		request.write(msg)
		request.finishRequest(False)
		return appserver.errorMarker

	def _handleInputErrors(self, errors, ctx):
		if not isinstance(errors, list):
			errors = [errors]
		msg = "Error(s) in given Parameters: %s"%"; ".join(
			[e.getErrorMessage() for e in errors])
		request = inevow.IRequest(ctx)
		request.setResponseCode(400)
		request.setHeader("content-type", "text/plain")
		request.setHeader("content-type", "text/plain")
		request.write(msg)
		request.finishRequest(False)
		return appserver.errorMarker



palettes = {
	"gold": '\xfc\xfc\x80\xfc\xfc\x80\xfc\xf8|\xfc\xf8|\xfc\xf4x\xf8\xf4x\xf8\xf0t\xf8\xf0p\xf8\xecp\xf4\xecl\xf4\xe8l\xf4\xe8h\xf4\xe4h\xf0\xe4d\xf0\xe0`\xf0\xe0`\xf0\xdc\\\xec\xdc\\\xec\xd8X\xec\xd8T\xec\xd4T\xec\xd4P\xe8\xd0P\xe8\xd0L\xe8\xccL\xe8\xccH\xe4\xc8D\xe4\xc8D\xe4\xc4@\xe4\xc4@\xe0\xc0<\xe0\xc08\xe0\xbc8\xe0\xbc4\xdc\xb84\xdc\xb80\xdc\xb40\xdc\xb4,\xdc\xb0(\xd8\xb0(\xd8\xac$\xd8\xac$\xd8\xa8 \xd4\xa8\x1c\xd4\xa4\x1c\xd4\xa4\x18\xd4\xa0\x18\xd0\xa0\x14\xd0\x9c\x14\xd0\x9c\x10\xd0\x98\x0c\xcc\x98\x0c\xcc\x94\x08\xcc\x94\x08\xcc\x90\x04\xc8\x8c\x00\xc4\x88\x00\xc4\x88\x00\xc4\x88\x00\xc4\x88\x00\xc0\x84\x00\xc0\x84\x00\xc0\x84\x00\xc0\x84\x00\xbc\x80\x00\xbc\x80\x00\xbc\x80\x00\xbc\x80\x00\xb8|\x00\xb8|\x00\xb8|\x00\xb8|\x00\xb4x\x00\xb4x\x00\xb4x\x00\xb4x\x00\xb0t\x00\xb0t\x00\xb0t\x00\xb0t\x00\xacp\x00\xacp\x00\xacp\x00\xacp\x00\xa8l\x00\xa8l\x00\xa8l\x00\xa8l\x00\xa4h\x00\xa4h\x00\xa4h\x00\xa4h\x00\xa0d\x00\xa0d\x00\xa0d\x00\xa0d\x00\x9c`\x00\x9c`\x00\x9c`\x00\x9c`\x00\x98\\\x00\x98\\\x00\x98\\\x00\x98\\\x00\x94X\x00\x94X\x00\x94X\x00\x94X\x00\x90T\x00\x90T\x00\x90T\x00\x90T\x00\x8cP\x00\x8cP\x00\x8cP\x00\x8cP\x00\x88L\x00\x88L\x00\x88L\x00\x88L\x00\x84H\x00\x84H\x00\x84H\x00\x84H\x00\x80D\x00\x80D\x00\x80D\x00\x80D\x00|@\x00|@\x00|@\x00|@\x00x<\x00x<\x00x<\x00x<\x00t8\x00t8\x00t8\x00t8\x00p4\x00p4\x00p4\x00p4\x00l0\x00l0\x00l0\x00l0\x00h,\x00h,\x00h,\x00h,\x00d(\x00d(\x00d(\x00d(\x00`$\x00`$\x00`$\x00`$\x00\\ \x00\\ \x00\\ \x00\\ \x00X\x1c\x00X\x1c\x00X\x1c\x00X\x1c\x00T\x18\x00T\x18\x00T\x18\x00T\x18\x00P\x14\x00P\x14\x00P\x14\x00P\x14\x00L\x10\x00L\x10\x00L\x10\x00L\x10\x00H\x0c\x00H\x0c\x00H\x0c\x00H\x0c\x00D\x08\x00D\x08\x00D\x08\x00D\x08\x00@\x04\x00@\x04\x00@\x04\x00@\x04\x00<\x00\x00<\x00\x00<\x00\x00<\x00\x008\x00\x008\x00\x008\x00\x008\x00\x004\x00\x004\x00\x004\x00\x004\x00\x000\x00\x000\x00\x000\x00\x000\x00\x00,\x00\x00,\x00\x00,\x00\x00,\x00\x00(\x00\x00(\x00\x00(\x00\x00(\x00\x00$\x00\x00$\x00\x00$\x00\x00$\x00\x00 \x00\x00 \x00\x00 \x00\x00 \x00\x00\x1c\x00\x00\x1c\x00\x00\x1c\x00\x00\x1c\x00\x00\x18\x00\x00\x18\x00\x00\x18\x00\x00\x18\x00\x00\x14\x00\x00\x14\x00\x00\x14\x00\x00\x14\x00\x00\x10\x00\x00\x10\x00\x00\x10\x00\x00\x10\x00\x00\x0c\x00\x00\x0c\x00\x00\x0c\x00\x00\x0c\x00\x00\x08\x00\x00\x08\x00\x00\x08\x00\x00\x08\x00\x00\x04\x00\x00\x04\x00\x00\x04\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
	"coldfire": '\x00\xac\xfc\x00\xac\xfc\x00\xac\xfc\x00\xa8\xfc\x00\xa4\xfc\x00\xa0\xfc\x00\x9c\xfc\x00\x98\xfc\x00\x98\xfc\x00\x94\xfc\x00\x90\xfc\x00\x8c\xfc\x00\x88\xfc\x00\x84\xfc\x00\x84\xfc\x00\x80\xfc\x00|\xfc\x00x\xfc\x00t\xfc\x00p\xfc\x00p\xfc\x00l\xfc\x00h\xfc\x00d\xfc\x00`\xfc\x00\\\xfc\x00\\\xfc\x00X\xfc\x00T\xfc\x00P\xfc\x00L\xfc\x00H\xfc\x00D\xfc\x00@\xfc\x00<\xfc\x008\xfc\x004\xfc\x000\xfc\x00,\xfc\x00(\xfc\x00$\xfc\x00 \xfc\x00\x1c\xfc\x00\x18\xfc\x00\x14\xfc\x00\x10\xfc\x00\x0c\xfc\x00\x08\xfc\x00\x04\xfc\x00\x04\xfc\x04\x04\xf8\x04\x04\xf8\x08\x04\xf4\x08\x08\xf0\x0c\x08\xf0\x0c\x08\xec\x10\x08\xe8\x10\x0c\xe8\x14\x0c\xe4\x14\x0c\xe0\x18\x0c\xe0\x18\x10\xdc\x1c\x10\xd8\x1c\x10\xd8 \x10\xd4 \x14\xd4$\x14\xd0$\x14\xcc(\x14\xcc(\x18\xc8,\x18\xc4,\x18\xc40\x18\xc00\x18\xbc4\x1c\xbc4\x1c\xb88\x1c\xb48\x1c\xb4< \xb0< \xac@ \xac@ \xa8D$\xa8D$\xa4H$\xa0H$\xa0L(\x9cL(\x98P(\x98P(\x94T,\x90T,\x90X,\x8cX,\x88\\0\x88\\0\x84`0\x80d0\x80d0|h4|h4xl4tl4tp8pp8lt8lt8hx<dx<d|<`|<\\\x80@\\\x80@X\x84@X\x84@T\x88DP\x88DP\x8cDL\x8cDH\x90HH\x90HD\x94H@\x94H@\x98H<\x98L8\x9cL8\x9cL4\xa0L0\xa0P0\xa4P,\xa4P,\xa8P(\xa8T$\xacT$\xacT \xb0T\x1c\xb0X\x1c\xb4X\x18\xb4X\x14\xb8X\x14\xb8\\\x10\xbc\\\x0c\xbc\\\x0c\xc0\\\x08\xc4`\x04\xc4`\x04\xc4d\x04\xc4d\x04\xc4h\x04\xc8l\x04\xc8l\x04\xc8p\x04\xc8p\x04\xc8t\x04\xccx\x04\xccx\x04\xcc|\x04\xcc|\x04\xd0\x80\x04\xd0\x84\x04\xd0\x84\x04\xd0\x88\x04\xd0\x88\x04\xd4\x8c\x04\xd4\x90\x04\xd4\x90\x04\xd4\x94\x04\xd8\x98\x04\xd8\x98\x04\xd8\x9c\x04\xd8\x9c\x04\xd8\xa0\x04\xdc\xa4\x04\xdc\xa4\x04\xdc\xa8\x04\xdc\xa8\x04\xe0\xac\x04\xe0\xb0\x04\xe0\xb0\x04\xe0\xb4\x04\xe0\xb4\x04\xe4\xb8\x04\xe4\xbc\x04\xe4\xbc\x04\xe4\xc0\x04\xe4\xc0\x04\xe8\xc4\x04\xe8\xc8\x04\xe8\xc8\x04\xe8\xcc\x04\xec\xd0\x04\xec\xd0\x04\xec\xd4\x04\xec\xd4\x04\xec\xd8\x04\xf0\xdc\x04\xf0\xdc\x04\xf0\xe0\x04\xf0\xe0\x04\xf4\xe4\x04\xf4\xe8\x04\xf4\xe8\x04\xf4\xec\x04\xf4\xec\x04\xf8\xf0\x04\xf8\xf4\x04\xf8\xf4\x04\xf8\xf8\x04\xfc\xfc\x00\xfc\xfch\xfc\xfch\xfc\xfcl\xfc\xfcp\xfc\xfct\xfc\xfcx\xfc\xfcx\xfc\xfc|\xfc\xfc\x80\xfc\xfc\x84\xfc\xfc\x88\xfc\xfc\x88\xfc\xfc\x8c\xfc\xfc\x90\xfc\xfc\x94\xfc\xfc\x98\xfc\xfc\x98\xfc\xfc\x9c\xfc\xfc\xa0\xfc\xfc\xa4\xfc\xfc\xa8\xfc\xfc\xa8\xfc\xfc\xac\xfc\xfc\xb0\xfc\xfc\xb4\xfc\xfc\xb8\xfc\xfc\xb8\xfc\xfc\xbc\xfc\xfc\xc0\xfc\xfc\xc4\xfc\xfc\xc8\xfc\xfc\xc8\xfc\xfc\xcc\xfc\xfc\xd0\xfc\xfc\xd4\xfc\xfc\xd8\xfc\xfc\xd8\xfc\xfc\xdc\xfc\xfc\xe0\xfc\xfc\xe4\xfc\xfc\xe8\xfc\xfc\xe8\xfc\xfc\xec\xfc\xfc\xf0\xfc\xfc\xf4\xfc\xfc\xf8\xfc\xfc\xfc',
	"plasma": '\xf0\xf0\x00\xf0\xe0\x00\xf0\xd0\x00\xf0\xc0\x00\xf0\xb0\x00\xf0\xa0\x00\xf0\x90\x00\xf0\x80\x00\xf0p\x00\xf0`\x00\xf0P\x00\xf0@\x00\xf00\x00\xf0 \x00\xf0\x10\x00\xf0\x00\x00\xe0\xe0\x10\xe0\xd4\x10\xe0\xc8\x10\xe0\xb8\x10\xe0\xac\x0c\xe0\x9c\x0c\xe0\x90\x0c\xe0\x80\x0c\xe0t\x08\xe0d\x08\xe0X\x08\xe0H\x08\xe0<\x04\xe0,\x04\xe0 \x04\xe0\x10\x00\xd0\xd0 \xd0\xc8 \xd0\xbc\x1c\xd0\xb0\x1c\xd0\xa4\x18\xd0\x98\x18\xd0\x8c\x14\xd0\x80\x14\xd0t\x10\xd0h\x10\xd0\\\x0c\xd0P\x0c\xd0D\x08\xd08\x08\xd0,\x04\xd0 \x00\xc0\xc00\xc0\xb80\xc0\xb0,\xc0\xa4(\xc0\x9c$\xc0\x90 \xc0\x88 \xc0\x80\x1c\xc0t\x18\xc0l\x14\xc0`\x10\xc0X\x10\xc0P\x0c\xc0D\x08\xc0<\x04\xc00\x00\xb0\xb0@\xb0\xac<\xb0\xa48\xb0\x9c4\xb0\x940\xb0\x8c,\xb0\x84(\xb0|$\xb0x \xb0p\x1c\xb0h\x18\xb0`\x14\xb0X\x10\xb0P\x0c\xb0H\x08\xb0@\x00\xa0\xa0P\xa0\x9cL\xa0\x98H\xa0\x90@\xa0\x8c<\xa0\x888\xa0\x800\xa0|,\xa0x(\xa0p \xa0l\x1c\xa0h\x18\xa0`\x10\xa0\\\x0c\xa0X\x08\xa0P\x00\x90\x90`\x90\x90\\\x90\x8cT\x90\x88P\x90\x84H\x90\x80@\x90\x80<\x90|4\x90x0\x90t(\x90p \x90p\x1c\x90l\x14\x90h\x10\x90d\x08\x90`\x00\x80\x80p\x80\x80l\x80\x80d\x80\x80\\\x80|T\x80|L\x80|D\x80|<\x80x8\x80x0\x80x(\x80x \x80t\x18\x80t\x10\x80t\x08\x80p\x00pp\x80ppxppppphpt`ptXptPptHpx<px4px,px$p|\x1cp|\x14p|\x0cp\x80\x00``\x90``\x88`d\x80`ht`ll`p``pX`tP`xD`|<`\x800`\x80(`\x84 `\x88\x14`\x8c\x0c`\x90\x00PP\xa0PT\x98PX\x8cP`\x80PdxPhlPp`PtXPxLP\x80@P\x848P\x88,P\x90 P\x94\x18P\x98\x0cP\xa0\x00@@\xb0@D\xa8@L\x9c@T\x90@\\\x84@dx@ll@t`@xT@\x80H@\x88<@\x900@\x98$@\xa0\x18@\xa8\x0c@\xb0\x0000\xc008\xb40@\xa80L\x9c0T\x900`\x800ht0ph0|\\0\x84P0\x90@0\x9840\xa0(0\xac\x1c0\xb4\x100\xc0\x00  \xd0 (\xc4 4\xb8 @\xa8 L\x9c X\x8c d\x80 pp |d \x88T \x94H \xa08 \xac, \xb8\x1c \xc4\x10 \xd0\x00\x10\x10\xe0\x10\x1c\xd4\x10(\xc4\x108\xb4\x10D\xa8\x10T\x98\x10`\x88\x10px\x10|l\x10\x8c\\\x10\x98L\x10\xa8<\x10\xb40\x10\xc4 \x10\xd0\x10\x10\xe0\x00\x00\x00\xf0\x00\x10\xe0\x00 \xd0\x000\xc0\x00@\xb0\x00P\xa0\x00`\x90\x00p\x80\x00\x80p\x00\x90`\x00\xa0P\x00\xb0@\x00\xc00\x00\xd0 \x00\xe0\x10\x00\xf0\x00',
	"rainbow": '\x00\x00\x00\x04\x00\x00\x08\x00\x00\x0c\x00\x00\x10\x00\x00\x14\x00\x00\x18\x00\x00\x1c\x00\x00 \x00\x00$\x00\x00(\x00\x00,\x00\x000\x00\x004\x00\x008\x00\x00<\x00\x00@\x00\x00D\x00\x00H\x00\x00L\x00\x00P\x00\x00U\x00\x00Y\x00\x00]\x00\x00a\x00\x00e\x00\x00i\x00\x00m\x00\x00q\x00\x00u\x00\x00y\x00\x00}\x00\x00\x81\x00\x00\x85\x00\x00\x89\x00\x00\x8d\x00\x00\x91\x00\x00\x95\x00\x00\x99\x00\x00\x9d\x00\x00\xa1\x00\x00\xa5\x00\x00\xaa\x00\x00\xae\x00\x00\xb2\x00\x00\xb6\x00\x00\xba\x00\x00\xbe\x00\x00\xc2\x00\x00\xc6\x00\x00\xca\x00\x00\xce\x00\x00\xd2\x00\x00\xd6\x00\x00\xda\x00\x00\xde\x00\x00\xe2\x00\x00\xe6\x00\x00\xea\x00\x00\xee\x00\x00\xf2\x00\x00\xf6\x00\x00\xfa\x00\x00\xff\x00\x00\xfa\x04\x00\xf6\x08\x00\xf2\x0c\x00\xee\x10\x00\xea\x14\x00\xe6\x18\x00\xe2\x1c\x00\xde \x00\xda$\x00\xd6(\x00\xd2,\x00\xce0\x00\xca4\x00\xc68\x00\xc2<\x00\xbe@\x00\xbaD\x00\xb6H\x00\xb2L\x00\xaeP\x00\xaaU\x00\xa5Y\x00\xa1]\x00\x9da\x00\x99e\x00\x95i\x00\x91m\x00\x8dq\x00\x89u\x00\x85y\x00\x81}\x00}\x81\x00y\x85\x00u\x89\x00q\x8d\x00m\x91\x00i\x95\x00e\x99\x00a\x9d\x00]\xa1\x00Y\xa5\x00U\xaa\x00P\xae\x00L\xb2\x00H\xb6\x00D\xba\x00@\xbe\x00<\xc2\x008\xc6\x004\xca\x000\xce\x00,\xd2\x00(\xd6\x00$\xda\x00 \xde\x00\x1c\xe2\x00\x18\xe6\x00\x14\xea\x00\x10\xee\x00\x0c\xf2\x00\x08\xf6\x00\x04\xfa\x00\x00\xff\x00\x00\xfb\x00\x00\xf8\x00\x00\xf5\x00\x00\xf2\x00\x00\xee\x00\x00\xeb\x00\x00\xe8\x00\x00\xe5\x00\x00\xe1\x00\x00\xde\x00\x00\xdb\x00\x00\xd8\x00\x00\xd4\x00\x00\xd1\x00\x00\xce\x00\x00\xcb\x00\x00\xc7\x00\x00\xc4\x00\x00\xc1\x00\x00\xbe\x00\x00\xbb\x00\x00\xb7\x00\x00\xb4\x00\x00\xb1\x00\x00\xae\x00\x00\xaa\x00\x00\xa7\x00\x00\xa4\x00\x00\xa1\x00\x00\x9d\x00\x00\x9a\x00\x00\x97\x00\x00\x94\x00\x00\x90\x00\x00\x8d\x00\x00\x8a\x00\x00\x87\x00\x00\x83\x00\x00\x80\x00\x00}\x00\x00z\x00\x00w\x00\x00s\x00\x00p\x00\x00m\x03\x00j\x06\x00f\t\x00c\x0c\x00`\x0f\x00]\x12\x00Y\x15\x00V\x18\x00S\x1b\x00P\x1e\x00L \x00I$\x00F\'\x00C*\x00?,\x00<0\x0093\x0066\x0038\x042<\x081?\x0c0A\x10/E\x14.H\x18.K\x1c-N ,Q$+T(*W,*Y0)]4(`8\'c<&f@&iD%lH$oL#qP"uU"xY!{] ~a\x1f\x81e\x1e\x83i\x1d\x87m\x1d\x8aq\x1c\x8du\x1b\x90y\x1a\x93}\x19\x96\x81\x19\x99\x85\x18\x9c\x89\x17\x9f\x8d\x16\xa2\x91\x15\xa5\x95\x15\xa8\x99\x14\xab\x9d\x13\xae\xa1\x12\xb1\xa5\x11\xb3\xaa\x11\xb7\xae\x10\xba\xb2\x0f\xbd\xb6\x0e\xc0\xba\r\xc3\xbe\x0c\xc6\xc2\x0c\xc9\xc6\x0b\xcc\xca\n\xcf\xce\t\xd2\xd2\x08\xd5\xd6\x08\xd8\xda\x07\xdb\xde\x06\xde\xe2\x05\xe1\xe6\x04\xe3\xea\x04\xe7\xee\x03\xea\xf2\x02\xed\xf6\x01\xf0\xfa\x00\xf3\xfa\x00\xf6\xfa\x00\xf9\xfa\x00\xfc',
}
