FROM node:14.16

WORKDIR /NodeJS
COPY ["package.json", "package-lock.json*", "./"]
RUN npm install --production

COPY . .
ENTRYPOINT [ "node", "app.js" ]
