ARG NODE_IMAGE=docker.io/library/node:24.20.0@sha256:6642ef280aebc09c4541bee0b15c9f89f0f3f3c247ddee79ae1d37eddfdcbbaa
FROM ${NODE_IMAGE} AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.23.0 --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY tsconfig*.json ./
COPY src ./src
RUN pnpm run build && pnpm prune --prod

FROM ${NODE_IMAGE}
ARG NODE_IMAGE
LABEL org.opencontainers.image.base.name=${NODE_IMAGE}
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
RUN mkdir /state && chown node:node /state
USER node
EXPOSE 8080
CMD ["node", "dist/server.js"]
