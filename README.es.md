# eversolo-screen

[Français](README.md) · [English](README.en.md) · [Español] · [Deutsch](README.de.md)

Pantalla "reproduciendo" para el Eversolo DMP-A6, disenada como el frontal de un amplificador: caratula, titulo, artista, album, calidad del flujo y progreso, a pantalla completa en una Raspberry Pi o desde cualquier navegador de la red local.

El DMP-A6 expone una API HTTP local en el puerto 9529. Todo permanece en su red, sin cuentas ni nube.

## Hardware

- Raspberry Pi (3, 4, 5 o Zero 2 W), Raspberry Pi OS Lite es suficiente
- Pantalla HDMI (opcional, la interfaz tambien funciona desde un telefono)
- Pi y DMP-A6 en la misma red

## Instalacion automatica

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Despues abra `http://IP_DE_LA_PI:8080`: se inicia el asistente de configuracion. Pide un idioma y una contrasena de administrador, y encuentra el DMP-A6 en la red por si solo (boton "Detectar"). Nada que editar a mano.

- Con `--kiosk`: la pantalla HDMI de la Pi muestra la interfaz a pantalla completa al arrancar (cage + Chromium, funciona sin escritorio).
- Sin la opcion: solo se instala el servidor, accesible desde cualquier dispositivo de la red.

Los ajustes se pueden cambiar despues en `http://IP_DE_LA_PI:8080/config` (hacer clic en el logo Eversolo de la pantalla tambien lleva alli).

## Seguridad

Ningun sistema es inviolable, pero esta aplicacion aplica defensas serias y adecuadas para una red local:

- Contrasena de administrador con hash scrypt, nunca en texto claro
- Archivos sensibles (`auth.json`, `.secret_key`) creados con permisos 600
- Sesiones firmadas, cookies HttpOnly y SameSite Strict, caducidad de 12 h
- Bloqueo anti fuerza bruta: 5 fallos, luego 15 minutos bloqueado
- Token CSRF en todos los formularios
- Proxy de caratulas limitado estrictamente a la direccion del streamer (anti SSRF)
- Cabeceras de seguridad: CSP, X-Frame-Options, nosniff, Referrer-Policy
- Servidor WSGI de produccion (waitress), sin modo debug
- Servicio systemd endurecido: NoNewPrivileges, ProtectSystem, PrivateTmp, etc.
- Solo la pantalla es de lectura publica; cualquier cambio exige la contrasena

Recomendaciones: no exponga el puerto 8080 a Internet; para acceso remoto use una VPN (WireGuard, Tailscale). Contrasena olvidada: borre `auth.json` en la Pi y recargue la pagina, el asistente se reinicia.

## Comandos utiles

```bash
journalctl -u eversolo-screen@$(whoami) -f          # registros del servidor
sudo systemctl restart eversolo-screen@$(whoami)    # reiniciar el servidor
sudo systemctl restart eversolo-kiosk@$(whoami)     # reiniciar el kiosco
cd ~/eversolo-screen && ./update.sh                 # actualizar
```

## Arquitectura

- `server.py`: servidor Flask + waitress. Consulta `ZidooMusicControl/v2/getState`, normaliza los metadatos (reproductor interno, Bluetooth, apps de streaming), hace de proxy para las caratulas y ofrece el asistente de configuracion protegido.
- `static/index.html`: interfaz sin framework, tipografia Fraunces / Archivo / IBM Plex Mono, ambiente de color extraido de la caratula, progreso interpolado en el cliente, interfaz traducida (fr, en, es, de).
- `install.sh`: venv de Python, servicios systemd, kiosco opcional.
