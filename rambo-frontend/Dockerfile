# ---------- FRONTEND BUILD STAGE ----------
FROM node:20 AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .
RUN npm run build

# ---------- NGINX SERVE STAGE ----------
FROM nginx:stable

# Copy built React app to Nginx html directory
COPY --from=build /app/build /usr/share/nginx/html

# SPA routing fallback so deep links / refreshes don't 404
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 (Nginx default)
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
