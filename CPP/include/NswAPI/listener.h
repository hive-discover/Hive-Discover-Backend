#ifndef NswAPI_LISTENER_H
#define NswAPI_LISTENER_H

#include <thread>
#include <nlohmann/json.hpp>
#include "Simple-Web-Server/server_http.hpp"

namespace NswAPI {
	using HttpServer = SimpleWeb::Server<SimpleWeb::HTTP>;


	namespace Endpoints {
		void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

		void feed(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

		void similar_by_category(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

		void similar_by_permlink(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

		void similar_accounts(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);
	}

	namespace Listener {
		static HttpServer server;
		static std::thread serverThread;

		void defineRoutes();

		void startAPI();
	}
}

#endif