# Wohnungsradar Browser-Dienst: führt zweimal täglich die Lese-Rezepte der JavaScript-Makler in einem
# unsichtbaren Chromium aus und legt die Rohdaten in GitHub ab (Zweig "engine", Datei inbox/browser/latest.json).
FROM mcr.microsoft.com/playwright:v1.49.1-noble
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY service.mjs ./
ENV NODE_ENV=production PORT=3000
EXPOSE 3000
CMD ["node", "service.mjs"]
