cmake_minimum_required (VERSION 3.8)
project ("CPP")

# Find: BOOST  
include_directories(${BOOST_ROOT})
find_package(Boost REQUIRED) 
message(STATUS "Boost is found at: ${BOOST_ROOT} | ${Boost_INCLUDE_DIRS} | ${Boost_LIBRARY_DIRS}")
include_directories(${Boost_INCLUDE_DIRS})
link_directories(${Boost_LIBRARY_DIRS}) 

# Find: Mongo Driver
if(UNIX) 
	# Mongo-Includes for Ubuntu Versions
	include_directories("/usr/local/include/mongocxx/v_noabi")
	include_directories("/usr/local/include/bsoncxx/v_noabi")
	include_directories("/usr/local/include/libmongoc-1.0")
	include_directories("/usr/local/include/libbson-1.0")
	include_directories("/usr/local/lib")
	include_directories("/mongo-c-driver-1.17.5")
endif()

find_package(libmongocxx REQUIRED)  
find_package(libbsoncxx REQUIRED)
message(STATUS "Mongocxx is found at: ${LIBMONGOCXX_INCLUDE_DIR} | ${LIBMONGOCXX_LIBRARIES}")
message(STATUS "Bsoncxx is found at: ${LIBBSONCXX_INCLUDE_DIR} | ${LIBBSONCXX_LIBRARIES}")
include_directories(${LIBMONGOCXX_INCLUDE_DIR} ${LIBBSONCXX_INCLUDE_DIR})
link_directories(${LIBMONGOCXX_INCLUDE_DIR} ${LIBBSONCXX_INCLUDE_DIR}) 
 
   
# Project Directory
add_subdirectory("hnswlib")
add_subdirectory("Simple-Web-Server") 
add_subdirectory("Nmslib-API")

add_executable(${PROJECT_NAME} "main.cpp" "main.hpp")

target_link_libraries(${PROJECT_NAME} Nmslib-API)

