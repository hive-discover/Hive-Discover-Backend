cmake_minimum_required (VERSION 3.8)
project("Nmslib-API")

include_directories("..")
include_directories("../hnswlib/hnswlib")
include_directories("../Simple-Web-Server")

add_library(${PROJECT_NAME} STATIC "api.cpp" "worker.cpp")
 

target_link_libraries(${PROJECT_NAME} ${Boost_LIBRARIES})
target_link_libraries(${PROJECT_NAME} ${LIBMONGOCXX_LIBRARIES})
target_link_libraries(${PROJECT_NAME} ${LIBBSONCXX_LIBRARIES})