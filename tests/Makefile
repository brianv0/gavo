# Fix to match the location of the (uninstalled) C slalib
SLADIR = ~/gavo/soft/SLALIB


CFLAGS+=-I $(SLADIR) -Wall
LDLIBS+=-L $(SLADIR) -lsla -lm 


stcgroundtruth.py: makestctruth
	./makestctruth > stcgroundtruth.py

makestctruth: makestctruth.o


clean:
	rm -r *.o maketest
