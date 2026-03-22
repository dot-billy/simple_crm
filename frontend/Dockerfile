FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

CMD ["npm", "run", "start"]
