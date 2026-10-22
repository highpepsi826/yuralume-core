FROM node:22.23.4-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d

WORKDIR /app

ENV NODE_ENV=production

COPY sidecars/whatsapp/package*.json ./
RUN npm ci --omit=dev --ignore-scripts \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

COPY sidecars/whatsapp/src ./src

RUN mkdir -p /data/auth /data/media \
    && chown -R node:node /data /app

USER node

EXPOSE 32190

CMD ["node", "src/main.js"]
