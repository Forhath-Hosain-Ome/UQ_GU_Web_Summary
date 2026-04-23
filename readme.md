# permisson
sudo chown -R $USER:$USER /home/dev_f4016/project/UQ_GU_Web_Summary/backend/media/uploads

# 
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=172.28.126.15


New-NetFirewallRule -DisplayName "WSL 8080" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow

netsh interface portproxy show all

Here’s the **clean summary — only commands + one-line purpose each**:

---

### 🔹 Get your WSL IP

```bash
hostname -I
```

➡ Get WSL internal IP for port forwarding

---

### 🔹 Forward Windows → WSL port

```powershell
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=172.28.126.15
```

➡ Allow LAN devices to access WSL services

---

### 🔹 Allow firewall

```powershell
New-NetFirewallRule -DisplayName "WSL 8080" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
```

➡ Open port 8080 for external access

---

### 🔹 Restart WSL networking

```powershell
wsl --shutdown
```

➡ Reset WSL networking issues / port binding

---

### 🔹 Check port binding

```powershell
netstat -ano | findstr :8080
```

➡ Verify if port is exposed to LAN (0.0.0.0 vs 127.0.0.1)

---

### 🔹 Check running containers

```bash
docker ps
```

➡ Confirm frontend/backend are running

---

### 🔹 Test backend from frontend container

```bash
docker exec -it frontend curl http://backend:8000
```

➡ Verify Docker internal connectivity (fix 502 errors)

---

### 🔹 Check Docker network

```bash
docker network ls
```

➡ Ensure services share same network

---

### 🔹 Test container DNS

```bash
docker exec -it frontend ping backend
```

➡ Confirm backend is resolvable inside Docker

---

### 🔹 Restart containers

```bash
docker compose up -d --build
```

➡ Rebuild and restart full stack

---

### 🔹 Fix frontend API base (code)

```js
baseURL: "/api/"
```

➡ Route all API calls through Nginx proxy

---

### 🔹 Nginx proxy (required)

```nginx
location /api/ {
    proxy_pass http://backend:8000;
}
```

➡ Forward frontend requests to backend container

---

### 🔹 Backend must bind correctly

```bash
daphne -b 0.0.0.0 -p 8000
```

➡ Allow other containers (Nginx) to access backend

---

### 🔹 Access frontend from network

```text
http://192.168.1.97:8080
```

➡ Use LAN IP to test from other devices

---

If you follow these exactly, your setup works end-to-end.
