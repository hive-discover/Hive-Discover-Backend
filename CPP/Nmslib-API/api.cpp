#include <iostream>
#include <thread>
#include <vector>
#include <string>

#include <mongocxx/instance.hpp>
#include <mongocxx/uri.hpp>
#include <mongocxx/pool.hpp>
#include <mongocxx/client.hpp>
#include <bsoncxx/json.hpp>

#include "Simple-Web-Server/server_http.hpp"
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include "main.hpp"
#include "worker.cpp"

using HttpServer = SimpleWeb::Server<SimpleWeb::HTTP>;

mongocxx::instance instance{};
mongocxx::pool pool{ mongocxx::uri{ config::MongoDB_URL } };


namespace Endpoints {
    using namespace boost::property_tree;

    void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
        response->write("Running");
    }

    void feed(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {       
       // std::thread workerThread([response, request] {
            try {
                // Prepare request Body
                ptree reqBody;
                read_json(request->content, reqBody);

                // Do Task and Send response
                ptree resBody = getFeed(reqBody.get<int>("account_id"), reqBody.get<std::string>("account_name"), reqBody.get<int>("amount"), pool);
                std::ostringstream oss;
                write_json(oss, resBody);
                response->write(oss.str());

            } catch (const std::exception& e) {
                *response << "HTTP/1.1 400 Bad Request\r\nContent-Length: " << strlen(e.what()) << "\r\n\r\n" << e.what();
            }
        //});   
        //workerThread.detach();
    } 

    void define(HttpServer& server) {
        server.resource["^/$"]["GET"] = index;
        server.resource["^/feed$"]["POST"] = feed;

        server.resource["^/json$"]["POST"] = [](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
            try {
                ptree pt;
                read_json(request->content, pt);

                auto name = pt.get<std::string>("firstName") + " " + pt.get<std::string>("lastName");

                response->write(name);
            }
            catch (const std::exception& e) {
                *response << "HTTP/1.1 400 Bad Request\r\nContent-Length: " << strlen(e.what()) << "\r\n\r\n" << e.what();
            }
        };
    }
}


// Executed from top main.cpp
int runAPI(const int port = 8000) {
	std::cout << "Starting API..." << std::endl;
	std::thread indexManager_Thread(manageIndex, std::pair<mongocxx::pool&, bool>(pool, false));

    // Start Server
    HttpServer server;
    server.config.port = port;
    Endpoints::define(server);
    std::cout << "Server listening on port " << port << std::endl;
    server.start();

	indexManager_Thread.detach();
	return 0;
}
