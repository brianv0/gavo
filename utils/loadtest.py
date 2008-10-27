"""
A script that runs quite a number of queries (actually, regression tests)
to the server at once and sees if any fail under load.
"""
# ** ARI-Location: ella.cl.uni-heidelberg.de:gavotest/

import Queue
import cPickle
import random
import sys
import threading
import time
import traceback
import urllib

import roughtest

def doTimedQuery(aTest):
	start = time.time()
	try:
		aTest.run()
		return "OK", time.time()-start, aTest.description, ""
	except AssertionError, msg:
		return "FAIL", time.time()-start, aTest.description, aTest.lastResult
	except Exception, msg:
		traceback.print_exc()
		return "FAIL", time.time()-start, aTest.description, msg


def runTest(aTest, outputQueue, id):
	"""runs a test, signalling its outcome to outputQueue.

	This is supposed to be run as a target of a threading.Thread.
	"""
	outputQueue.put(("testFinished", id, doTimedQuery(aTest)))


class TestStatistics:
	def __init__(self):
		self.runs = []
		self.oks, self.fails, self.total = 0, 0, 0
		self.globalStart = time.time()
		self.lastTimestamp = time.time()+1
		self.timeSum = 0
	
	def add(self, status, runTime, title, payload):
		if status=="OK":
			self.oks += 1
		else:
			self.fails += 1
		self.total += 1
		self.timeSum += runTime
		self.runs.append((runTime, status, title, payload))
		self.lastTimestamp = time.time()

	def getReport(self):
		try:
			return ("%d of %d bad.  avg %.2f, min %.2f, max %.2f. %.1f/s, par %.1f"
				)%(self.fails, self.fails+self.oks, self.timeSum/len(self.runs),
				min(self.runs)[0], max(self.runs)[0], float(self.total)/(
					self.lastTimestamp-self.globalStart),
				self.timeSum/(self.lastTimestamp-self.globalStart))
		except ZeroDivisionError:
			return "No report yet"

	def save(self, target):
		f = open(target, "w")
		cPickle.dump(self.runs, f)
		f.close()


class TestRunner:
	def __init__(self, testCollection, nSimul, nTotal):
		self.testCollection = testCollection
		self.nSimul, self.nTotal = nSimul, nTotal
		self.inputQueue = Queue.Queue()
		self.threadPool = {}
		self.stats = TestStatistics()
		self.nextThreadId = 0

	def _spawnThread(self):
		t = random.choice(self.testCollection)
		newThread = threading.Thread(target=runTest, args=(t, self.inputQueue,
			self.nextThreadId))
		self.threadPool[self.nextThreadId] = newThread
		self.nextThreadId += 1
		newThread.setDaemon(True)
		newThread.start()

	def _spawnThreads(self):
		while len(self.threadPool)<self.nSimul:
			self._spawnThread()

	def _handleEvent(self, ev):
		msg, id, stats = ev
		assert msg=="testFinished"
		self.stats.add(*stats)
		del self.threadPool[id]

	def _collectRemainingThreads(self):
		timeoutStart = time.time()
		while len(self.threadPool):
			self._handleEvent(self.inputQueue.get(block=True, timeout=10))
			if time.time()-timeoutStart>20:
				break
		if len(self.threadPool):
			print "\n*************%d hung threads!"%len(self.threadPool)

	def mainloop(self):
		try:
			while self.stats.total<=self.nTotal-self.nSimul:
				self._spawnThreads()
				self._handleEvent(self.inputQueue.get(block=True, timeout=10))
				sys.stdout.write("\r"+self.stats.getReport())
				sys.stdout.flush()
		except Queue.Empty:
			print "**** Too many hung threads, giving up"
		self._collectRemainingThreads()


class _StreamTest(object):
	"""is a test requesting a random amount of data from test/streaming.
	"""
	description = "Get lotsa bytes"

	def run(self):
		chunkSize = [100, 500, 1000, 10000, 50000][random.randint(0, 4)]
		if random.random()<0.01:
			dataSize = 10**random.randint(6, 8)+random.randint(0, 400000)
		else:
			dataSize = 10**random.randint(1, 7)+random.randint(0, 40000)
		f = urllib.urlopen(
			"http://localhost:8080/test/stream?chunkSize=%d&size=%d"%(
				chunkSize, dataSize))
		dataLength = 0
		while True:
			res = f.read(65536)
			if not res:
				break
			dataLength += len(res)
		f.close()
		assert dataLength==dataSize



class _PreviewTest(object):
	"""is a test requesting a cutout preview.
	"""
	description = "Get cutout preview"

	previewURL = ("http://localhost:8080/__system__/products/products/p"
		"/get?key=lswscans/data/Bruceplatten/FITS/B2866b.fits%26amp"
		"%3Bra%3D2.0%26amp%3Bdec%3D2.0%26amp%3Bsra%3D0.2%26amp%3Bsdec"
		"%3D0.2&preview=True")
	previewSize = 9748

	def run(self):
		res = urllib.urlopen(self.previewURL).read()
		assert len(res)==self.previewSize


testGroupsWithState = set(["dexter", "upload"])

def _getTestCollection():
	tests = []
	for tg in roughtest.myTests:
		if tg.name in testGroupsWithState:
			continue
		tests.extend(tg.tests)
	return tests

#def _getTestCollection():
#	return [roughtest.myTests[5].tests[1]]

def _getNSimul():
	if len(sys.argv)>1:
		return (int(sys.argv[1]))
	return 3

def _getNTotal():
	if len(sys.argv)>2:
		return (int(sys.argv[2]))
	return 1000

def main():
	if len(sys.argv)>3:
		if sys.argv[3]=="stream":
			tests = [_StreamTest()]
		elif sys.argv[3]=="preview":
			tests = [_PreviewTest()]
		else:
			raise Exception("Dammit")
	else:
		tests = _getTestCollection()
	tr = TestRunner(tests, _getNSimul(), _getNTotal())
	try:
		tr.mainloop()
	except KeyboardInterrupt:
		pass
	print "\n End of load test"
	print tr.stats.getReport()
	tr.stats.save("laststats.pickle")


if __name__=="__main__":
	main()
