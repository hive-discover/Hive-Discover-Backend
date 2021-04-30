cmake_minimum_required (VERSION 3.8)
include_directories("../hnswlib")
include_directories("../Simple-Web-Server")



add_executable (${PROJECT_NAME} "main.cpp")

target_link_libraries(${PROJECT_NAME} ${Boost_LIBRARIES})
target_link_libraries(${PROJECT_NAME} ${LIBMONGOCXX_LIBRARIES})
target_link_libraries(${PROJECT_NAME} ${LIBBSONCXX_LIBRARIES})