FROM ubuntu:20.04

# General Stuff
ENV TZ=Europe/Minsk
ENV DEBIAN_FRONTEND=noninteractive 
RUN apt-get update && apt-get upgrade
RUN apt-get update && apt-get install -y build-essential g++ make cmake unzip zip git curl tar wget pkg-config nano

# Install Dependencies for Mongo Driver
RUN apt-get install -y libmongoc-1.0-0  libbson-1.0 libssl-dev libsasl2-dev

# Get Boost
#WORKDIR /usr/local/
#RUN wget https://boostorg.jfrog.io/artifactory/main/release/1.76.0/source/boost_1_76_0.tar.gz
#RUN tar -xzf boost_1_76_0.tar.gz
RUN apt-get install -y libboost-all-dev libssl-dev

WORKDIR /

# Build Mongo C Driver and Bson
RUN wget https://github.com/mongodb/mongo-c-driver/releases/download/1.17.5/mongo-c-driver-1.17.5.tar.gz && tar xzf mongo-c-driver-1.17.5.tar.gz
RUN mkdir mongo-c-driver-1.17.5/cmake-build
WORKDIR mongo-c-driver-1.17.5/cmake-build
RUN cmake -DENABLE_AUTOMATIC_INIT_AND_CLEANUP=OFF .. && cmake --build . && cmake --build . --target install

WORKDIR /

# Build Mongo Cxx Driver
RUN curl -OL https://github.com/mongodb/mongo-cxx-driver/releases/download/r3.6.3/mongo-cxx-driver-r3.6.3.tar.gz && tar -xzf mongo-cxx-driver-r3.6.3.tar.gz
WORKDIR mongo-cxx-driver-r3.6.3/build
RUN cmake .. -DCMAKE_BUILD_TYPE=Release -DLIBMONGOC_DIR=/mongo-c-driver-1.17.5 -DLIBBSON_DIR=/mongo-c-driver-1.17.5 -DCMAKE_INSTALL_PREFIX=/usr/local/ && cmake --build . && cmake --build . --target install

# Get more Boost
WORKDIR /usr/local/
RUN wget https://boostorg.jfrog.io/artifactory/main/release/1.76.0/source/boost_1_76_0.tar.gz
RUN tar -xzf boost_1_76_0.tar.gz

# Get nlohmann::json
RUN apt-get install -y nlohmann-json3-dev

# Copy to / src
RUN mkdir /src /build
WORKDIR /src
COPY . .

EXPOSE 2626

# Build /src to /build
WORKDIR /build
RUN cmake -DCMAKE_BUILD_TYPE=Release /src && make   

ENTRYPOINT ["./cpp-backend"]