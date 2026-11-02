LIBS ?= $(abspath ../libs)
J = $(LIBS)/jpegdec/src
E = $(LIBS)/jpegenc/src
P = $(LIBS)/pngdec/src
CXXFLAGS = -O2 -D__LINUX__ -DPNG_MAX_BUFFERED_PIXELS=16386 -I$(J) -I$(E) -I$(P) -I..
CFLAGS = -O2 -D__LINUX__ -I$(P)
Z = adler32 crc32 infback inffast inflate inftrees zutil
imgcli: imgcli.c ../imgcore.cpp $(J)/JPEGDEC.cpp $(E)/JPEGENC.cpp $(P)/PNGdec.cpp $(Z:%=$(P)/%.c)
	$(CC) $(CFLAGS) -c imgcli.c -o imgcli.o
	for z in $(Z); do $(CC) $(CFLAGS) -c $(P)/$$z.c -o z_$$z.o; done
	$(CXX) $(CXXFLAGS) -c ../imgcore.cpp -o imgcore.o
	$(CXX) $(CXXFLAGS) -c $(J)/JPEGDEC.cpp -o jpegdec.o
	$(CXX) $(CXXFLAGS) -c $(E)/JPEGENC.cpp -o jpegenc.o
	$(CXX) $(CXXFLAGS) -c $(P)/PNGdec.cpp -o pngdec.o
	$(CXX) -o $@ *.o
clean:
	rm -f *.o imgcli
