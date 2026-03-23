# Build stage
FROM node:20-alpine as build
WORKDIR /app
COPY package*.json ./
# Since bun.lock and bun.lockb exist, we can use npm but to be safe let's just use npm ci or install.
# Since we have package-lock.json we just run npm install
RUN npm install
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
# Copy the custom nginx configuration for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
