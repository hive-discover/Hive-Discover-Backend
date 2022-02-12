#ifndef IMAGE_API_LISTENER_H
#define IMAGE_API_LISTENER_H

#include <thread>
#include <nlohmann/json.hpp>
#include "Simple-Web-Server/server_http.hpp"

namespace ImageAPI {
	using HttpServer = SimpleWeb::Server<SimpleWeb::HTTP>;


	int start();

	namespace Listener {
		static HttpServer server;
		static std::thread serverThread;

		void defineRoutes();
		void runAPI();
	

		namespace Endpoints {
			// All over POST-Method

			void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

			void text_searching(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

			void similar_searching(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);
		}
	}
}

#endif