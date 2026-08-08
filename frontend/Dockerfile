FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# write proxy target for vite preview to read at runtime
ARG VITE_API_PROXY_TARGET=http://api:8000
RUN printf "VITE_API_PROXY_TARGET=%s\n" "$VITE_API_PROXY_TARGET" > .env.production && npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/.env.production ./.env.production
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./

EXPOSE 3000
CMD ["npm", "run", "preview", "--", "--host", "--port", "3000"]
