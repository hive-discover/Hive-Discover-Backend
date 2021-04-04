FROM node:14.16

WORKDIR /HiveDiscoverAPI
COPY ["package.json", "package-lock.json*", "./"]
RUN npm install --production

COPY . .
CMD [ "node", "app.js" ]
