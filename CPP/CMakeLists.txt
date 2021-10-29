cmake_minimum_required(VERSION 3.8)
project("cpp-backend")

# Find Boost
find_package(Boost REQUIRED COMPONENTS program_options system context) 
include_directories(${Boost_INCLUDE_DIRS})
link_directories(${BOOST_ROOT} ${Boost_LIBRARY_DIRS}) 

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

find_package(nlohmann_json REQUIRED)

add_subdirectory("libs/Simple-Web-Server") 
add_subdirectory("libs/hnswlib") 

# Add Source Files: all .cpp from /src...
file(GLOB PROJECT_SRC src/*.cpp src/*/*.cpp src/*/*/*.cpp)
add_executable(${PROJECT_NAME} ${PROJECT_SRC})

# Enable C++11 standard compliance 
set_property (TARGET ${PROJECT_NAME}
  PROPERTY CXX_STANDARD 11
)

# Link Headers and Libs
target_include_directories(${PROJECT_NAME} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_include_directories(${PROJECT_NAME} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/libs")
target_link_libraries(${PROJECT_NAME} simple-web-server)

# Link extern libraries
target_link_libraries(${PROJECT_NAME} ${Boost_LIBRARIES} ${Boost_SYSTEM_LIBRARY} ${Boost_FILESYSTEM_LIBRARY})
target_link_libraries(${PROJECT_NAME} Boost::boost Boost::system Boost::program_options Boost::context)
target_link_libraries(${PROJECT_NAME} hnswlib)
target_link_libraries(${PROJECT_NAME} nlohmann_json)
target_link_libraries(${PROJECT_NAME} ${LIBMONGOCXX_LIBRARIES})
target_link_libraries(${PROJECT_NAME} ${LIBBSONCXX_LIBRARIES})