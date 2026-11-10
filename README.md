# Leafwise · Plant Identifier PWA

Features:
- Select an image or take a photo on supported mobile browsers
- Identify plants with the Baidu Plant Identification API
- Translate plant names and Baidu Baike descriptions into English for the interface
- Save identification results, confidence scores, descriptions, thumbnails, and timestamps in SQLite
- Browse the latest 100 records, delete individual records, or clear history
- PWA manifest, service worker, install entry point, and responsive mobile/desktop layout

## Run locally on Windows

1. Install Python 3.10 or newer.
2. Extract the project and open the `plant-identifier-pwa` folder.
3. Type `cmd` in the folder address bar and press Enter.
4. Create and activate a virtual environment:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   ```

5. Install dependencies:

   ```bat
   pip install -r requirements.txt
   ```

6. Set your Baidu API credentials (valid for the current terminal window):

   ```bat
   set BAIDU_API_KEY=your_new_baidu_api_key
   set BAIDU_SECRET_KEY=your_new_baidu_secret_key
   ```

7. Start the app:

   ```bat
   python app.py
   ```

8. Open `http://127.0.0.1:5000` in your browser.

## English translation of Baidu encyclopedia results

Baidu may return Chinese plant names and Baike descriptions. The backend translates these into English using Google's public web translation endpoint. An internet connection is required for translation. If the translation endpoint is unavailable, the app displays an English fallback message instead of showing Chinese text. Translation quality for botanical names can vary, so use the original encyclopedia link when you need to verify a species name.

## Mobile camera and PWA installation

- Use `http://localhost:5000` for local development on the computer.
- Camera access and PWA installation generally require HTTPS when accessed from a phone. Deploy to a host with HTTPS.
- On iPhone/iPad, use Safari's Share menu and choose Add to Home Screen. On Android, the browser usually provides an install option.
- The service worker caches static frontend resources only. Identification and history still require the backend and an internet connection.

## Deployment notes

This is a Flask backend application. It cannot be deployed by dragging the HTML folder into Netlify Drop. Use a Python/Flask-compatible host and configure `BAIDU_API_KEY` and `BAIDU_SECRET_KEY` as environment variables. `Procfile` is intended for platforms that support Gunicorn/Procfile; deployment details vary by host.

SQLite is suitable for a prototype or single-instance deployment. If the host uses an ephemeral filesystem, the database may be lost after restarts or redeployments. Use persistent storage or a managed database for long-term use.

## Security

Never put the Baidu Secret Key in frontend JavaScript, a public repository, or screenshots. If your previous key was exposed, rotate it in the Baidu console and configure the new credentials as environment variables. Do not run with `debug=True` in production.
