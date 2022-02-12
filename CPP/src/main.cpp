#include "main.h"

#include <iostream>
#include "NswAPI/index.h"
#include "ImageAPI/listener.h"

mongocxx::instance GLOBAL::MongoDB::inst{};
mongocxx::pool GLOBAL::MongoDB::mongoPool{ mongocxx::uri{GLOBAL::MongoUrl} };

namespace StartArguments {

	void initOptionDescription(){
		desc.add_options()
			("help", "produce help message")
			("image_api", "start Image API")
			("nsw_api", "start Nsw API")
			;
	}

	void parseOptions(const int argc, const char* argv[]) {
		po::store(po::parse_command_line(argc, argv, desc), vm);
		po::notify(vm);
	};
}

int main(int argc, const char* argv[]) {
	// Start-Options Handling
	std::cout << "[INFO] Parsing Start-Options..." << std::endl;
	StartArguments::initOptionDescription();
	StartArguments::parseOptions(argc, argv);

	if (StartArguments::vm.count("help")) {
		std::cout << StartArguments::desc << std::endl;
		return 0;
	}

	// Start fired functions
	std::cout << "[INFO] Starting CPP-Backend..." << std::endl;	
	std::vector<std::future<int>> tasks_running;

	if(StartArguments::vm.count("image_api"))
		tasks_running.emplace_back(std::async(ImageAPI::start));
	if (StartArguments::vm.count("nsw_api"))
		tasks_running.emplace_back(std::async(NswAPI::start));

	std::cout << "[INFO] Started all defined functions. Running until an error occurs!" << std::endl;

	// We do not have to wait here because futures wait at the end of the scope to end
	return 0;
}
