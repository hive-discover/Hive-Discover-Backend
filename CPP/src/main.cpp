#include "main.h"

#include <iostream>
#include "NswAPI/index.h"
#include "ImageAPI/listener.h"
#include <stdio.h>

// Extern Var Definitions
std::atomic<bool> GLOBAL::STOP_PROCESS(false);
std::atomic<bool> GLOBAL::SERVER_IS_READY(false);
std::atomic<bool> GLOBAL::isPrimary(true);
std::atomic<int> GLOBAL::PRE_DELAY{0};


mongocxx::instance GLOBAL::MongoDB::inst{};
mongocxx::pool GLOBAL::MongoDB::mongoPool{ mongocxx::uri{GLOBAL::MongoUrl} };


namespace StartArguments {

	void initOptionDescription(){
		desc.add_options()
			("help", "produce help message")
			("image_api", "start Image API")
			("nsw_api", "start Nsw API")
			("secondary", "Set the program as a secondary-instance with less computings")
			("pre_delay", po::value<int>(), "Time in seconds to wait before calculating heavy stuff (only at start-up)")
			;
	}

	void parseOptions(const int argc, const char* argv[]) {
		po::store(po::parse_command_line(argc, argv, desc), vm);
		po::notify(vm);
	}

	void evalOptions() {
		// Get docker's Task Slot of this instance (replicas start counting from 1 to ...)
		// ==> when task slot equals 1, it should be the primary instance (default) else secondary is turned on
		const char* TASK_SLOT = std::getenv("TASK_SLOT");

		if (vm.count("secondary") || std::stoi(TASK_SLOT ? TASK_SLOT : "1") != 1)
			GLOBAL::isPrimary = false;
		if (vm.count("pre_delay"))
			GLOBAL::PRE_DELAY = vm["pre_delay"].as<int>();			
	}
}

int main(int argc, const char* argv[]) {
	// Start-Options Handling
	std::cout << "[INFO] Parsing Start-Options..." << std::endl;
	StartArguments::initOptionDescription();
	StartArguments::parseOptions(argc, argv);
	StartArguments::evalOptions();

	// Print mode: primary or secondary?
	std::cout << "[INFO] " << ESC << WHITE_BKG << ";"; // Start Line
	if (GLOBAL::isPrimary)
		std::cout << RED_TXT << "m primary-mode ";
	else
		std::cout << GREEN_TXT << "m secondary-mode ";
	std::cout << RESET << " activated." << std::endl; // finish Line

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
