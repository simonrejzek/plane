# Mirrored app.plane.so commercial web SPA for self-host.
# UI assets from cloud; runtime API/PI are same-origin (DeepSeek PI, CE API).
FROM nginx:1.27-alpine

COPY public/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf

# plane proxy expects web:3000
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
