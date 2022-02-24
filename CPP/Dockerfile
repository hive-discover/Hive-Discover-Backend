FROM registry.hive-discover.tech/cpp:0.1

# All Dependencies come from the cpp-background image

# Copy to / src
RUN mkdir /src /build
WORKDIR /src
COPY . .

EXPOSE 2626
EXPOSE 2525

# Build /src to /build
WORKDIR /build
RUN cmake -DCMAKE_BUILD_TYPE=Release /src && make   

ENTRYPOINT ["./cpp-backend"]