#include "nmslib_api.h"
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

#include "main.h"
#include "nmslib_worker.h"

using HttpServer = SimpleWeb::Server<SimpleWeb::HTTP>;

namespace Endpoints {
    using namespace boost::property_tree;

    void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
        response->write("Running");
    }

    void feed(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
        std::thread workerThread([response, request] {
            try {
                // Prepare request Body
                ptree reqBody, resBody, feedItems;
                read_json(request->content, reqBody);

                // Do Task and add it into reqBody 
                resBody.put("status", "ok");
                feedItems = getFeed(
                    reqBody.get<int>("account_id"), reqBody.get<std::string>("account_name"),
                    reqBody.get<int>("amount"), config::pool,
                    reqBody.get<int>("abstraction_value")
                );
                resBody.add_child("result", feedItems);

                // Serialize reqBody and send it
                std::ostringstream oss;
                write_json(oss, resBody);
                response->write(oss.str());

            }
            catch (const std::exception& e) {
                // Something went wrong
                *response << "HTTP/1.1 400 Bad Request\r\nContent-Length: " << strlen(e.what()) << "\r\n\r\n" << e.what();
            }
            });
        workerThread.detach();
    }

    void sortPersonalized(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
        std::thread workerThread([response, request] {
            try {
                // Prepare request Body
                ptree reqBody, resBody, sortedItems;
                read_json(request->content, reqBody);

                // Do Task and add it into reqBody 
                resBody.put("status", "ok");
                sortedItems = sortPersonalizedIds(
                    reqBody.get<int>("account_id"), reqBody.get<std::string>("account_name"),
                    reqBody.get_child("query_ids"), config::pool
                );
                resBody.add_child("result", sortedItems);

                // Serialize reqBody and send it
                std::ostringstream oss;
                write_json(oss, resBody);
                response->write(oss.str());

            }
            catch (const std::exception& e) {
                // Something went wrong
                *response << "HTTP/1.1 400 Bad Request\r\nContent-Length: " << strlen(e.what()) << "\r\n\r\n" << e.what();
            }
            });
        workerThread.detach();
    }

    void defineRoutes(HttpServer& server) {
        server.resource["^/$"]["GET"] = index;
        server.resource["^/feed$"]["POST"] = feed;
        server.resource["^/sort/personalized$"]["POST"] = sortPersonalized;

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


int runAPI(const int port) {  
    std::cout << "Starting API..." << std::endl;
    std::thread indexManager_Thread(manageIndex, std::pair<mongocxx::pool&, bool>(config::pool, false));

    // Start Server
    HttpServer server;
    server.config.port = port;
    Endpoints::defineRoutes(server);
    std::cout << "Server listening on port " << port << std::endl;
    server.start();

    indexManager_Thread.detach();
    return 0;
}

