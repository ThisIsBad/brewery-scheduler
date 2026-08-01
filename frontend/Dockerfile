# Dev-mode Dockerfile. Phase 1 only ships local dev; production build goes
# straight to Azure Static Web Apps in Phase 5.

FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
