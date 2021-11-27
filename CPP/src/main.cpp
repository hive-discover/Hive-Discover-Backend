#include "main.h"

#include <iostream>
#include "NswAPI/index.h"

mongocxx::instance GLOBAL::MongoDB::inst{};
mongocxx::pool GLOBAL::MongoDB::mongoPool{ mongocxx::uri{GLOBAL::MongoUrl} };

int main() {
	std::cout << "[INFO] Starting CPP-Backend" << std::endl;	

	NswAPI::start();

	// Wait to not end this Process
	while (!GLOBAL::STOP_PROCESS)
		std::this_thread::sleep_for(std::chrono::milliseconds(1500));

	std::cout << "[INFO] Terminating CPP-Backend" << std::endl;
	return 0;
}
