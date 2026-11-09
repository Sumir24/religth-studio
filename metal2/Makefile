CXX = clang++
CXXFLAGS = -O3 -std=c++17 -fPIC -Wall -Wextra -Wno-unused-parameter
FRAMEWORKS = -framework Metal -framework Foundation -framework CoreGraphics
TARGET = libmetal2.dylib
SRC = src/metal_bridge.mm

all: $(TARGET)

$(TARGET): $(SRC) src/metal_bridge.h
	$(CXX) $(CXXFLAGS) $(FRAMEWORKS) -shared -o $(TARGET) $(SRC)

clean:
	rm -f $(TARGET)

.PHONY: all clean
