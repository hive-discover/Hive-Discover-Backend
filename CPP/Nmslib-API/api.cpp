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

    /// <summary>
    /// Handle Path: "/" GET
    /// ==> Check if Server is running
    /// </summary>
    /// <param name="response"></param>
    /// <param name="request"></param>
    void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
        response->write("Running");
    }

    /// <summary>
    /// Handle Path: "/feed" POST
    /// ==> Create a Feed for an Account. More information into worker.cpp->getFeed()
    /// </summary>
    /// <param name="response">Should contain: account_id, account_name, amount, abstraction_value</param>
    /// <param name="request"></param>
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
                        reqBody.get<int>("amount"), pool, 
                        reqBody.get<int>("abstraction_value")
                );
                resBody.add_child("result", feedItems);

                // Serialize reqBody and send it
                std::ostringstream oss;
                write_json(oss, resBody);
                response->write(oss.str());

            } catch (const std::exception& e) {
                // Something went wrong
                *response << "HTTP/1.1 400 Bad Request\r\nContent-Length: " << strlen(e.what()) << "\r\n\r\n" << e.what();
            }
        });   
        workerThread.detach();
    } 

    /// <summary>
    /// Handle Path: "/sort/personalized" POST
    /// </summary>
    /// <param name="response">Should contain: account_id, account_name, query_ids</param>
    /// <param name="request"></param>
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
                    reqBody.get_child("query_ids"), pool
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

    /// <summary>
    /// Define all possible Entrypoints
    /// </summary>
    /// <param name="server">On which HttpServer instance should the routes be defined?</param>
    void define(HttpServer& server) {
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


/// <summary>
/// Entrypoint for top main.cpp to start the NMSLIB-API
/// </summary>
/// <param name="port">Which Http-Port should the API run?</param>
/// <returns>Status Code (when API exits). Mainly an error code!</returns>
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
