FROM node:22-alpine AS base

RUN corepack enable && corepack prepare pnpm@10.6.2 --activate
WORKDIR /app

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --frozen-lockfile || pnpm install

COPY apps/web apps/web

RUN pnpm --filter @di-aai-fs/web build

EXPOSE 3000

CMD ["pnpm", "--filter", "@di-aai-fs/web", "start"]
