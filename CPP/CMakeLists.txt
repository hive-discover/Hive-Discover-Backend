cmake_minimum_required (VERSION 3.8)
project ("CPP")

# BOOST  
find_package(Boost REQUIRED) 
include_directories(${Boost_INCLUDE_DIRS})
link_directories(${Boost_LIBRARY_DIRS}) 

# Mongo Driver
find_package(libmongocxx REQUIRED)  
find_package(libbsoncxx REQUIRED)
include_directories(${LIBMONGOCXX_INCLUDE_DIR} ${LIBBSONCXX_INCLUDE_DIR})
link_directories(${LIBMONGOCXX_INCLUDE_DIR} ${LIBBSONCXX_INCLUDE_DIR}) 
 
   
# Extern Header Libraries 
add_subdirectory("hnswlib")
add_subdirectory("Simple-Web-Server") 

add_executable(${PROJECT_NAME} "main.cpp" "main.hpp")

# Own Libraries
add_subdirectory("Nmslib-API")
target_link_libraries(${PROJECT_NAME} Nmslib-API)

