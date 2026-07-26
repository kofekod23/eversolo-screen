# eversolo-screen

[Français](README.md) · [English](README.en.md) · [Español] · [Deutsch](README.de.md)

Pantalla "reproduciendo" para los streamers Eversolo (DMP-A6, A6 Master Edition, A8, A10), diseñada como el frontal de un amplificador: carátula, titulo, artista, album, calidad del flujo y progreso, a pantalla completa en una Raspberry Pi o desde cualquier navegador de la red local.

Estos dispositivos exponen una API HTTP local en el puerto 9529. Todo permanece en su red, sin cuentas ni nube.

## Hardware

- Raspberry Pi (3, 4, 5 o Zero 2 W), Raspberry Pi OS Lite es suficiente
- Pantalla HDMI (opcional, la interfaz también funciona desde un telefono)
- Pi y streamer en la misma red

## Instalación automatica

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Después abra `http://IP_DE_LA_PI:8080`: se inicia el asistente de configuración. Pide un idioma y una contraseña de administrador, y encuentra el streamer en la red por si solo (boton "Detectar"). Nada que editar a mano.

- Con `--kiosk`: la pantalla HDMI de la Pi muestra la interfaz a pantalla completa al arrancar (cage + Chromium, funciona sin escritorio).
- Sin la opción: solo se instala el servidor, accesible desde cualquier dispositivo de la red.

Los ajustes se pueden cambiar después en `http://IP_DE_LA_PI:8080/config` (hacer clic en el logo Eversolo de la pantalla también lleva alli).

## Seguridad

Ningún sistema es inviolable, pero esta aplicación aplica defensas serias y adecuadas para una red local:

- Contraseña de administrador con hash scrypt, nunca en texto claro
- Archivos sensibles (`auth.json`, `.secret_key`) creados con permisos 600
- Sesiones firmadas, cookies HttpOnly y SameSite Strict, caducidad de 12 h
- Bloqueo anti fuerza bruta: 5 fallos, luego 15 minutos bloqueado
- Token CSRF en todos los formularios
- Proxy de carátulas limitado estrictamente a la dirección del streamer (anti SSRF)
- Cabeceras de seguridad: CSP, X-Frame-Options, nosniff, Referrer-Policy
- Servidor WSGI de produccion (waitress), sin modo debug
- Servicio systemd endurecido: NoNewPrivileges, ProtectSystem, PrivateTmp, etc.
- Solo la pantalla es de lectura publica; cualquier cambio exige la contraseña

Recomendaciones: no exponga el puerto 8080 a Internet; para acceso remoto use una VPN (WireGuard, Tailscale). Contraseña olvidada: borre `auth.json` en la Pi y recargue la pagina, el asistente se reinicia.

## Comandos utiles

```bash
journalctl -u eversolo-screen@$(whoami) -f          # registros del servidor
sudo systemctl restart eversolo-screen@$(whoami)    # reiniciar el servidor
sudo systemctl restart eversolo-kiosk@$(whoami)     # reiniciar el kiosco
cd ~/eversolo-screen && ./update.sh                 # actualizar
```

## Arquitectura

- `server.py`: servidor Flask + waitress. Consulta `ZidooMusicControl/v2/getState`, normaliza los metadatos (reproductor interno, Bluetooth, apps de streaming), hace de proxy para las carátulas y ofrece el asistente de configuración protegido.
- `static/index.html`: interfaz sin framework, tipografia Fraunces / Archivo / IBM Plex Mono, ambiente de color extraido de la carátula, progreso interpolado en el cliente, interfaz traducida (fr, en, es, de).
- `install.sh`: venv de Python, servicios systemd, kiosco opcional.
