LDFLAGS=-lcfitsio -ljpeg -lm
CFLAGS=-Wall -g

TARGET=$(shell  P=`gavoconfig platform`; if [ -z $P ]; \
	then echo "fitspreview"; else echo "fitspreview-$P"; fi)

install:

TARGET: fitspreview.o
	$(CC) $(CFLAGS) -o $(TARGET) $^ $(LDFLAGS)

install: $(TARGET)
	cp $(TARGET) ../bin

clean:
	rm -f *.o fitspreview
