# Fix to match the location of the (uninstalled) C slalib/C sofa
SLADIR = ~/gavo/soft/SLALIB
SOFADIR = ~/gavo/soft/sofa


CFLAGS+=-I $(SLADIR) -I $(SOFADIR) -Wall
LDLIBS+=-L $(SLADIR) -lsla -L $(SOFADIR) -lsofa_c -lm 


stcgroundtruth.py: makestctruth
	./makestctruth > stcgroundtruth.py

makestctruth: makestctruth.o


clean:
	rm -r *.o maketest
