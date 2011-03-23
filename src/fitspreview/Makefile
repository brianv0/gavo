LDFLAGS=-lcfitsio -ljpeg -lm
CFLAGS=-Wall -g

TARGET=$(shell  P=`gavo config platform`; if [ -z $$P ]; \
	then echo "fitspreview"; else echo "fitspreview-$$P"; fi)

# REMOVE THIS WHEN DONE
fitspreview-i386:

install:

$(TARGET): fitspreview.o
	$(CC) $(CFLAGS) -o $(TARGET) $^ $(LDFLAGS)

install: $(TARGET)
	cp $(TARGET) `gavo config inputsDir`/__system/bin

clean:
	rm -f *.o fitspreview $(TARGET)
